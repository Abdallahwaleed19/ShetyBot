"""
web/app.py — FastAPI application entry point.
Run:  uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from db.worker_client import get_client, close_client, health_check
from web.routes import router
from config import BASE_DIR, REPORTS_DIR

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure local database tables are created
    from db.database import init_db_sync
    try:
        init_db_sync()
        logger.info("✅ Auth and ownership database initialized.")
    except Exception as e:
        logger.warning(f"⚠️ Auth database init error: {e}")

    # Startup: warm up the HTTP client & check Worker
    await get_client()
    ok = await health_check()
    if ok:
        logger.info("✅ Cloudflare Worker is reachable.")
    else:
        logger.warning("⚠️  Cloudflare Worker health-check failed — continuing anyway.")


    # Startup: warm up PDF font cache in background thread (avoids first-request delay)
    try:
        import asyncio as _asyncio
        from pdf.generator import _warmup_font_cache
        await _asyncio.to_thread(_warmup_font_cache)
        logger.info("✅ PDF font cache warmed up.")
    except Exception as _e:
        logger.warning(f"⚠️ PDF font warmup failed: {_e}")
    yield
    # Shutdown: close the shared HTTP client
    await close_client()


app = FastAPI(
    title="Sick Leave Verification — منصة التحقق من التقارير المرضية",
    description="Verify sick leave reports issued via the Telegram bot.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS Middleware to support smooth API calls from web, mobile, and bot WebApp
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
static_dir = BASE_DIR / "web" / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Serve generated PDFs
app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR)), name="reports")

app.include_router(router)
