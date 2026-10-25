"""
db/database.py — SQLite storage for users, verification codes, audit logs, and reports.
"""
import os
import sys
import logging
import sqlite3
import hashlib
import random
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from config import (
    BASE_DIR,
    ADMIN_USERNAME,
    ADMIN_USERNAMES,
    ADMIN_EMAIL,
    ADMIN_TELEGRAM_ID,
    OTP_TTL_SECONDS,
    ACTIVE_USER_MINUTES,
)

logger = logging.getLogger(__name__)

DB_PATH = BASE_DIR / "seha_auth.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


class UserRecord:
    def __init__(self, row: sqlite3.Row | dict):
        d = dict(row)
        self.id = d["id"]
        self.telegram_user_id = str(d.get("telegram_user_id", "0"))
        self.username = d.get("username")
        self.role = d.get("role", "user")
        self.is_active = bool(d.get("is_active", 1))

        # Registration & Identity fields
        self.email = d.get("email")
        self.full_name_ar = d.get("full_name_ar")
        self.full_name_en = d.get("full_name_en")
        self.registration_status = d.get("registration_status", "ACTIVE")
        self.rejection_reason = d.get("rejection_reason")

        # Parse approval dates
        self.approved_at = d.get("approved_at")
        self.approved_by = d.get("approved_by")

        # Parse subscription datetimes
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
        self.updated_at = d.get("updated_at")
        self.last_active_at = d.get("last_active_at")

    def __repr__(self):
        return f"<User id={self.id} tg={self.telegram_user_id} u={self.username} status={self.registration_status} role={self.role}>"


def init_db_sync() -> None:
    """Initializes tables for users, verifications, subscriptions, audits, and saved reports."""
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_user_id TEXT UNIQUE NOT NULL,
        username TEXT,
        full_name_ar TEXT,
        full_name_en TEXT,
        email TEXT,
        role TEXT DEFAULT 'user',
        registration_status TEXT DEFAULT 'PENDING_APPROVAL',
        rejection_reason TEXT,
        approved_at TEXT,
        approved_by TEXT,
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
        attempts INTEGER DEFAULT 0,
        purpose TEXT DEFAULT 'auth',
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
        is_deleted INTEGER DEFAULT 0,
        deleted_at TEXT,
        deleted_by TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS report_ownership (
        service_code TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        telegram_user_id TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Safe Schema Migrations (Add missing columns if table already existed)
    alter_queries = [
        ("users", "email", "TEXT"),
        ("users", "full_name_ar", "TEXT"),
        ("users", "full_name_en", "TEXT"),
        ("users", "registration_status", "TEXT DEFAULT 'ACTIVE'"),
        ("users", "rejection_reason", "TEXT"),
        ("users", "approved_at", "TEXT"),
        ("users", "last_active_at", "TEXT"),
        ("users", "approved_by", "TEXT"),
        ("verification_codes", "code", "TEXT"),
        ("verification_codes", "attempts", "INTEGER DEFAULT 0"),
        ("verification_codes", "purpose", "TEXT DEFAULT 'auth'"),
        ("saved_reports", "is_deleted", "INTEGER DEFAULT 0"),
        ("saved_reports", "deleted_at", "TEXT"),
        ("saved_reports", "deleted_by", "TEXT"),
        ("saved_reports", "updated_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("saved_reports", "nationality_en", "TEXT"),
        ("saved_reports", "employer_en", "TEXT"),
        ("saved_reports", "practitioner_name_en", "TEXT"),
        ("saved_reports", "job_title_en", "TEXT"),
        ("saved_reports", "hospital_name_en", "TEXT"),
    ]
    for tbl, col, col_type in alter_queries:
        try:
            cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {col_type}")
        except Exception:
            pass

    # Ensure Admin accounts (@RE_i1i and @As1_oi) have admin privileges in DB
    now_iso = datetime.now(timezone.utc).isoformat()
    future_iso = (datetime.now(timezone.utc) + timedelta(days=3650)).isoformat()
    try:
        cur.execute(
            """UPDATE users 
               SET role = 'admin', registration_status = 'ACTIVE', is_active = 1,
                   username = ?, email = ?, telegram_user_id = ?,
                   subscription_end = ?
               WHERE telegram_user_id = ? OR email = ? COLLATE NOCASE OR username = ? COLLATE NOCASE OR id = 10""",
            (ADMIN_USERNAME, ADMIN_EMAIL, ADMIN_TELEGRAM_ID, future_iso, ADMIN_TELEGRAM_ID, ADMIN_EMAIL, ADMIN_USERNAME)
        )
        if cur.rowcount == 0:
            cur.execute(
                """INSERT INTO users (telegram_user_id, username, email, role, registration_status, subscription_start, subscription_end, is_active)
                   VALUES (?, ?, ?, 'admin', 'ACTIVE', ?, ?, 1)""",
                (ADMIN_TELEGRAM_ID, ADMIN_USERNAME, ADMIN_EMAIL, now_iso, future_iso)
            )
        conn.commit()
    except Exception as e:
        logger.warning(f"Admin seeding error: {e}")

    # Seed co-admin @As1_oi
    try:
        cur.execute(
            """UPDATE users 
               SET role = 'admin', registration_status = 'ACTIVE', is_active = 1,
                   subscription_end = ?
               WHERE username = 'As1_oi' COLLATE NOCASE""",
            (future_iso,)
        )
        if cur.rowcount == 0:
            cur.execute(
                """INSERT INTO users (telegram_user_id, username, role, registration_status, subscription_start, subscription_end, is_active)
                   VALUES ('admin_as1_oi', 'As1_oi', 'admin', 'ACTIVE', ?, ?, 1)""",
                (now_iso, future_iso)
            )
        conn.commit()
    except Exception as e:
        logger.warning(f"Co-admin As1_oi seeding error: {e}")

    # Seed past report GSL26102444927 if not present so previous data is visible immediately
    try:
        cur.execute("SELECT service_code FROM saved_reports WHERE service_code = 'GSL26102444927'")
        if not cur.fetchone():
            cur.execute(
                """INSERT OR IGNORE INTO saved_reports (
                    service_code, user_id, telegram_user_id, national_id,
                    patient_name_ar, patient_name_en, nationality, employer,
                    practitioner_name_ar, practitioner_name_en, job_title_ar,
                    hospital_name_ar, hospital_type, report_type,
                    admission_date, discharge_date, leave_duration_days,
                    issue_date, report_time, is_deleted, created_at
                ) VALUES (
                    'GSL26102444927', 1, 'user_admen', '9575523473',
                    'MOHAMMEDFADLALIAQLAN7122', 'متوفر سك ليف الدفع بعد', 'يمني', 'طالب',
                    'محمد بن عبدالرحمن السعدان', 'سك ليف يجي في صحتي', 'طبيب عام',
                    'مستشفى الملك فيصل التخصصي', 'government', 'GSL',
                    '2026-10-24', '2026-10-24', '1',
                    '2026-10-24', '03:57', 0, CURRENT_TIMESTAMP
                )"""
            )
    except Exception as e:
        logger.warning(f"Past report seeding error: {e}")

    conn.commit()
    conn.close()
    logger.info("Database schema initialized and verified successfully at %s", DB_PATH)


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
    tg_id = str(telegram_user_id).strip()
    clean_u = (username or "").lstrip("@").strip()
    cur.execute("SELECT * FROM users WHERE telegram_user_id = ?", (tg_id,))
    row = cur.fetchone()

    if not row:
        is_adm = (tg_id == ADMIN_TELEGRAM_ID) or (clean_u and clean_u.lower() == ADMIN_USERNAME.lower())
        role = "admin" if is_adm else "user"
        reg_status = "ACTIVE" if is_adm else "PENDING_APPROVAL"

        now = datetime.now(timezone.utc)
        sub_end = now + timedelta(days=3650 if is_adm else 30)
        cur.execute(
            """INSERT INTO users (telegram_user_id, username, role, registration_status, subscription_start, subscription_end, is_active)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (tg_id, clean_u, role, reg_status, now.isoformat(), sub_end.isoformat())
        )
        conn.commit()
        user_id = cur.lastrowid
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        log_audit(user_id, "USER_CREATED", f"User {clean_u or tg_id} created (role: {role}, status: {reg_status})")

    conn.close()
    return UserRecord(row)


async def get_or_create_user(session=None, telegram_user_id: str = "0", username: str = None) -> UserRecord:
    return get_or_create_user_sync(telegram_user_id, username)


def get_all_users_sync() -> List[UserRecord]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return [UserRecord(r) for r in rows]


async def get_all_users(session=None) -> List[UserRecord]:
    return get_all_users_sync()


def get_user_by_identifier_sync(identifier: str) -> Optional[UserRecord]:
    conn = _get_conn()
    cur = conn.cursor()
    val = str(identifier).strip().lstrip("@")
    cur.execute(
        """SELECT * FROM users 
           WHERE telegram_user_id = ? OR username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE OR id = ?""",
        (val, val, val, int(val) if val.isdigit() else -1)
    )
    row = cur.fetchone()
    conn.close()
    return UserRecord(row) if row else None


async def get_user_by_identifier(session=None, identifier: str = "") -> Optional[UserRecord]:
    return get_user_by_identifier_sync(identifier)


def create_new_user_sync(username: str, days: int = 30, role: str = "user") -> UserRecord:
    """Directly creates a user with ACTIVE status (for admin usage)."""
    conn = _get_conn()
    cur = conn.cursor()
    clean_u = (username or "").lstrip("@").strip()
    now = datetime.now(timezone.utc)
    sub_end = now + timedelta(days=days)

    cur.execute(
        """INSERT INTO users (telegram_user_id, username, role, registration_status, subscription_start, subscription_end, is_active)
           VALUES (?, ?, ?, 'ACTIVE', ?, ?, 1)""",
        ("0", clean_u, role, now.isoformat(), sub_end.isoformat())
    )
    conn.commit()
    user_id = cur.lastrowid
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    log_audit(user_id, "ADMIN_CREATE_USER", f"Admin created user {clean_u} with {days} days")
    return UserRecord(row)


def register_user_request_sync(
    full_name_ar: str,
    full_name_en: str,
    email: str,
    telegram_user_id: str,
    username: str = None,
) -> UserRecord:
    """Registers a new user request in PENDING_APPROVAL status."""
    conn = _get_conn()
    cur = conn.cursor()

    clean_email = str(email).strip().lower()
    clean_tg_id = str(telegram_user_id).strip()
    clean_u = (username or "").lstrip("@").strip()
    clean_ar = str(full_name_ar).strip()
    clean_en = str(full_name_en).strip()

    # Check if already exists
    cur.execute(
        "SELECT * FROM users WHERE telegram_user_id = ? OR email = ? COLLATE NOCASE",
        (clean_tg_id, clean_email)
    )
    existing = cur.fetchone()

    now = datetime.now(timezone.utc)
    sub_end = now + timedelta(days=30)

    # Check if this is the admin account
    is_admin = (
        clean_tg_id == ADMIN_TELEGRAM_ID
        or clean_email == ADMIN_EMAIL.lower()
        or (clean_u and clean_u.lower() == ADMIN_USERNAME.lower())
    )

    if existing:
        user_id = existing["id"]
        new_status = "ACTIVE" if is_admin else "PENDING_APPROVAL"
        new_role = "admin" if is_admin else existing["role"]
        cur.execute(
            """UPDATE users 
               SET full_name_ar = ?, full_name_en = ?, email = ?, username = ?, 
                   role = ?, registration_status = ?, rejection_reason = NULL,
                   updated_at = CURRENT_TIMESTAMP
               WHERE id = ?""",
            (clean_ar, clean_en, clean_email, clean_u, new_role, new_status, user_id)
        )
        conn.commit()
        log_audit(user_id, "REGISTRATION_RESUBMITTED", f"Registration resubmitted by {clean_ar}")
    else:
        new_status = "ACTIVE" if is_admin else "PENDING_APPROVAL"
        new_role = "admin" if is_admin else "user"
        cur.execute(
            """INSERT INTO users (
                telegram_user_id, username, full_name_ar, full_name_en, email,
                role, registration_status, subscription_start, subscription_end, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (clean_tg_id, clean_u, clean_ar, clean_en, clean_email, new_role, new_status, now.isoformat(), sub_end.isoformat())
        )
        conn.commit()
        user_id = cur.lastrowid
        log_audit(user_id, "REGISTRATION_SUBMITTED", f"New registration request by {clean_ar} ({clean_email})")

    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return UserRecord(row)


def approve_user_registration_sync(user_id: int, admin_id: str = "admin") -> tuple[UserRecord, str]:
    """Admin approves registration: status becomes APPROVED, generates 30s OTP code."""
    conn = _get_conn()
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).isoformat()

    cur.execute(
        """UPDATE users 
           SET registration_status = 'APPROVED', approved_at = ?, approved_by = ?,
               is_active = 1, rejection_reason = NULL, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (now_iso, str(admin_id), user_id)
    )
    conn.commit()
    conn.close()

    # Generate 30-second verification code for the user
    otp_code = create_verification_code_sync(user_id, purpose="registration")
    log_audit(user_id, "REGISTRATION_APPROVED", f"Approved by {admin_id}. 30s OTP generated.")

    user = get_user_by_identifier_sync(str(user_id))
    return user, otp_code


def reject_user_registration_sync(user_id: int, reason: str = "", admin_id: str = "admin") -> UserRecord:
    """Admin rejects registration."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE users 
           SET registration_status = 'REJECTED', rejection_reason = ?, approved_by = ?,
               is_active = 0, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (str(reason).strip() or "لم يتم استيفاء شروط التسجيل", str(admin_id), user_id)
    )
    conn.commit()
    conn.close()

    log_audit(user_id, "REGISTRATION_REJECTED", f"Rejected by {admin_id}. Reason: {reason}")
    return get_user_by_identifier_sync(str(user_id))


def suspend_user_sync(user_id: int, admin_id: str = "admin") -> UserRecord:
    """Suspends a user account."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE users 
           SET registration_status = 'SUSPENDED', is_active = 0, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (user_id,)
    )
    conn.commit()
    conn.close()
    log_audit(user_id, "USER_SUSPENDED", f"User suspended by {admin_id}")
    return get_user_by_identifier_sync(str(user_id))


def activate_user_sync(user_id: int, admin_id: str = "admin") -> UserRecord:
    """Reactivates a user account."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """UPDATE users 
           SET registration_status = 'ACTIVE', is_active = 1, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (user_id,)
    )
    conn.commit()
    conn.close()
    log_audit(user_id, "USER_ACTIVATED", f"User activated by {admin_id}")
    return get_user_by_identifier_sync(str(user_id))


def get_pending_registrations_sync() -> list[dict]:
    """Return all users waiting for approval."""
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE registration_status = 'PENDING_APPROVAL' ORDER BY created_at DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Subscription Management ───────────────────────────────────────────────────
def check_subscription_sync(user_id: int = 0) -> Dict[str, Any]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"active": False, "days_remaining": 0, "message": "المستخدم غير موجود", "status": "NOT_FOUND"}

    user = UserRecord(row)
    if not user.is_active or user.registration_status in ("SUSPENDED", "REJECTED"):
        return {
            "active": False,
            "days_remaining": 0,
            "message": f"الحساب غير مفعل ({user.registration_status})",
            "status": user.registration_status
        }

    if user.registration_status == "PENDING_APPROVAL":
        return {
            "active": False,
            "days_remaining": 0,
            "message": "طلب التسجيل قيد المراجعة من الإدارة",
            "status": "PENDING_APPROVAL"
        }

    if user.registration_status == "APPROVED":
        return {
            "active": False,
            "days_remaining": 0,
            "message": "تم قبول الطلب، يرجى إدخال رمز التحقق (30 ثانية)",
            "status": "APPROVED"
        }

    if not user.subscription_end:
        return {"active": False, "days_remaining": 0, "message": "لا يوجد اشتراك", "status": "NO_SUBSCRIPTION"}

    now = datetime.now(timezone.utc)
    sub_end = user.subscription_end
    if sub_end.tzinfo is None:
        sub_end = sub_end.replace(tzinfo=timezone.utc)

    diff = sub_end - now
    total_sec = diff.total_seconds()

    if total_sec <= 0:
        return {"active": False, "days_remaining": 0, "message": "انتهى الاشتراك (30 يوماً)", "status": "EXPIRED"}

    days_remaining = max(1, int(math.ceil(total_sec / 86400)))
    message = f"متبقي على انتهاء الاشتراك {days_remaining} يوم"
    return {"active": True, "days_remaining": days_remaining, "message": message, "status": "ACTIVE"}


async def check_subscription(session=None, user_id: int = 0) -> Dict[str, Any]:
    return check_subscription_sync(user_id)


def renew_subscription_sync(user_id: int = 0, days: int = 30) -> UserRecord:
    # Strictly 30 days per renewal
    days = 30
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise ValueError("User not found")

    user = UserRecord(row)
    now = datetime.now(timezone.utc)

    # Idempotency guard: prevent duplicate extensions from rapid double-clicks (within 5 seconds)
    if user.updated_at:
        try:
            up_dt = datetime.fromisoformat(user.updated_at)
            if up_dt.tzinfo is None:
                up_dt = up_dt.replace(tzinfo=timezone.utc)
            if abs((now - up_dt).total_seconds()) < 5.0 and user.subscription_end and user.subscription_end > now:
                logger.info(f"Ignoring duplicate renewal click for user {user_id} (idempotency guard)")
                conn.close()
                return user
        except Exception:
            pass

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
           SET subscription_start = ?, subscription_end = ?, is_active = 1,
               registration_status = 'ACTIVE', updated_at = CURRENT_TIMESTAMP
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


# ── Verification Codes (Strictly 30s expiry) ──────────────────────────────────
def create_verification_code_sync(user_id: int = 0, purpose: str = "auth") -> str:
    """Generates a secure 5-digit OTP with exactly 30-second server TTL."""
    # Invalidate previous unused codes for this user
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE verification_codes SET used = 1 WHERE user_id = ? AND used = 0",
        (user_id,)
    )

    code = f"{random.randint(10000, 99999)}"
    code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)

    cur.execute(
        """INSERT INTO verification_codes (user_id, code_hash, code, expires_at, used, attempts, purpose)
           VALUES (?, ?, ?, ?, 0, 0, ?)""",
        (user_id, code_hash, code, expires_at.isoformat(), purpose)
    )
    conn.commit()
    conn.close()

    log_audit(user_id, "CODE_REQUESTED", f"Verification code generated (30s expiry, purpose: {purpose})")
    return code


async def create_verification_code(session=None, user_id: int = 0, purpose: str = "auth") -> str:
    return create_verification_code_sync(user_id, purpose)


def verify_code_sync(user_id: int = 0, code: str = "", purpose: str = None) -> bool:
    """Verifies a 5-digit code within the exact 30-second window."""
    code_hash = hashlib.sha256(str(code).strip().encode("utf-8")).hexdigest()

    conn = _get_conn()
    cur = conn.cursor()

    if purpose:
        cur.execute(
            """SELECT id, expires_at, attempts FROM verification_codes 
               WHERE user_id = ? AND code_hash = ? AND used = 0 AND purpose = ?
               ORDER BY id DESC LIMIT 1""",
            (user_id, code_hash, purpose)
        )
    else:
        cur.execute(
            """SELECT id, expires_at, attempts FROM verification_codes 
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
    attempts = row["attempts"] + 1

    # Check brute force threshold (max 5 attempts)
    if attempts > 5:
        cur.execute("UPDATE verification_codes SET used = 1 WHERE id = ?", (code_id,))
        conn.commit()
        conn.close()
        log_audit(user_id, "CODE_BLOCKED", "Too many failed attempts for code")
        return False

    cur.execute("UPDATE verification_codes SET attempts = ? WHERE id = ?", (attempts, code_id))
    conn.commit()

    exp_dt = datetime.fromisoformat(row["expires_at"])
    if exp_dt.tzinfo is None:
        exp_dt = exp_dt.replace(tzinfo=timezone.utc)

    # Server-side 30-second TTL check
    if datetime.now(timezone.utc) > exp_dt:
        cur.execute("UPDATE verification_codes SET used = 1 WHERE id = ?", (code_id,))
        conn.commit()
        conn.close()
        log_audit(user_id, "CODE_EXPIRED", f"Verification code expired (exceeded {OTP_TTL_SECONDS} seconds)")
        return False

    # Valid! Mark code as used
    cur.execute("UPDATE verification_codes SET used = 1 WHERE id = ?", (code_id,))
    conn.commit()
    conn.close()

    log_audit(user_id, "CODE_VERIFIED", "Verification code verified successfully within 30s")
    return True


async def verify_code(session=None, user_id: int = 0, code: str = "", purpose: str = None) -> bool:
    return verify_code_sync(user_id, code, purpose)


def get_latest_code_for_user_sync(user_id: int) -> Optional[Dict[str, Any]]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, code, expires_at, used, created_at, purpose 
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


# ── Saved Reports Management (Active & Soft-Deleted) ──────────────────────────
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
            leave_duration_days, issue_date, report_time, data_json,
            is_deleted, created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )""",
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
            json.dumps(data, ensure_ascii=False),
        )
    )
    conn.commit()
    conn.close()
    log_audit(int(data.get("user_id") or 0), "REPORT_CREATED", f"Report {sc} created for {data.get('patient_name_ar')}")


def update_saved_report_sync(service_code: str, data: dict, user_id: int = 0) -> bool:
    """Updates an existing report in place."""
    import json
    conn = _get_conn()
    cur = conn.cursor()
    sc = str(service_code).strip()

    cur.execute(
        """UPDATE saved_reports 
           SET national_id = ?, patient_name_ar = ?, patient_name_en = ?,
               nationality = ?, nationality_en = ?, employer = ?, employer_en = ?,
               practitioner_name_ar = ?, practitioner_name_en = ?,
               job_title_ar = ?, job_title_en = ?, hospital_name_ar = ?,
               hospital_name_en = ?, hospital_type = ?, report_type = ?,
               admission_date = ?, discharge_date = ?, leave_duration_days = ?,
               issue_date = ?, report_time = ?, data_json = ?,
               updated_at = CURRENT_TIMESTAMP
           WHERE service_code = ?""",
        (
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
            json.dumps(data, ensure_ascii=False),
            sc,
        )
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()

    if updated:
        log_audit(user_id, "REPORT_UPDATED", f"Report {sc} updated by user {user_id}")
    return updated


def soft_delete_report_sync(service_code: str, user_id: int = 0, is_admin: bool = False) -> bool:
    """Moves report to trash (is_deleted = 1)."""
    conn = _get_conn()
    cur = conn.cursor()
    sc = str(service_code).strip()
    now_iso = datetime.now(timezone.utc).isoformat()

    query = """UPDATE saved_reports 
               SET is_deleted = 1, deleted_at = ?, deleted_by = ?, updated_at = CURRENT_TIMESTAMP
               WHERE service_code = ?"""
    params = [now_iso, str(user_id), sc]
    if user_id and not is_admin:
        query += " AND user_id = ?"
        params.append(user_id)

    cur.execute(query, tuple(params))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()

    if ok:
        log_audit(user_id, "REPORT_SOFT_DELETED", f"Report {sc} moved to trash by user {user_id}")
    return ok


def restore_report_sync(service_code: str, user_id: int = 0, is_admin: bool = False) -> bool:
    """Restores report from trash (is_deleted = 0)."""
    conn = _get_conn()
    cur = conn.cursor()
    sc = str(service_code).strip()

    query = """UPDATE saved_reports 
               SET is_deleted = 0, deleted_at = NULL, deleted_by = NULL, updated_at = CURRENT_TIMESTAMP
               WHERE service_code = ?"""
    params = [sc]
    if user_id and not is_admin:
        query += " AND user_id = ?"
        params.append(user_id)

    cur.execute(query, tuple(params))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()

    if ok:
        log_audit(user_id, "REPORT_RESTORED", f"Report {sc} restored by user {user_id}")
    return ok


def permanent_delete_report_sync(service_code: str, user_id: int = 0) -> bool:
    """Permanently deletes a report from database."""
    conn = _get_conn()
    cur = conn.cursor()
    sc = str(service_code).strip()

    cur.execute("DELETE FROM saved_reports WHERE service_code = ?", (sc,))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()

    if ok:
        log_audit(user_id, "REPORT_PERMANENTLY_DELETED", f"Report {sc} permanently deleted by {user_id}")
    return ok


def get_all_saved_reports_sync(user_id: Optional[int] = None, telegram_user_id: Optional[str] = None, is_admin: bool = False) -> list[dict]:
    """Returns active (non-deleted) reports. Admin sees all."""
    conn = _get_conn()
    cur = conn.cursor()
    if is_admin:
        cur.execute("SELECT * FROM saved_reports WHERE is_deleted = 0 ORDER BY created_at DESC")
    elif user_id:
        cur.execute("SELECT * FROM saved_reports WHERE user_id = ? AND is_deleted = 0 ORDER BY created_at DESC", (user_id,))
    elif telegram_user_id and telegram_user_id != "0":
        cur.execute("SELECT * FROM saved_reports WHERE telegram_user_id = ? AND is_deleted = 0 ORDER BY created_at DESC", (str(telegram_user_id),))
    else:
        cur.execute("SELECT * FROM saved_reports WHERE is_deleted = 0 ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]




def record_user_activity_sync(user_id: Optional[int] = None, telegram_user_id: Optional[str] = None) -> None:
    """Updates last_active_at timestamp for active tracking."""
    if not user_id and not telegram_user_id:
        return
    try:
        conn = _get_conn()
        cur = conn.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()
        if user_id:
            cur.execute("UPDATE users SET last_active_at = ? WHERE id = ?", (now_iso, user_id))
        elif telegram_user_id and str(telegram_user_id) != "0":
            cur.execute("UPDATE users SET last_active_at = ? WHERE telegram_user_id = ?", (now_iso, str(telegram_user_id)))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"Error recording user activity: {e}")


def get_currently_active_users_sync(minutes: int = ACTIVE_USER_MINUTES) -> list[dict]:
    """Returns users active within the given minutes threshold."""
    conn = _get_conn()
    cur = conn.cursor()
    threshold_iso = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    cur.execute(
        """SELECT id, telegram_user_id, username, full_name_ar, full_name_en, 
                  email, role, registration_status, last_active_at, subscription_end
           FROM users 
           WHERE last_active_at IS NOT NULL AND last_active_at >= ?
           ORDER BY last_active_at DESC""",
        (threshold_iso,)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_trash_reports_sync(user_id: Optional[int] = None, is_admin: bool = False) -> list[dict]:
    """Returns soft-deleted reports from trash bin."""
    conn = _get_conn()
    cur = conn.cursor()
    if is_admin:
        cur.execute("SELECT * FROM saved_reports WHERE is_deleted = 1 ORDER BY deleted_at DESC")
    elif user_id:
        cur.execute("SELECT * FROM saved_reports WHERE user_id = ? AND is_deleted = 1 ORDER BY deleted_at DESC", (user_id,))
    else:
        cur.execute("SELECT * FROM saved_reports WHERE is_deleted = 1 ORDER BY deleted_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_single_saved_report_sync(service_code: str, include_deleted: bool = False) -> Optional[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    sc = str(service_code).strip()
    if include_deleted:
        cur.execute("SELECT * FROM saved_reports WHERE service_code = ?", (sc,))
    else:
        cur.execute("SELECT * FROM saved_reports WHERE service_code = ? AND is_deleted = 0", (sc,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


# ── Audit & System Summary ───────────────────────────────────────────────────
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


def get_audit_logs_sync(limit: int = 50) -> list[dict]:
    conn = _get_conn()
    cur = conn.cursor()
    cur.execute(
        """SELECT a.*, u.username, u.full_name_ar 
           FROM audit_logs a 
           LEFT JOIN users u ON a.user_id = u.id 
           ORDER BY a.id DESC LIMIT ?""",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_system_stats_sync() -> dict:
    """Returns system metrics for Admin Overview."""
    conn = _get_conn()
    cur = conn.cursor()

    cur.execute("SELECT count(*) FROM users")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM users WHERE registration_status = 'PENDING_APPROVAL'")
    pending_regs = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM users WHERE registration_status = 'APPROVED'")
    approved_users = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM users WHERE registration_status = 'REJECTED'")
    rejected_users = cur.fetchone()[0]

    cur.execute(
        "SELECT count(*) FROM users WHERE is_active = 1 AND registration_status = 'ACTIVE'"
        " AND subscription_end IS NOT NULL AND subscription_end > datetime('now')"
    )
    active_users = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM users WHERE is_active = 0 OR registration_status = 'SUSPENDED'")
    suspended_users = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM saved_reports WHERE is_deleted = 0")
    total_reports = cur.fetchone()[0]

    cur.execute("SELECT count(*) FROM saved_reports WHERE is_deleted = 1")
    deleted_reports = cur.fetchone()[0]

    threshold_iso = (datetime.now(timezone.utc) - timedelta(minutes=ACTIVE_USER_MINUTES)).isoformat()
    cur.execute("SELECT count(*) FROM users WHERE last_active_at IS NOT NULL AND last_active_at >= ?", (threshold_iso,))
    active_now_users = cur.fetchone()[0]

    conn.close()

    return {
        "total_users": total_users,
        "pending_registrations": pending_regs,
        "approved_users": approved_users,
        "rejected_users": rejected_users,
        "active_users": active_users,
        "active_now_users": active_now_users,
        "suspended_users": suspended_users,
        "total_reports": total_reports,
        "deleted_reports": deleted_reports,
    }


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
