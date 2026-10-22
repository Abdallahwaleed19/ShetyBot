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

# ── Database (MySQL — نفس قاعدة Laravel) ─────────────────────────────────
# بعد الرفع على الاستضافة غيّر المتغيرات دي في بيئة التشغيل فقط
DB_HOST: str = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT: int = int(os.getenv("DB_PORT", "3307"))
DB_NAME: str = os.getenv("DB_NAME", "seha_db")
DB_USER: str = os.getenv("DB_USER", "root")
DB_PASS: str = os.getenv("DB_PASS", "")

# aiomysql async driver — نفس قاعدة Laravel
DATABASE_URL: str = (
    f"mysql+aiomysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    "?charset=utf8mb4"
)

# ── File Storage ─────────────────────────────────────────────────────────────
UPLOADS_DIR: Path = BASE_DIR / "uploads"
REPORTS_DIR: Path = BASE_DIR / "reports"
UPLOADS_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)

# ── Web App ──────────────────────────────────────────────────────────────────
WEB_HOST: str = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT: int = int(os.getenv("WEB_PORT", "8000"))
