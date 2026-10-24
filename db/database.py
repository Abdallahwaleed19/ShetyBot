"""
db/database.py — Unified Auth, Subscription, Verification, and Audit Database.
Provides synchronous core functions and async wrappers for FastAPI.
Fast, reliable, zero-deadlock SQLite storage.
"""
from __future__ import annotations
import os
import sys
import sqlite3
import hashlib
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import BASE_DIR

logger = logging.getLogger(__name__)

DB_PATH = BASE_DIR / "seha_auth.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


class UserRecord:
    def __init__(self, row: sqlite3.Row | dict):
        d = dict(row)
        self.id = d["id"]
        self.telegram_user_id = str(d["telegram_user_id"])
        self.username = d.get("username")
        self.role = d.get("role", "user")
        self.is_active = bool(d.get("is_active", 1))

        # Parse datetimes
        s_start = d.get("subscription_start")
        if isinstance(s_start, str):
            try:
                self.subscription_start = datetime.fromisoformat(s_start)
            except Exception:
                self.subscription_start = None
        else:
            self.subscription_start = s_start

        s_end = d.get("subscription_end")
        if isinstance(s_end, str):
            try:
                self.subscription_end = datetime.fromisoformat(s_end)
            except Exception:
                self.subscription_end = None
        else:
            self.subscription_end = s_end

        self.created_at = d.get("created_at")

    def __repr__(self):
        return f"<User id={self.id} tg={self.telegram_user_id} role={self.role}>"


def init_db_sync() -> None:
    """Initializes tables for users, verifications, subscriptions, and audits."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_user_id TEXT UNIQUE NOT NULL,
        username TEXT,
        role TEXT DEFAULT 'user',
        subscription_start TEXT,
        subscription_end TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS verification_codes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        code_hash TEXT NOT NULL,
        code TEXT,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        details TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    cur.execute("""
        cur.execute('''
    CREATE TABLE IF NOT EXISTS saved_reports (
        service_code TEXT PRIMARY KEY,
        user_id INTEGER,
        telegram_user_id TEXT,
        national_id TEXT,
        patient_name_ar TEXT,
        patient_name_en TEXT,
        nationality TEXT,
        nationality_en TEXT,
        employer TEXT,
        employer_en TEXT,
        practitioner_name_ar TEXT,
        practitioner_name_en TEXT,
        job_title_ar TEXT,
        job_title_en TEXT,
        hospital_name_ar TEXT,
        hospital_name_en TEXT,
        hospital_type TEXT,
        report_type TEXT,
        admission_date TEXT,
        discharge_date TEXT,
        leave_duration_days TEXT,
        issue_date TEXT,
        report_time TEXT,
        data_json TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    CREATE TABLE IF NOT EXISTS report_ownership (
        service_code TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        telegram_user_id TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    try:
        cur.execute("ALTER TABLE verification_codes ADD COLUMN code TEXT")
    except Exception:
        pass
    conn.commit()
    conn.close()
    logger.info("Database schema initialized successfully at %s", DB_PATH)


async def init_db() -> None:
    init_db_sync()


async def get_session():
    """Async generator compatible with FastAPI Depends(get_session)."""
    class DummySession:
        pass
    yield DummySession()


# ── User Management ───────────────────────────────────────────────────────────
def get_or_create_user_sync(telegram_user_id: str = "0", username: str = None) -> UserRecord:
    conn = _get_conn()
    cur = conn.cursor()
    tg_id = str(telegram_user_id)
    cur.execute("SELECT * FROM users WHERE telegram_user_id = ?", (tg_id,))
    row = cur.fetchone()

    if not row:
        admin_id = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
        role = "admin" if (admin_id and tg_id == admin_id) else "user"

        now = datetime.now(timezone.utc)
        sub_end = now + timedelta(days=30)
        cur.execute(
            """INSERT INTO users (telegram_user_id, username, role, subscription_start, subscription_end, is_active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (tg_id, username, role, now.isoformat(), sub_end.isoformat())
        )
        conn.commit()
        user_id = cur.lastrowid
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        log_audit(user_id, "USER_CREATED", f"User {username or tg_id} created with initial 30d subscription")

    conn.close()
    return UserRecord(row)


async def get_or_create_user(session=None, telegram_user_id: str = "0", username: str = None) -> UserRecord:
    return get_or_create_user_sync(telegram_user_id, username)


def get_all_users_sync() -> List[UserRecord]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY id ASC")
    rows = cur.fetchall()
    conn.close()
    return [UserRecord(r) for r in rows]


async def get_all_users(session=None) -> List[UserRecord]:
    return get_all_users_sync()



def get_user_by_identifier_sync(identifier: str) -> Optional[UserRecord]:
    conn = _get_conn()
    cur = conn.cursor()
    val = str(identifier).strip()
    cur.execute(
        "SELECT * FROM users WHERE telegram_user_id = ? OR username = ? COLLATE NOCASE",
        (val, val)
    )
    row = cur.fetchone()
    conn.close()
    return UserRecord(row) if row else None


async def get_user_by_identifier(session=None, identifier: str = "") -> Optional[UserRecord]:
    return get_user_by_identifier_sync(identifier)


def create_new_user_sync(username: str, days: int = 30) -> UserRecord:
    conn = _get_conn()
    cur = conn.cursor()
    clean_u = str(username).strip()
    tg_id = f"user_{clean_u}"
    now = datetime.now(timezone.utc)
    sub_end = now + timedelta(days=days)
    cur.execute(
        """INSERT INTO users (telegram_user_id, username, role, subscription_start, subscription_end, is_active)
           VALUES (?, ?, 'user', ?, ?, 1)""",
        (tg_id, clean_u, now.isoformat(), sub_end.isoformat())
    )
    conn.commit()
    user_id = cur.lastrowid
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    log_audit(user_id, "USER_CREATED", f"User {clean_u} created with {days}d subscription")
    return UserRecord(row)


async def create_new_user(session=None, username: str = "", days: int = 30) -> UserRecord:
    return create_new_user_sync(username, days)


def get_latest_code_for_user_sync(user_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, code, expires_at, used, created_at 
           FROM verification_codes 
           WHERE user_id = ? 
           ORDER BY id DESC LIMIT 1""",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    exp = datetime.fromisoformat(d["expires_at"])
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    d["is_valid"] = (not d["used"]) and (now < exp)
    d["seconds_left"] = max(0, int((exp - now).total_seconds()))
    return d


async def get_latest_code_for_user(session=None, user_id: int = 0) -> Optional[Dict[str, Any]]:
    return get_latest_code_for_user_sync(user_id)

# ── Subscription Management ───────────────────────────────────────────────────
def check_subscription_sync(user_id: int = 0) -> Dict[str, Any]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"active": False, "days_remaining": 0, "message": "المستخدم غير موجود"}

    user = UserRecord(row)
    if not user.is_active:
        return {"active": False, "days_remaining": 0, "message": "الحساب معطل"}

    if not user.subscription_end:
        return {"active": False, "days_remaining": 0, "message": "لا يوجد اشتراك"}

    now = datetime.now(timezone.utc)
    sub_end = user.subscription_end
    if sub_end.tzinfo is None:
        sub_end = sub_end.replace(tzinfo=timezone.utc)

    diff = sub_end - now
    total_sec = diff.total_seconds()

    if total_sec <= 0:
        return {"active": False, "days_remaining": 0, "message": "انتهى الاشتراك"}

    import math
    days_remaining = max(1, int(math.ceil(total_sec / 86400)))

    message = f"متبقي على انتهاء الاشتراك {days_remaining} يوم"
    return {"active": True, "days_remaining": days_remaining, "message": message}


async def check_subscription(session=None, user_id: int = 0) -> Dict[str, Any]:
    return check_subscription_sync(user_id)


def renew_subscription_sync(user_id: int = 0, days: int = 30) -> UserRecord:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError("User not found")

    user = UserRecord(row)
    now = datetime.now(timezone.utc)

    current_end = user.subscription_end
    if current_end and current_end.tzinfo is None:
        current_end = current_end.replace(tzinfo=timezone.utc)

    if current_end and current_end > now:
        new_end = current_end + timedelta(days=days)
        new_start = user.subscription_start or now
    else:
        new_start = now
        new_end = now + timedelta(days=days)

    cur.execute(
        """UPDATE users 
           SET subscription_start = ?, subscription_end = ?, is_active = 1, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (new_start.isoformat(), new_end.isoformat(), user_id)
    )
    conn.commit()

    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    updated_row = cur.fetchone()
    conn.close()

    log_audit(user_id, "RENEW_SUBSCRIPTION", f"Subscription renewed by {days} days until {new_end.isoformat()}")
    return UserRecord(updated_row)


async def renew_subscription(session=None, user_id: int = 0, days: int = 30) -> UserRecord:
    return renew_subscription_sync(user_id, days)


# ── Verification Codes (5-digit, strictly 10s expiry) ─────────────────────────
def create_verification_code_sync(user_id: int = 0) -> str:
    code = f"{random.randint(10000, 99999)}"
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=10)

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO verification_codes (user_id, code_hash, code, expires_at, used)
           VALUES (?, ?, ?, ?, 0)""",
        (user_id, code_hash, code, expires_at.isoformat())
    )
    conn.commit()
    conn.close()

    log_audit(user_id, "CODE_REQUESTED", "Verification code generated (10s expiry)")
    return code


async def create_verification_code(session=None, user_id: int = 0) -> str:
    return create_verification_code_sync(user_id)


def verify_code_sync(user_id: int = 0, code: str = "") -> bool:
    code_hash = hashlib.sha256(str(code).strip().encode("utf-8")).hexdigest()

    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, expires_at FROM verification_codes 
           WHERE user_id = ? AND code_hash = ? AND used = 0
           ORDER BY id DESC LIMIT 1""",
        (user_id, code_hash)
    )
    row = cur.fetchone()

    if not row:
        conn.close()
        log_audit(user_id, "CODE_FAILED", "Invalid code attempted")
        return False

    code_id = row["id"]
    exp_dt = datetime.fromisoformat(row["expires_at"])
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=timezone.utc)

    if datetime.now(timezone.utc) > exp_dt:
        cur.execute("UPDATE verification_codes SET used = 1 WHERE id = ?", (code_id,))
        conn.commit()
        conn.close()
        log_audit(user_id, "CODE_EXPIRED", "Verification code expired (exceeded 10 seconds)")
        return False

    cur.execute("UPDATE verification_codes SET used = 1 WHERE id = ?", (code_id,))
    conn.commit()
    conn.close()

    log_audit(user_id, "CODE_VERIFIED", "Verification code verified successfully")
    return True


async def verify_code(session=None, user_id: int = 0, code: str = "") -> bool:
    return verify_code_sync(user_id, code)


# ── Data Isolation & Report Ownership ─────────────────────────────────────────
def record_report_ownership_sync(service_code: str = "", user_id: int = 0, telegram_user_id: str = "0"):
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT OR REPLACE INTO report_ownership (service_code, user_id, telegram_user_id)
           VALUES (?, ?, ?)""",
        (str(service_code), int(user_id), str(telegram_user_id))
    )
    conn.commit()
    conn.close()


async def record_report_ownership(session=None, service_code: str = "", user_id: int = 0, telegram_user_id: str = "0"):
    record_report_ownership_sync(service_code, user_id, telegram_user_id)


def verify_report_ownership_sync(service_code_or_id: Any = "", user_id: int = 0) -> bool:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id FROM report_ownership WHERE service_code = ?",
        (str(service_code_or_id),)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return True
    return row["user_id"] == int(user_id)


async def verify_report_ownership(session=None, service_code_or_id: Any = "", user_id: int = 0) -> bool:
    return verify_report_ownership_sync(service_code_or_id, user_id)


def get_user_reports_sync(user_id: int = 0) -> list[str]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT service_code FROM report_ownership WHERE user_id = ?", (int(user_id),))
    rows = cur.fetchall()
    conn.close()
    return [r["service_code"] for r in rows]


async def get_user_reports(session=None, user_id: int = 0) -> list[str]:
    return get_user_reports_sync(user_id)


# ── Audit Logging ─────────────────────────────────────────────────────────────
def log_audit(user_id: Optional[int], action: str, details: str = ""):
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_logs (user_id, action, details) VALUES (?, ?, ?)",
            (user_id, str(action), str(details))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Failed to write audit log: {e}")


# ── Saved Reports Management ──────────────────────────────────────────────────
def save_report_full_sync(data: dict) -> None:
    import json
    conn = _get_conn()
    cur = conn.cursor()
    sc = str(data.get("service_code", "")).strip()
    if not sc:
        conn.close()
        return
    cur.execute(
        """INSERT OR REPLACE INTO saved_reports (
            service_code, user_id, telegram_user_id, national_id,
            patient_name_ar, patient_name_en, nationality, nationality_en,
            employer, employer_en, practitioner_name_ar, practitioner_name_en,
            job_title_ar, job_title_en, hospital_name_ar, hospital_name_en,
            hospital_type, report_type, admission_date, discharge_date,
            leave_duration_days, issue_date, report_time, data_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (
            sc,
            int(data.get("user_id") or 0),
            str(data.get("telegram_user_id") or "0"),
            str(data.get("national_id") or ""),
            str(data.get("patient_name_ar") or ""),
            str(data.get("patient_name_en") or ""),
            str(data.get("nationality") or ""),
            str(data.get("nationality_en") or ""),
            str(data.get("employer") or ""),
            str(data.get("employer_en") or ""),
            str(data.get("practitioner_name_ar") or ""),
            str(data.get("practitioner_name_en") or ""),
            str(data.get("job_title_ar") or ""),
            str(data.get("job_title_en") or ""),
            str(data.get("hospital_name_ar") or ""),
            str(data.get("hospital_name_en") or ""),
            str(data.get("hospital_type") or "government"),
            str(data.get("report_type") or "GSL"),
            str(data.get("admission_date") or ""),
            str(data.get("discharge_date") or ""),
            str(data.get("leave_duration_days") or "1"),
            str(data.get("issue_date") or ""),
            str(data.get("report_time") or ""),
            json.dumps(data, ensure_ascii=False)
        )
    )
    conn.commit()
    conn.close()


def get_all_saved_reports_sync(user_id: Optional[int] = None, telegram_user_id: Optional[str] = None) -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    if user_id:
        cur.execute("SELECT * FROM saved_reports WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    elif telegram_user_id and telegram_user_id != "0":
        cur.execute("SELECT * FROM saved_reports WHERE telegram_user_id = ? ORDER BY created_at DESC", (str(telegram_user_id),))
    else:
        cur.execute("SELECT * FROM saved_reports ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
