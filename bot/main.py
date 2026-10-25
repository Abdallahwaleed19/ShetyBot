"""
bot/main.py — Bot entry point with WebApp support, singleton PID lock, and auto-reconnection.
"""
import logging
import os
import sys
import time
import atexit
import signal
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)
from telegram.request import HTTPXRequest
from telegram.error import NetworkError, TimedOut, Conflict, RetryAfter

from config import BOT_TOKEN, PROXY_URL, BASE_DIR

from bot.handlers import (
    start, handle_webapp_data, verify,
    edit_report, my_report, handle_callback,
    handle_text_menu,
)

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── WebApp URL (must be HTTPS) ─────────────────────────────────────────────────
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
LOCK_FILE = BASE_DIR / ".bot.lock"


def _is_pid_running(pid: int) -> bool:
    """Checks if a process with given PID is still active on the host OS."""
    try:
        if os.name == 'nt':
            # Windows
            import ctypes
            kernel32 = ctypes.windll.kernel32
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        else:
            # Unix
            os.kill(pid, 0)
            return True
    except Exception:
        return False


def acquire_singleton_lock() -> bool:
    """Prevents multiple competing bot instances polling the same Telegram token."""
    pid = os.getpid()
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
            if old_pid != pid and _is_pid_running(old_pid):
                logger.error(f"Another bot instance is already running with PID {old_pid}. Exiting to prevent token conflicts.")
                return False
        except Exception:
            pass  # Stale or corrupted lock

    try:
        LOCK_FILE.write_text(str(pid), encoding="utf-8")
        atexit.register(release_singleton_lock)
        return True
    except Exception as e:
        logger.warning(f"Could not create lock file: {e}")
        return True


def release_singleton_lock() -> None:
    """Removes the singleton lock file upon exit."""
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


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

    # Set bot bio and description
    try:
        bio_desc = "بوت الإجازات المرضية _ لتفعيل تواصل مع \nالإدارة:@RE_i1i\nالمشرف:@WS2030W"
        short_desc = "بوت الإجازات المرضية _ لتفعيل تواصل مع الإدارة:@RE_i1i المشرف:@WS2030W"
        await app.bot.set_my_description(description=bio_desc)
        await app.bot.set_my_short_description(short_description=short_desc)
        logger.info("Bot bio and description set successfully.")
    except Exception as e:
        logger.warning(f"Could not set bot bio: {e}")


def main() -> None:
    if BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.error("BOT_TOKEN not configured!")
        sys.exit(1)

    if not acquire_singleton_lock():
        sys.exit(0)

    req_kwargs = dict(connect_timeout=30, read_timeout=30, write_timeout=30, pool_timeout=30)
    if PROXY_URL:
        req_kwargs["proxy"] = PROXY_URL
        logger.info(f"Using proxy: {PROXY_URL}")

    max_retries = 10
    retry_count = 0

    while retry_count < max_retries:
        try:
            app = (
                Application.builder()
                .token(BOT_TOKEN)
                .request(HTTPXRequest(**req_kwargs))
                .post_init(post_init)
                .build()
            )

            app.add_handler(CommandHandler("start",    start))
            app.add_handler(CommandHandler("menu",     start))
            app.add_handler(CommandHandler("verify",   verify))
            app.add_handler(CommandHandler("edit",     edit_report))
            app.add_handler(CommandHandler("myreport", my_report))
            app.add_handler(CallbackQueryHandler(handle_callback))
            app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))
            app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_menu))

            logger.info("Bot starting (polling)...")
            app.run_polling(drop_pending_updates=True, allowed_updates=["message", "callback_query"])
            break
        except (NetworkError, TimedOut) as net_err:
            retry_count += 1
            wait_time = min(30, 2 ** min(retry_count, 5))
            logger.warning(f"Network error in Telegram polling ({net_err}). Retrying in {wait_time}s... (attempt {retry_count}/{max_retries})")
            time.sleep(wait_time)
        except Conflict as conf_err:
            retry_count += 1
            logger.error(f"Telegram polling conflict: {conf_err}. Waiting 15s for other instance to release token...")
            time.sleep(15)
        except RetryAfter as retry_err:
            logger.warning(f"Rate limited by Telegram. Backing off for {retry_err.retry_after}s...")
            time.sleep(retry_err.retry_after)
        except Exception as e:
            logger.exception(f"Unexpected bot crash: {e}. Recovering in 5s...")
            time.sleep(5)
            retry_count += 1


if __name__ == "__main__":
    main()
