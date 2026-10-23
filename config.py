"""
config.py — Central configuration via environment variables.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).parent

# ── Telegram ────────────────────────────────────────────────────────────────
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
PROXY_URL:  str = os.getenv("PROXY_URL", "").strip()

# ── Cloudflare Worker API ────────────────────────────────────────────────────
WORKER_URL: str = os.getenv(
    "WORKER_URL",
    "https://seha-api.ramo-711-vip.workers.dev"
).rstrip("/")

# Optional secret token to protect your Worker endpoints
WORKER_SECRET: str = os.getenv("WORKER_SECRET", "")

# ── File Storage (local cache for PDF generation) ────────────────────────────
UPLOADS_DIR: Path = BASE_DIR / "uploads"
REPORTS_DIR: Path = BASE_DIR / "reports"
UPLOADS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# ── Web App ──────────────────────────────────────────────────────────────────
WEBAPP_URL: str = os.getenv("WEBAPP_URL", "")
WEB_HOST:   str = os.getenv("WEB_HOST", "0.0.0.0")
# Fly.io injects PORT, Railway injects PORT, local uses WEB_PORT
WEB_PORT:   int = int(os.getenv("PORT", os.getenv("WEB_PORT", "8000")))
