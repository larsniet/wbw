import os
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Tuple
from dotenv import load_dotenv
from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from fastapi import FastAPI
from database import Database
from monitor import PageMonitor
import uvicorn
from threading import Thread
import re

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI()

# Initialize database
db = Database()

# States for conversation handler
URL, SELECTORS = range(2)  # Removed INTERVAL state

# Store user conversation data temporarily
user_data: Dict[int, dict] = {}

# Store active monitoring tasks and their monitors
monitoring_tasks: Dict[int, Tuple[asyncio.Task, PageMonitor]] = {}

def clean_selector(selector: str) -> str:
    """Clean and escape a CSS selector."""
    # Handle multiple classes for the same element (e.g., ".class1 class2" -> ".class1.class2")
    if selector.startswith('.') and ' ' in selector and not selector.count(' ') > selector.count('.'):
        # Check if this looks like multiple classes for the same element
        parts = selector.split()
        if all(part.startswith('.') or not part.startswith(('.', '#')) for part in parts):
            # Convert ".class1 class2" to ".class1.class2" for same-element multiple classes
            if len(parts) == 2 and not parts[1].startswith('.') and not parts[1].startswith('#'):
                return f".{parts[0][1:]}.{parts[1]}"
    
    # For complex selectors or descendant selectors, don't modify
    if ' ' in selector and selector.count(' ') > 1:
        return selector
    
    # Original logic for IDs and simple selectors
    if selector.startswith('#') or selector.startswith('.'):
        prefix = selector[0]
        value = selector[1:]
        
        # For IDs, we need to escape special characters in a way that Selenium accepts
        # But don't escape spaces in class selectors as they might be intentional
        escaped = ''
        for char in value:
            if char in '.,()' and selector.startswith('#'):  # Only escape for IDs, not classes
                escaped += '\\' + char
            else:
                escaped += char
        
        return prefix + escaped.replace('\\\\', '\\')  # Remove any double escapes
    return selector

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the conversation and ask for URL."""
    chat_id = update.effective_chat.id
    logger.info(f"User {chat_id} started the conversation")
    
    active_count = db.get_active_sessions_count()
    logger.info(f"Current active sessions: {active_count}")
    
    if active_count >= 5:
        logger.info(f"Rejecting user {chat_id} due to session limit")
        await update.message.reply_text(
            "Sorry, the maximum number of active monitoring sessions (5) has been reached. "
            "Please try again later."
        )
        return ConversationHandler.END

    existing_session = db.get_session(chat_id)
    if existing_session:
        logger.info(f"User {chat_id} already has an active session")
        await update.message.reply_text(
            "You already have an active monitoring session. "
            "Use /stop to end it before starting a new one."
        )
        return ConversationHandler.END

    logger.info(f"Prompting user {chat_id} for URL")
    await update.message.reply_text(
        "Let's set up your page monitoring. "
        "Please send me the URL you want to monitor:"
    )
    return URL

async def url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the URL and ask for element selectors."""
    chat_id = update.effective_chat.id
    url = update.message.text
    logger.info(f"User {chat_id} provided URL: {url}")
    
    user_data[chat_id] = {"url": url}
    logger.info(f"Stored URL for user {chat_id}")
    
    await update.message.reply_text(
        "Great! Now send me the CSS selector(s) for the element(s) you want to monitor. "
        "You can send multiple selectors, one per line.\n\n"
        "Examples:\n"
        "- For elements with ID: #my-element\n"
        "- For elements with class: .status-text\n"
        "- For specific elements: button[type='submit']"
    )
    return SELECTORS

async def selectors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the selectors and start monitoring."""
    chat_id = update.effective_chat.id
    raw_selectors = update.message.text.strip().split('\n')
    
    # Clean and escape each selector
    selectors = [clean_selector(s.strip()) for s in raw_selectors]
    logger.info(f"User {chat_id} provided selectors: {selectors}")
    
    user_data[chat_id]["selectors"] = selectors
    logger.info(f"Stored cleaned selectors for user {chat_id}: {selectors}")

    # Use hardcoded 60-second interval
    interval = 60
    user_info = user_data[chat_id]
    logger.info(f"Starting session for user {chat_id} with data: {user_info}")
    
    # Send acknowledgment message about which elements we're looking for
    element_list = "\n".join([f"- {s}" for s in raw_selectors])
    await update.message.reply_text(
        f"I'll look for these elements on the page:\n{element_list}\n\n"
        f"Let me verify I can find them..."
    )

    # Create monitor instance
    monitor = PageMonitor()
    try:
        success, element_texts, error = monitor.check_elements(user_info["url"], user_info["selectors"])
        if not success:
            logger.error(f"Initial element check failed for user {chat_id}: {error}")
            await update.message.reply_text(
                f"Sorry, I couldn't find one or more elements: {error}\n"
                "Please check your selectors and try again with /start"
            )
            return ConversationHandler.END
    except Exception as e:
        monitor.close_driver()
        logger.error(f"Error during initial check for user {chat_id}: {e}")
        await update.message.reply_text(
            f"Sorry, something went wrong during setup: {str(e)}\n"
            "Please try again with /start"
        )
        return ConversationHandler.END

    # Add session to database
    if not db.add_session(
        chat_id,
        user_info["url"],
        user_info["selectors"],
        interval
    ):
        logger.error(f"Failed to add session for user {chat_id}")
        monitor.close_driver()
        await update.message.reply_text(
            "Failed to start monitoring session. Please try again later."
        )
        return ConversationHandler.END

    logger.info(f"Session added to database for user {chat_id}")

    # Start monitoring task
    task = asyncio.create_task(
        monitor_page(
            chat_id,
            user_info["url"],
            user_info["selectors"],
            interval,
            context.bot,
            monitor
        )
    )
    monitoring_tasks[chat_id] = (task, monitor)
    logger.info(f"Monitoring task created for user {chat_id}")

    # Only send success message after we've verified everything works
    await update.message.reply_text(
        f"Great! I found all the elements. Monitoring has started!\n"
        f"I'll check the page every {interval} seconds and "
        f"notify you if any element text changes or if elements disappear.\n\n"
        f"Use /stop to end monitoring."
    )

    # Cleanup temporary data
    if chat_id in user_data:
        del user_data[chat_id]
        logger.info(f"Cleaned up temporary data for user {chat_id}")

    return ConversationHandler.END

async def monitor_page(chat_id: int, url: str, selectors: list, interval: int, bot: Bot, monitor: PageMonitor):
    """Background task to monitor the page for changes."""
    logger.info(f"Starting monitoring task for user {chat_id}")
    logger.info(f"URL: {url}")
    logger.info(f"Selectors: {selectors}")
    logger.info(f"Interval: {interval} seconds")
    
    start_time = datetime.now()
    
    try:
        while True:
            logger.info(f"Checking page for user {chat_id}")
            
            # Check if monitoring should stop due to time limit
            if monitor.should_stop_monitoring(start_time):
                logger.info(f"Time limit reached for user {chat_id}")
                await bot.send_message(
                    chat_id=chat_id,
                    text="Monitoring stopped: 12-hour time limit reached."
                )
                break

            # Check elements
            logger.info(f"Checking elements for user {chat_id}")
            success, element_texts, error = monitor.check_elements(url, selectors, allow_missing=True)
            
            # Handle missing elements (treat as change detection)
            if success == "missing":
                logger.info(f"Elements missing for user {chat_id}: {error}")
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"Element disappeared! Check the page: {url}\nMissing: {error}"
                )
                break
            
            # Handle other errors
            if not success:
                logger.error(f"Element check failed for user {chat_id}: {error}")
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"Error monitoring page: {error}"
                )
                break

            # Get previous element texts
            session = db.get_session(chat_id)
            if not session:
                logger.info(f"Session not found for user {chat_id}, stopping monitoring")
                break

            # Check for changes
            logger.info(f"Current element texts for user {chat_id}: {element_texts}")
            logger.info(f"Previous element texts: {session['last_element_texts']}")
            
            if monitor.has_changes(session["last_element_texts"], element_texts):
                logger.info(f"Element text changed for user {chat_id}")
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"Element text changed! Check the page: {url}"
                )
                break

            # Update stored element texts
            logger.info(f"Updating element texts for user {chat_id}")
            db.update_element_texts(chat_id, element_texts)
            
            logger.info(f"Sleeping for {interval} seconds")
            await asyncio.sleep(interval)

    except Exception as e:
        logger.error(f"Error in monitoring task for user {chat_id}: {e}")
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"An error occurred while monitoring: {str(e)}"
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message to user {chat_id}: {send_error}")
    finally:
        logger.info(f"Cleaning up monitoring task for user {chat_id}")
        monitor.close_driver()
        db.remove_session(chat_id)
        if chat_id in monitoring_tasks:
            del monitoring_tasks[chat_id]
        logger.info(f"Monitoring stopped for user {chat_id}")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Stop monitoring for the user."""
    chat_id = update.effective_chat.id
    logger.info(f"User {chat_id} requested to stop monitoring")
    
    if chat_id in monitoring_tasks:
        logger.info(f"Cancelling monitoring task for user {chat_id}")
        task, monitor = monitoring_tasks[chat_id]
        monitor.stop()  # Signal the monitor to stop
        task.cancel()  # Cancel the monitoring task
        del monitoring_tasks[chat_id]
        db.remove_session(chat_id)
        await update.message.reply_text("Monitoring stopped.")
        logger.info(f"Monitoring stopped for user {chat_id}")
    else:
        logger.info(f"No active monitoring found for user {chat_id}")
        await update.message.reply_text("No active monitoring session found.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    chat_id = update.effective_chat.id
    logger.info(f"User {chat_id} cancelled the setup")
    
    if chat_id in user_data:
        del user_data[chat_id]
        logger.info(f"Cleaned up temporary data for user {chat_id}")
    
    await update.message.reply_text("Setup cancelled.")
    return ConversationHandler.END

def run_bot():
    """Run the bot."""
    logger.info("Starting the bot")
    # Create application and add handlers
    application = Application.builder().token(os.getenv("TELEGRAM_BOT_TOKEN")).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, url)],
            SELECTORS: [MessageHandler(filters.TEXT & ~filters.COMMAND, selectors)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("stop", stop))

    logger.info("Bot handlers configured")
    # Start the bot
    logger.info("Starting bot polling")
    application.run_polling()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    logger.info("Health check requested")
    return {"status": "ok"}

def run_api():
    """Run the FastAPI server."""
    logger.info("Starting FastAPI server")
    uvicorn.run(app, host="0.0.0.0", port=8080)

if __name__ == "__main__":
    logger.info("Application starting")
    # Start FastAPI in a separate thread
    api_thread = Thread(target=run_api, daemon=True)
    api_thread.start()
    logger.info("API thread started")

    # Run the bot in the main thread
    logger.info("Starting bot in main thread")
    run_bot() 