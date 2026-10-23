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

from db.worker_client import get_client, close_client, health_check
from web.routes import router
from config import BASE_DIR

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: warm up the HTTP client & check Worker
    await get_client()
    ok = await health_check()
    if ok:
        logger.info("✅ Cloudflare Worker is reachable.")
    else:
        logger.warning("⚠️  Cloudflare Worker health-check failed — continuing anyway.")
    yield
    # Shutdown: close the shared HTTP client
    await close_client()


app = FastAPI(
    title="Sick Leave Verification — منصة التحقق من التقارير المرضية",
    description="Verify sick leave reports issued via the Telegram bot.",
    version="2.0.0",
    lifespan=lifespan,
)

# Static files
static_dir = BASE_DIR / "web" / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Serve generated PDFs
app.mount("/reports", StaticFiles(directory=str(BASE_DIR / "reports")), name="reports")

app.include_router(router)
