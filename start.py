"""
start.py — Runs both the Telegram bot and FastAPI web server concurrently.
Used for Railway/production deployment (single process, two async tasks).
"""
import asyncio
import logging
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(__file__))

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("start")


def run_web():
    """Run FastAPI with uvicorn in a thread (no reload in production)."""
    import uvicorn
    port = int(os.getenv("PORT", os.getenv("WEB_PORT", "8000")))
    host = os.getenv("WEB_HOST", "0.0.0.0")
    logger.info(f"Starting web server on {host}:{port}")
    uvicorn.run(
        "web.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        timeout_keep_alive=120,
        limit_concurrency=100,
        timeout_graceful_shutdown=30,
    )


def run_bot():
    """Run Telegram bot polling in a thread."""
    from bot.main import main
    logger.info("Starting Telegram bot...")
    main()


if __name__ == "__main__":
    logger.info("Starting SehtyBot — Web + Bot together")

    # Run web server in background thread
    web_thread = threading.Thread(target=run_web, daemon=True, name="WebServer")
    web_thread.start()

    # Run bot in main thread (blocking)
    run_bot()
