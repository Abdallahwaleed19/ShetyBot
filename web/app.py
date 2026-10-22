"""
web/app.py — FastAPI verification web application.
Run:  uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from db.database import init_db
from web.routes import router
from config import BASE_DIR


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="Sick Leave Verification — منصة التحقق من الإجازات المرضية",
    description="Verify sick leave reports issued via the Telegram bot.",
    version="1.0.0",
    lifespan=lifespan,
)

# Serve static files (CSS, etc.)
static_dir = BASE_DIR / "web" / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount reports directory so PDFs are downloadable
app.mount("/reports", StaticFiles(directory=str(BASE_DIR / "reports")), name="reports")

app.include_router(router)
