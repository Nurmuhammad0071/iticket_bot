import os
import nest_asyncio
nest_asyncio.apply()  # Allow nested event loops

import asyncio
import logging
import requests
from datetime import datetime
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# Configure logging to see all actions in the console
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# Global constants and configuration
API_URL = "https://api.iticket.uz/ru/v5/events/concerts/uzbekistan-vs-kyrgyz-republic?client=web"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 8000))

# Store background auto-check tasks per chat
auto_check_tasks = {}

def check_tickets():
    """
    Check the API and return the number of available tickets.
    """
    try:
        response = requests.get(API_URL)
        if response.status_code == 200:
            data = response.json()
            available = data.get("available_tickets_count", 0)
            logging.info(f"API checked at {datetime.now()} - Tickets available: {available}")
            return available
        else:
            logging.error(f"API error: status code {response.status_code}")
            return None
    except Exception as e:
        logging.error("Error fetching API data: %s", e)
        return None

# Telegram bot handler functions

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the /start command and sends a persistent menu.
    """
    keyboard = [
        [InlineKeyboardButton("Manual Check", callback_data="manual_check")],
        [InlineKeyboardButton("Start Auto Check", callback_data="start_auto")],
        [InlineKeyboardButton("Stop Auto Check", callback_data="stop_auto")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Ticket Checker Menu:", reply_markup=reply_markup)
    logging.info(f"Sent start menu to chat {update.message.chat.id}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles button presses for manual check and auto-check.
    The menu remains persistent.
    """
    query = update.callback_query
    chat_id = query.message.chat.id
    action = query.data
    logging.info(f"Chat {chat_id} clicked button: {action}")

    if action == "manual_check":
        available_tickets = check_tickets()
        if available_tickets is None:
            await query.answer("Error fetching data.", show_alert=True)
        elif available_tickets > 0:
            # Send a notification only if tickets are available.
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Tickets are available! ({available_tickets} available)"
            )
            await query.answer("Tickets found!")
        else:
            await query.answer("No tickets available.", show_alert=False)

    elif action == "start_auto":
        if chat_id in auto_check_tasks:
            await query.answer("Auto check already running.", show_alert=True)
        else:
            task = asyncio.create_task(auto_check_loop(context, chat_id))
            auto_check_tasks[chat_id] = task
            await query.answer("Started auto check.")
            logging.info(f"Auto check started for chat {chat_id}")

    elif action == "stop_auto":
        if chat_id in auto_check_tasks:
            task = auto_check_tasks.pop(chat_id)
            task.cancel()
            await query.answer("Stopped auto check.")
            logging.info(f"Auto check stopped for chat {chat_id}")
        else:
            await query.answer("Auto check is not running.", show_alert=True)

async def auto_check_loop(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """
    Runs every 30 seconds; checks API and sends a message only if tickets are available.
    """
    try:
        while True:
            available_tickets = check_tickets()
            if available_tickets is None:
                logging.error(f"Auto-check error in chat {chat_id}")
            elif available_tickets > 0:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"Tickets are available! ({available_tickets} available)"
                )
                logging.info(f"Auto-check found tickets for chat {chat_id}")
            else:
                logging.info(f"Auto-check: No tickets for chat {chat_id}")
            await asyncio.sleep(30)
    except asyncio.CancelledError:
        logging.info(f"Auto check for chat {chat_id} cancelled.")
    except Exception as e:
        logging.error("Error in auto check loop for chat %s: %s", chat_id, e)

# Function to start the Telegram bot
async def start_bot():
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    logging.info("Telegram bot is running...")
    await application.run_polling()

# Create FastAPI app for binding to a port
app = FastAPI()

@app.get("/", response_class=PlainTextResponse)
async def root():
    return "Bot is running."

# On startup, run the Telegram bot in the background
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_bot())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)
