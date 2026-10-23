"""
bot/main.py — Bot entry point with WebApp support.
"""
import logging
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from telegram.ext import Application, CommandHandler, MessageHandler, filters
from telegram.request import HTTPXRequest

from config import BOT_TOKEN, PROXY_URL

from bot.handlers import start, handle_webapp_data, verify

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── WebApp URL (must be HTTPS) ─────────────────────────────────────────────────
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()


async def post_init(app) -> None:
    form_url = (WEBAPP_URL.rstrip("/") + "/form") if WEBAPP_URL else ""
    app.bot_data["webapp_url"] = form_url
    if form_url:
        logger.info(f"WebApp URL: {form_url}")
    else:
        logger.warning(
            "WEBAPP_URL not set in .env!\n"
            "Run ngrok/cloudflared then add WEBAPP_URL=https://xxxx.ngrok.io to .env"
        )


def main() -> None:
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.error("BOT_TOKEN not configured!")
        sys.exit(1)

    req_kwargs = dict(connect_timeout=30, read_timeout=30, write_timeout=30, pool_timeout=30)
    if PROXY_URL:
        req_kwargs["proxy"] = PROXY_URL
        logger.info(f"Using proxy: {PROXY_URL}")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(HTTPXRequest(**req_kwargs))
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("verify", verify))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))

    logger.info("Bot starting (polling)…")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
