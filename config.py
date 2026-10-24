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

# ── Admin Account & Credentials ──────────────────────────────────────────────
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "As1_oi").lstrip("@").strip()
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "ramo.711.vip@gmail.com").strip().lower()
ADMIN_TELEGRAM_ID: str = os.getenv("ADMIN_TELEGRAM_ID", "8733335095").strip()
ADMIN_KEY: str = os.getenv("ADMIN_KEY", "admin123").strip()

# ── OTP Security ─────────────────────────────────────────────────────────────
# Central setting for verification code lifetime: exactly 30 seconds
OTP_TTL_SECONDS: int = int(os.getenv("OTP_TTL_SECONDS", "30"))

# ── Email Service (SMTP) ─────────────────────────────────────────────────────
SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "").strip()
SMTP_PASS: str = os.getenv("SMTP_PASS", "").strip()
SMTP_FROM: str = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", "no-reply@seha.sa")).strip()

# ── Cloudflare Worker API ────────────────────────────────────────────────────
WORKER_URL: str = os.getenv(
    "WORKER_URL",
    "https://seha-api.ramo-711-vip.workers.dev"
).rstrip("/")

# Optional secret token to protect your Worker endpoints
WORKER_SECRET: str = os.getenv("WORKER_SECRET", "sehabot").strip()

# ── Database (SQLite for local/Fly.io auth, or MySQL/Postgres if configured) ──
DEFAULT_DB_PATH = BASE_DIR / "seha_auth.db"
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{DEFAULT_DB_PATH.as_posix()}"
)

# ── File Storage (local cache for PDF generation) ────────────────────────────
UPLOADS_DIR: Path = BASE_DIR / "uploads"
REPORTS_DIR: Path = BASE_DIR / "reports"
UPLOADS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# ── Web App ──────────────────────────────────────────────────────────────────
WEBAPP_URL: str = os.getenv("WEBAPP_URL", "")
WEB_HOST:   str = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT:   int = int(os.getenv("PORT", os.getenv("WEB_PORT", "8000")))
