"""
Whale Alert Bot
Monitors large cryptocurrency transactions and sends alerts.
"""
import os
import asyncio
import logging
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
MIN_VALUE = float(os.getenv("MIN_VALUE", "100000"))
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "120"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "15"))

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

subscribers: set = set()
known: set = set()


def is_admin(chat_id: Any) -> bool:
    if not ADMIN_CHAT_ID:
        return True
    return str(chat_id) in ADMIN_CHAT_ID.split(",")


async def fetch_whale_tx() -> list:
    url = "https://api.whale-alert.io/v1/transactions"
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            r = await client.get(url, params={"api_key": "free", "min_value": MIN_VALUE, "limit": 10})
            if r.status_code == 200:
                return r.json().get("transactions", [])
    except Exception as e:
        logger.warning(f"Whale fetch failed: {e}")
    return []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    await update.message.reply_text(
        "🐋 Whale Alert Bot\n\n"
        "/subscribe - Subscribe\n"
        "/unsubscribe - Unsubscribe\n"
        "/status - Status"
    )


async def cmd_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    if not is_admin(update.effective_chat.id):
        return
    subscribers.add(update.effective_chat.id)
    await update.message.reply_text("✅ Subscribed to whale alerts.")


async def cmd_unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    subscribers.discard(update.effective_chat.id)
    await update.message.reply_text("✅ Unsubscribed.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    await update.message.reply_text(f"📊 Subscribers: {len(subscribers)}\nMin value: ${MIN_VALUE:,.0f}")


async def monitor(app: Application) -> None:
    first_run = True
    while True:
        try:
            txs = await fetch_whale_tx()
            if first_run:
                for tx in txs:
                    known.add(tx.get("hash", str(tx)))
                first_run = False
                continue
            for tx in txs:
                tid = tx.get("hash", str(tx))
                if tid in known:
                    continue
                known.add(tid)
                text = (
                    f"🐋 <b>Whale Alert</b>\n\n"
                    f"From: {tx.get('from', 'unknown')}\n"
                    f"To: {tx.get('to', 'unknown')}\n"
                    f"Amount: <b>{tx.get('amount', 0):,.2f} {tx.get('symbol', 'BTC')}</b>\n"
                    f"Value: <b>${tx.get('amount_usd', 0):,.0f}</b>"
                )
                for chat_id in list(subscribers):
                    try:
                        await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                    except Exception as e:
                        logger.warning(f"Alert failed: {e}")
                    await asyncio.sleep(0.3)
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


async def post_init(application: Application) -> None:
    asyncio.create_task(monitor(application))
    commands = [BotCommand("start", "Start"), BotCommand("subscribe", "Subscribe"), BotCommand("unsubscribe", "Unsubscribe"), BotCommand("status", "Status")]
    await application.bot.set_my_commands(commands)


def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN missing!")
        return
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("subscribe", cmd_subscribe))
    application.add_handler(CommandHandler("unsubscribe", cmd_unsubscribe))
    application.add_handler(CommandHandler("status", cmd_status))
    application.run_polling()


if __name__ == "__main__":
    main()
