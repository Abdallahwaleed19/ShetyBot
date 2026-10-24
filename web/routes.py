"""
web/routes.py — API + HTML routes
"""
import os
import sys
import asyncio
import logging
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Request, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db.worker_client import (
    create_report,
    get_report,
    search_by_national_id,
    upload_logo,
)
from db.database import (
    get_session,
    get_or_create_user,
    get_all_users,
    get_all_users_sync,
    check_subscription,
    check_subscription_sync,
    renew_subscription,
    renew_subscription_sync,
    create_verification_code,
    create_verification_code_sync,
    verify_code,
    verify_code_sync,
    get_user_reports,
    verify_report_ownership,
    record_report_ownership,
    get_user_by_identifier_sync,
    create_new_user_sync,
    register_user_request_sync,
    approve_user_registration_sync,
    reject_user_registration_sync,
    suspend_user_sync,
    activate_user_sync,
    get_pending_registrations_sync,
    get_system_stats_sync,
    get_audit_logs_sync,
    get_latest_code_for_user_sync,
    save_report_full_sync,
    get_all_saved_reports_sync,
    get_trash_reports_sync,
    get_single_saved_report_sync,
    soft_delete_report_sync,
    restore_report_sync,
    permanent_delete_report_sync,
    update_saved_report_sync,
    log_audit,
    ADMIN_TELEGRAM_ID,
    ADMIN_EMAIL,
    ADMIN_USERNAME,
    OTP_TTL_SECONDS,
)
import hashlib
from db.models import User
from config import BASE_DIR, UPLOADS_DIR, REPORTS_DIR
from web.form_logic import inclusive_duration
from services.email_service import (
    send_admin_new_registration_notification,
    send_user_otp_email,
)

router    = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))


# ── Dependency: Get current user (Token / Username / Telegram) ───────────────
def _make_token(user_id: int) -> str:
    salt = "sehty_salt_99"
    sig = hashlib.sha256(f"{user_id}:{salt}".encode()).hexdigest()[:16]
    return f"{user_id}:{sig}"


def _verify_token(token: str) -> Optional[int]:
    try:
        parts = str(token).split(":")
        if len(parts) != 2:
            return None
        uid = int(parts[0])
        salt = "sehty_salt_99"
        expected = hashlib.sha256(f"{uid}:{salt}".encode()).hexdigest()[:16]
        if parts[1] == expected:
            return uid
    except Exception:
        pass
    return None


def is_admin_request(user: Optional[User], request: Request) -> bool:
    """Check if the current request is authenticated as admin."""
    admin_key = request.query_params.get("key") or request.headers.get("x-admin-key")
    configured_key = os.getenv("ADMIN_KEY", "admin123").strip()
    if admin_key and admin_key.strip() == configured_key:
        return True
    if not user:
        return False
    if getattr(user, "role", None) == "admin":
        return True
    tg_id = str(getattr(user, "telegram_user_id", "")).strip()
    if tg_id and tg_id == ADMIN_TELEGRAM_ID:
        return True
    un = str(getattr(user, "username", "")).lstrip("@").strip().lower()
    if un and un == ADMIN_USERNAME.lower():
        return True
    return False


async def send_telegram_message_safe(chat_id: str, html_text: str):
    """Safely deliver a Telegram message without raising exceptions."""
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token or not chat_id or str(chat_id) in ("0", "-1"):
        return
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": str(chat_id), "text": html_text, "parse_mode": "HTML"}
            )
    except Exception as e:
        logger.warning(f"Telegram notification to {chat_id} failed: {e}")


async def get_current_user(request: Request) -> User:
    """Get current user from auth token header/query, username query, or Telegram WebApp"""
    # 1. Try token from header or query
    token = request.headers.get("x-auth-token") or request.query_params.get("token")
    if not token and request.headers.get("authorization", "").startswith("Bearer "):
        token = request.headers.get("authorization")[7:].strip()

    if token:
        uid = _verify_token(token)
        if uid:
            u_rec = get_user_by_identifier_sync(str(uid))
            if u_rec:
                return User(
                    id=u_rec.id,
                    telegram_user_id=u_rec.telegram_user_id,
                    username=u_rec.username,
                    role=u_rec.role,
                    subscription_start=u_rec.subscription_start,
                    subscription_end=u_rec.subscription_end,
                    is_active=u_rec.is_active,
                )

    # 2. Try username from header or query
    username = (
        request.headers.get("x-username")
        or request.query_params.get("u")
        or request.query_params.get("username")
    )
    if username:
        u_rec = get_user_by_identifier_sync(username)
        if u_rec:
            return User(
                id=u_rec.id,
                telegram_user_id=u_rec.telegram_user_id,
                username=u_rec.username,
                role=u_rec.role,
                subscription_start=u_rec.subscription_start,
                subscription_end=u_rec.subscription_end,
                is_active=u_rec.is_active,
            )

    # 3. Fallback to Telegram WebApp user
    telegram_user_id = request.query_params.get("telegram_user_id") or "0"
    u_rec = get_user_by_identifier_sync(telegram_user_id)
    if u_rec:
        return User(
            id=u_rec.id,
            telegram_user_id=u_rec.telegram_user_id,
            username=u_rec.username,
            role=u_rec.role,
            subscription_start=u_rec.subscription_start,
            subscription_end=u_rec.subscription_end,
            is_active=u_rec.is_active,
        )

    # 4. Fallback to admin if matching
    if str(telegram_user_id).strip() == ADMIN_TELEGRAM_ID:
        u_rec = get_user_by_identifier_sync(ADMIN_TELEGRAM_ID)
        if u_rec:
            return User(
                id=u_rec.id,
                telegram_user_id=u_rec.telegram_user_id,
                username=u_rec.username,
                role=u_rec.role,
                subscription_start=u_rec.subscription_start,
                subscription_end=u_rec.subscription_end,
                is_active=u_rec.is_active,
            )

    # Default fallback user
    return User(
        id=0,
        telegram_user_id=str(telegram_user_id),
        username="guest",
        role="guest",
        subscription_start=None,
        subscription_end=None,
        is_active=False,
    )


# ── WebApp Form ────────────────────────────────────────────────────────────────
@router.get("/form", response_class=HTMLResponse, summary="Telegram WebApp 3-page form")
async def form_page(request: Request):
    return templates.TemplateResponse(request, "form.html", {})


# ── Submit Report API ──────────────────────────────────────────────────────────
@router.post("/api/submit-report", summary="Receive form data, save via Worker, generate PDF")
async def submit_report(
    current_user: User = Depends(get_current_user),
    # Page 1
    service_code:         str = Form(...),
    report_type:          str = Form("GSL"),
    admission_date:       str = Form(...),
    discharge_date:       str = Form(...),
    leave_duration_days:  str = Form("1"),
    issue_date:           str = Form(""),
    report_time:          str = Form(""),
    include_barcode:      str = Form("0"),
    # Page 2
    national_id:          str = Form(...),
    patient_name_ar:      str = Form(...),
    patient_name_en:      str = Form(""),
    nationality:          str = Form(""),
    nationality_en:       str = Form(""),
    employer:             str = Form(""),
    employer_en:          str = Form(""),
    # Page 3
    practitioner_name_ar: str = Form(""),
    practitioner_name_en: str = Form(""),
    job_title_ar:         str = Form(""),
    job_title_en:         str = Form(""),
    hospital_name_ar:     str = Form(""),
    hospital_name_en:     str = Form(""),
    hospital_type:        str = Form("government"),
    logo: Optional[UploadFile] = File(None),
):
    try:
        # Check subscription for non-admin users
        if current_user.role != "admin" and str(current_user.telegram_user_id) != ADMIN_TELEGRAM_ID:
            if current_user.id > 0:
                sub_status = check_subscription_sync(current_user.id)
                if not sub_status["active"]:
                    return JSONResponse({
                        "success": False,
                        "error": sub_status["message"],
                        "subscription_expired": True
                    })

        # Arabia Standard Time (UTC+3) for fallback timestamps
        now_dt = datetime.now(timezone(timedelta(hours=3)))

        # Parse helper
        def pd(s):
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try:
                    return datetime.strptime(s.strip(), fmt).date()
                except Exception:
                    pass
            return None

        adm = pd(admission_date)
        dis = pd(discharge_date)
        if not adm or not dis:
            return JSONResponse({"success": False, "error": "تاريخ غير صحيح"})
        if dis < adm:
            return JSONResponse({"success": False, "error": "تاريخ الخروج يجب ألا يسبق تاريخ الدخول"})
        if report_type not in {"GSL", "PSL"}:
            return JSONResponse({"success": False, "error": "نوع التقرير غير صالح"})

        # Issue date: use form value if valid, else server date
        iss = pd(issue_date) if issue_date.strip() else None
        if not iss:
            iss = now_dt.date()

        # Issue time: use form value if valid (HH:MM), else server time
        rt = None
        if report_time.strip():
            try:
                rt_parsed = datetime.strptime(report_time.strip(), "%H:%M")
                rt = rt_parsed.time()
            except Exception:
                pass
        if rt is None:
            rt = now_dt.time().replace(second=0, microsecond=0)

        # Leave duration
        dur = inclusive_duration(adm, dis)
        with_barcode = (include_barcode.strip() == "1")

        # Upload logo to R2
        logo_url = None
        logo_local_path = None
        if logo and logo.filename:
            ext         = Path(logo.filename).suffix or ".jpg"
            unique_name = f"logo_{service_code}{ext}"
            file_bytes  = await logo.read()

            local_path = UPLOADS_DIR / unique_name
            local_path.write_bytes(file_bytes)
            logo_local_path = str(local_path)

            content_type = logo.content_type or "image/jpeg"
            try:
                logo_url = await upload_logo(unique_name, file_bytes, content_type)
            except Exception:
                logo_url = None

        # Hijri conversion helper
        def _hijri(d):
            try:
                from hijri_converter import convert
                h = convert.Gregorian(d.year, d.month, d.day).to_hijri()
                return f"{h.day:02d}-{h.month:02d}-{h.year}"
            except Exception:
                return str(d)

        def _fmt(d):
            return d.strftime("%d-%m-%Y") if d else ""

        # Build PDF data dict
        pdf_data = {
            "leave_id":                  service_code,
            "national_id":               national_id,
            "patient_name_ar":           patient_name_ar,
            "patient_name_en":           patient_name_en,
            "nationality":               nationality,
            "nationality_en":            nationality_en,
            "employer":                  employer,
            "employer_en":               employer_en,
            "report_type":               report_type,
            "admission_date_gregorian":  _fmt(adm),
            "admission_date_hijri":      _hijri(adm),
            "discharge_date_gregorian":  _fmt(dis),
            "discharge_date_hijri":      _hijri(dis),
            "leave_duration_days":       dur,
            "issue_date_gregorian":      _fmt(iss),
            "issue_date_hijri":          _hijri(iss),
            "issue_date_long":           f"{iss.strftime('%A')} ,{iss.day} {iss.strftime('%B %Y')}",
            "issue_time":                rt.strftime("%I:%M %p").lstrip("0"),
            "practitioner_name_ar":      practitioner_name_ar,
            "practitioner_name_en":      practitioner_name_en,
            "practitioner_position_ar":  job_title_ar,
            "practitioner_position_en":  job_title_en,
            "hospital_name_ar":          hospital_name_ar,
            "hospital_name_en":          hospital_name_en,
            "hospital_type":             hospital_type,
            "hospital_logo_path":        logo_local_path,
            "include_barcode":           with_barcode,
        }

        # Generate PDF
        from pdf.generator import generate_pdf
        pdf_path = REPORTS_DIR / f"{service_code}.pdf"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, generate_pdf, pdf_data, pdf_path)

        # Track ownership in database for data isolation
        try:
            async for s in get_session():
                await record_report_ownership(s, service_code, current_user.id, current_user.telegram_user_id)
        except Exception:
            pass

        # Save to Cloudflare Worker (D1) and local SQLite
        report_data = {
            "service_code":         service_code,
            "report_type":          report_type,
            "admission_date":       str(adm),
            "discharge_date":       str(dis),
            "leave_duration_days":  dur,
            "issue_date":           str(iss),
            "report_time":          rt.strftime("%H:%M"),
            "national_id":          national_id,
            "patient_name_ar":      patient_name_ar,
            "patient_name_en":      patient_name_en,
            "nationality":          nationality,
            "nationality_en":       nationality_en,
            "employer":             employer,
            "employer_en":          employer_en,
            "practitioner_name_ar": practitioner_name_ar,
            "practitioner_name_en": practitioner_name_en,
            "job_title_ar":         job_title_ar,
            "job_title_en":         job_title_en,
            "hospital_name_ar":     hospital_name_ar,
            "hospital_name_en":     hospital_name_en,
            "hospital_type":        hospital_type,
            "logo_url":             logo_url or "",
            "telegram_user_id":     current_user.telegram_user_id,
            "user_id":              current_user.id,
        }

        # Save to local SQLite database for instant retrieval in Records page
        try:
            save_report_full_sync(report_data)
        except Exception as e:
            logger.warning(f"Failed to save locally: {e}")

        worker_result = await create_report(report_data)
        if not worker_result.get("success"):
            logger.warning("Worker save skipped/failed: %s", worker_result.get("error"))

        log_audit(current_user.id, "REPORT_CREATED", f"Created report {service_code} for {patient_name_ar}")
        return JSONResponse({"success": True, "service_code": service_code})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)})


# ── Verification pages ─────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "verify.html",
        {"record": None, "error": None, "query": ""},
    )


@router.get("/verify",    response_class=HTMLResponse)
@router.get("/inquiries", response_class=HTMLResponse)
async def verify_page(request: Request, q: Optional[str] = Query(None)):
    record = None
    error  = None
    if q:
        record = await get_report(q)
        if not record:
            results = await search_by_national_id(q)
            record  = results[0] if results else None
        if not record:
            error = f"لم يتم العثور على سجل لـ: {q}"
    return templates.TemplateResponse(
        request,
        "verify.html",
        {"record": record, "error": error, "query": q or ""},
    )


@router.get("/api/verify")
async def api_verify(q: str = Query(...)):
    # Check local SQLite first for speed and offline reliability
    local_rec = get_single_saved_report_sync(q)
    if local_rec:
        return local_rec

    record = await get_report(q)
    if not record:
        results = await search_by_national_id(q)
        record  = results[0] if results else None
    if not record:
        raise HTTPException(404, f"No record found for: {q}")
    return record


@router.get("/api/my-reports")
async def my_reports(telegram_user_id: str = Query(...)):
    """Get reports by telegram_user_id (latest first)."""
    from db.worker_client import get_client
    client = await get_client()
    try:
        resp = await client.get("/api/reports", params={"telegram_user_id": telegram_user_id})
        if resp.status_code == 200:
            return resp.json()
        return {"data": []}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/api/download/{service_code}")
async def download_pdf(service_code: str):
    """Download PDF directly for the report creator"""
    pdf = REPORTS_DIR / f"{service_code}.pdf"
    if not pdf.exists():
        # Attempt to regenerate if data is available
        rec = get_single_saved_report_sync(service_code)
        if rec:
            try:
                from pdf.generator import generate_pdf
                generate_pdf(rec, pdf)
            except Exception as e:
                logger.error(f"Failed to regenerate PDF: {e}")

    if not pdf.exists():
        raise HTTPException(404, "PDF not found")

    return FileResponse(
        str(pdf),
        media_type="application/pdf",
        filename=f"SickLeave_{service_code}.pdf",
    )


# ── Auth & Registration APIs ──────────────────────────────────────────────────

@router.post("/api/auth/register")
async def api_register_user(
    full_name_ar:     str = Form(...),
    full_name_en:     str = Form(""),
    email:            str = Form(...),
    telegram_user_id: str = Form("0"),
    username:         str = Form(""),
):
    """
    Submits user registration request:
    1. Saves user with PENDING_APPROVAL status.
    2. Sends immediate email notification to Admin (ramo.711.vip@gmail.com).
    3. Sends Telegram message notification to Admin bot chat.
    """
    clean_ar = full_name_ar.strip()
    clean_en = full_name_en.strip()
    clean_email = email.strip().lower()
    clean_tg = str(telegram_user_id).strip()
    clean_u = username.lstrip("@").strip()

    if not clean_ar or not clean_email:
        return JSONResponse({"success": False, "error": "الاسم الكامل والبريد الإلكتروني مطلوبان"})

    try:
        user_rec = register_user_request_sync(
            full_name_ar=clean_ar,
            full_name_en=clean_en,
            email=clean_email,
            telegram_user_id=clean_tg,
            username=clean_u,
        )

        user_dict = {
            "id": user_rec.id,
            "full_name_ar": user_rec.full_name_ar,
            "full_name_en": user_rec.full_name_en,
            "email": user_rec.email,
            "telegram_user_id": user_rec.telegram_user_id,
            "username": user_rec.username,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        }

        # 1. Send Email Notification to Admin
        asyncio.create_task(
            asyncio.to_thread(send_admin_new_registration_notification, user_dict)
        )

        # 2. Send Telegram Notification to Admin
        admin_tg_msg = (
            f"🔔 <b>طلب تسجيل جديد ينتظر الموافقة</b>\n\n"
            f"👤 <b>الاسم بالعربي:</b> {clean_ar}\n"
            f"🔤 <b>الاسم بالإنجليزي:</b> {clean_en or '-'}\n"
            f"📧 <b>البريد:</b> <code>{clean_email}</code>\n"
            f"🆔 <b>Telegram ID:</b> <code>{clean_tg}</code>\n"
            f"🏷️ <b>Username:</b> @{clean_u or 'بدون'}\n\n"
            f"⚙️ للموافقة أو الرفض، افتح لوحة الأدمن: <code>/admin</code>"
        )
        asyncio.create_task(send_telegram_message_safe(ADMIN_TELEGRAM_ID, admin_tg_msg))

        return JSONResponse({
            "success": True,
            "user_id": user_rec.id,
            "status": "PENDING_APPROVAL",
            "message": "تم إرسال طلب التسجيل بنجاح! طلبك قيد مراجعة الإدارة وسوف يتم إشعارك فور الموافقة."
        })

    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        return JSONResponse({"success": False, "error": f"حدث خطأ أثناء التسجيل: {str(e)}"})


@router.get("/api/auth/status")
async def api_auth_status(
    telegram_user_id: Optional[str] = Query(None),
    username:         Optional[str] = Query(None),
    token:            Optional[str] = Query(None),
):
    """
    Checks user registration & subscription status.
    """
    clean_tg = str(telegram_user_id or "").strip()
    clean_un = str(username or "").lstrip("@").strip().lower()

    # Immediate Admin Check by incoming params
    if clean_tg == ADMIN_TELEGRAM_ID or clean_un == ADMIN_USERNAME.lower():
        return JSONResponse({
            "success": True,
            "registered": True,
            "user_id": 1,
            "username": ADMIN_USERNAME,
            "email": ADMIN_EMAIL,
            "full_name_ar": "مدير النظام",
            "status": "ACTIVE",
            "is_admin": True,
            "active": True,
            "days_remaining": 3650,
            "message": "حساب الأدمن الرئيسي نشط بصلاحيات كاملة",
        })

    user_rec = None
    if token:
        uid = _verify_token(token)
        if uid:
            user_rec = get_user_by_identifier_sync(str(uid))

    if not user_rec and clean_un:
        user_rec = get_user_by_identifier_sync(clean_un)

    if not user_rec and clean_tg and clean_tg not in ("0", ""):
        user_rec = get_user_by_identifier_sync(clean_tg)

    if not user_rec:
        return JSONResponse({
            "success": True,
            "registered": False,
            "status": "UNREGISTERED",
            "active": False,
            "message": "المستخدم غير مسجل في النظام",
        })

    # Admin check on user_rec
    is_admin = (
        user_rec.role == "admin"
        or str(user_rec.telegram_user_id) == ADMIN_TELEGRAM_ID
        or (user_rec.username and user_rec.username.lower() == ADMIN_USERNAME.lower())
        or (user_rec.email and user_rec.email.lower() == ADMIN_EMAIL.lower())
    )

    if is_admin:
        return JSONResponse({
            "success": True,
            "registered": True,
            "user_id": user_rec.id,
            "username": user_rec.username or ADMIN_USERNAME,
            "email": user_rec.email or ADMIN_EMAIL,
            "full_name_ar": user_rec.full_name_ar or "مدير النظام",
            "status": "ACTIVE",
            "is_admin": True,
            "active": True,
            "days_remaining": 3650,
            "message": "حساب الأدمن الرئيسي نشط بصلاحيات كاملة",
        })

    sub = check_subscription_sync(user_rec.id)

    return JSONResponse({
        "success": True,
        "registered": True,
        "user_id": user_rec.id,
        "username": user_rec.username,
        "email": user_rec.email,
        "full_name_ar": user_rec.full_name_ar,
        "status": user_rec.registration_status,
        "is_admin": False,
        "active": sub["active"],
        "days_remaining": sub["days_remaining"],
        "message": sub["message"],
    })


@router.post("/api/auth/verify-registration-otp")
async def api_verify_registration_otp(
    identifier: str = Form(...),
    code:       str = Form(...),
):
    """
    User submits the 30-second OTP code received via email upon Admin approval.
    """
    clean_id = identifier.strip()
    clean_code = code.strip()

    user = get_user_by_identifier_sync(clean_id)
    if not user:
        return JSONResponse({"success": False, "error": "المستخدم غير موجود"})

    valid = verify_code_sync(user.id, clean_code)
    if not valid:
        return JSONResponse({
            "success": False,
            "error": "رمز التحقق غير صحيح أو انتهت صلاحيته (المدة 30 ثانية). يرجى طلب رمز جديد."
        })

    # Activate user and start 30-day subscription
    activate_user_sync(user.id)
    renew_subscription_sync(user.id, days=30)
    token = _make_token(user.id)

    log_audit(user.id, "OTP_VERIFIED", f"User {user.username or user.telegram_user_id} verified 30s OTP and became ACTIVE")

    return JSONResponse({
        "success": True,
        "token": token,
        "user_id": user.id,
        "username": user.username,
        "days_remaining": 30,
        "message": "تم تأكيد الحساب بنجاح وتفعيل الاشتراك لمدة 30 يوماً!"
    })


@router.post("/api/auth/request-code")
async def api_request_code(username: str = Form(...)):
    """Request a fresh 30-second verification code sent to user email and telegram."""
    clean_u = str(username).strip()
    if not clean_u:
        return JSONResponse({"success": False, "error": "اسم المستخدم مطلوب"})

    user = get_user_by_identifier_sync(clean_u)
    if not user:
        return JSONResponse({"success": False, "error": "المستخدم غير موجود"})

    sub = check_subscription_sync(user.id)
    if not sub["active"] and user.role != "admin":
        return JSONResponse({
            "success": False,
            "error": "عذراً، انتهت فترة اشتراك هذا الحساب (30 يوماً). يرجى التواصل مع الإدارة للتجديد.",
            "expired": True,
            "days_remaining": 0
        })

    code = create_verification_code_sync(user.id)

    # 1. Send to user email if available
    if user.email:
        asyncio.create_task(
            asyncio.to_thread(send_user_otp_email, user.email, code, user.full_name_ar or user.username or "")
        )

    # 2. Send Telegram notification to Admin
    msg = (
        f"🔔 <b>رمز دخول مؤقت جديد (30 ثانية)</b>\n\n"
        f"👤 <b>المستخدم:</b> <code>{user.username or user.telegram_user_id}</code>\n"
        f"📧 <b>البريد:</b> {user.email or '-'}\n"
        f"🔑 <b>رمز الدخول:</b> <code>{code}</code>\n"
        f"⏳ <b>المدة:</b> 30 ثانية فقط!"
    )
    asyncio.create_task(send_telegram_message_safe(ADMIN_TELEGRAM_ID, msg))

    return JSONResponse({
        "success": True,
        "message": "تم إنشاء رمز التحقق (صالح لمدة 30 ثانية)",
        "expires_in": OTP_TTL_SECONDS
    })


@router.post("/api/auth/verify-code")
async def api_verify_code(username: str = Form(...), code: str = Form(...)):
    """Verify 5-digit code within 30s"""
    clean_u = str(username).strip()
    clean_c = str(code).strip()

    user = get_user_by_identifier_sync(clean_u)
    if not user:
        return JSONResponse({"success": False, "error": "المستخدم غير موجود"})

    valid = verify_code_sync(user.id, clean_c)
    if not valid:
        return JSONResponse({
            "success": False,
            "error": "الرمز غير صحيح أو انتهت صلاحيته (30 ثانية). يرجى طلب رمز جديد."
        })

    sub = check_subscription_sync(user.id)
    token = _make_token(user.id)

    return JSONResponse({
        "success": True,
        "token": token,
        "username": user.username,
        "user_id": user.id,
        "days_remaining": sub["days_remaining"],
        "message": sub["message"]
    })


@router.get("/api/auth/check-session")
async def api_check_session(token: str = Query(...)):
    """Validate existing session token and return subscription status"""
    uid = _verify_token(token)
    if not uid:
        return JSONResponse({"success": False, "error": "الجلسة غير صالحة"})

    sub = check_subscription_sync(uid)
    return JSONResponse({
        "success": True,
        "active": sub["active"],
        "days_remaining": sub["days_remaining"],
        "message": sub["message"]
    })


# ── Records & Previous Persons Management ─────────────────────────────────────
@router.get("/records", response_class=HTMLResponse)
async def records_page(request: Request):
    return templates.TemplateResponse(request, "records.html", {})


@router.get("/api/all-records")
async def api_all_records(request: Request, current_user: User = Depends(get_current_user)):
    """
    Returns active reports (is_deleted = 0).
    - If user is Admin: returns all active reports in system.
    - If regular user: returns only their own reports.
    """
    is_adm = is_admin_request(current_user, request)
    uid = None if is_adm else (current_user.id if current_user.id > 0 else None)
    tg_id = None if is_adm else (current_user.telegram_user_id if current_user.telegram_user_id != "0" else None)

    reports = get_all_saved_reports_sync(user_id=uid, telegram_user_id=tg_id)
    return JSONResponse({"success": True, "data": reports, "is_admin": is_adm})


@router.get("/api/trash-records")
async def api_trash_records(request: Request, current_user: User = Depends(get_current_user)):
    """
    Returns soft-deleted reports (is_deleted = 1).
    - If user is Admin: returns all trashed reports.
    - If regular user: returns their own trashed reports.
    """
    is_adm = is_admin_request(current_user, request)
    uid = None if is_adm else (current_user.id if current_user.id > 0 else None)
    tg_id = None if is_adm else (current_user.telegram_user_id if current_user.telegram_user_id != "0" else None)

    reports = get_trash_reports_sync(user_id=uid, telegram_user_id=tg_id)
    return JSONResponse({"success": True, "data": reports, "is_admin": is_adm})


@router.post("/api/records/delete")
async def api_delete_record(
    request: Request,
    service_code: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Soft delete: moves report to trash bin (is_deleted = 1)."""
    is_adm = is_admin_request(current_user, request)
    uid = current_user.id if current_user.id > 0 else None

    ok = soft_delete_report_sync(service_code.strip(), user_id=uid, is_admin=is_adm)
    if ok:
        log_audit(current_user.id, "REPORT_TRASHED", f"Report {service_code} moved to trash by user {current_user.id}")
        return JSONResponse({"success": True, "message": "تم نقل السجل إلى سلة المحذوفات بنجاح"})
    return JSONResponse({"success": False, "error": "تعذر حذف السجل أو ليس لديك صلاحية"})


@router.post("/api/records/restore")
async def api_restore_record(
    request: Request,
    service_code: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Restores report from trash bin (is_deleted = 0)."""
    is_adm = is_admin_request(current_user, request)
    uid = current_user.id if current_user.id > 0 else None

    ok = restore_report_sync(service_code.strip(), user_id=uid, is_admin=is_adm)
    if ok:
        log_audit(current_user.id, "REPORT_RESTORED", f"Report {service_code} restored by user {current_user.id}")
        return JSONResponse({"success": True, "message": "تم استرجاع السجل من سلة المحذوفات بنجاح"})
    return JSONResponse({"success": False, "error": "تعذر استرجاع السجل أو ليس لديك صلاحية"})


@router.post("/api/records/permanent-delete")
async def api_permanent_delete_record(
    request: Request,
    service_code: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Permanently deletes report from database (admin only)."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")

    ok = permanent_delete_report_sync(service_code.strip())
    if ok:
        log_audit(current_user.id, "REPORT_PERMANENT_DELETED", f"Report {service_code} permanently deleted by admin")
        return JSONResponse({"success": True, "message": "تم حذف السجل نهائياً من قاعدة البيانات"})
    return JSONResponse({"success": False, "error": "تعذر حذف السجل نهائياً"})


@router.get("/api/records/get")
async def api_get_record(service_code: str = Query(...)):
    """Fetch single report for editing in form."""
    rec = get_single_saved_report_sync(service_code.strip())
    if rec:
        return JSONResponse({"success": True, "data": rec})
    return JSONResponse({"success": False, "error": "السجل غير موجود"}, status_code=404)


@router.post("/api/records/update")
async def api_update_record(
    request: Request,
    service_code:         str = Form(...),
    report_type:          str = Form("GSL"),
    admission_date:       str = Form(...),
    discharge_date:       str = Form(...),
    leave_duration_days:  str = Form("1"),
    issue_date:           str = Form(""),
    report_time:          str = Form(""),
    include_barcode:      str = Form("0"),
    national_id:          str = Form(...),
    patient_name_ar:      str = Form(...),
    patient_name_en:      str = Form(""),
    nationality:          str = Form(""),
    nationality_en:       str = Form(""),
    employer:             str = Form(""),
    employer_en:          str = Form(""),
    practitioner_name_ar: str = Form(""),
    practitioner_name_en: str = Form(""),
    job_title_ar:         str = Form(""),
    job_title_en:         str = Form(""),
    hospital_name_ar:     str = Form(""),
    hospital_name_en:     str = Form(""),
    hospital_type:        str = Form("government"),
    current_user: User = Depends(get_current_user)
):
    """
    Updates existing report data in SQLite and Worker without duplicate creation,
    and regenerates the PDF with updated values.
    """
    clean_code = service_code.strip()
    is_adm = is_admin_request(current_user, request)
    uid = current_user.id if current_user.id > 0 else None

    update_dict = {
        "report_type":          report_type,
        "admission_date":       admission_date,
        "discharge_date":       discharge_date,
        "leave_duration_days":  leave_duration_days,
        "issue_date":           issue_date,
        "report_time":          report_time,
        "national_id":          national_id,
        "patient_name_ar":      patient_name_ar,
        "patient_name_en":      patient_name_en,
        "nationality":          nationality,
        "nationality_en":       nationality_en,
        "employer":             employer,
        "employer_en":          employer_en,
        "practitioner_name_ar": practitioner_name_ar,
        "practitioner_name_en": practitioner_name_en,
        "job_title_ar":         job_title_ar,
        "job_title_en":         job_title_en,
        "hospital_name_ar":     hospital_name_ar,
        "hospital_name_en":     hospital_name_en,
        "hospital_type":        hospital_type,
    }

    ok = update_saved_report_sync(clean_code, update_dict, user_id=uid, is_admin=is_adm)
    if not ok:
        return JSONResponse({"success": False, "error": "تعذر تعديل السجل أو ليس لديك صلاحية"})

    # Regenerate PDF
    try:
        from pdf.generator import generate_pdf
        pdf_path = REPORTS_DIR / f"{clean_code}.pdf"
        rec = get_single_saved_report_sync(clean_code)
        if rec:
            rec["include_barcode"] = (include_barcode.strip() == "1")
            generate_pdf(rec, pdf_path)
    except Exception as e:
        logger.warning(f"Failed to regenerate PDF on update: {e}")

    log_audit(current_user.id, "REPORT_UPDATED", f"Report {clean_code} updated by user {current_user.id}")
    return JSONResponse({"success": True, "message": "تم تحديث بيانات التقرير بنجاح", "service_code": clean_code})


# ── Full Admin Control Panel ──────────────────────────────────────────────────

@router.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, current_user: User = Depends(get_current_user)):
    """Admin dashboard accessible by @As1_oi / 8733335095 / ramo.711.vip@gmail.com or admin key."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")

    users = get_all_users_sync()
    users_data = []
    for user in users:
        sub_status = check_subscription_sync(user.id)
        latest_code = get_latest_code_for_user_sync(user.id)
        users_data.append({
            "id": user.id,
            "telegram_user_id": user.telegram_user_id,
            "username": user.username,
            "full_name_ar": user.full_name_ar,
            "full_name_en": user.full_name_en,
            "email": user.email,
            "role": user.role,
            "registration_status": user.registration_status,
            "subscription_start": user.subscription_start.isoformat() if hasattr(user.subscription_start, "isoformat") else str(user.subscription_start or ""),
            "subscription_end": user.subscription_end.isoformat() if hasattr(user.subscription_end, "isoformat") else str(user.subscription_end or ""),
            "is_active": user.is_active,
            "days_remaining": sub_status["days_remaining"],
            "subscription_message": sub_status["message"],
            "latest_code": latest_code["code"] if latest_code else None,
            "code_valid": latest_code["is_valid"] if latest_code else False,
            "code_seconds_left": latest_code["seconds_left"] if latest_code else 0,
        })

    pending_reqs = get_pending_registrations_sync()
    stats = get_system_stats_sync()
    audit_logs = get_audit_logs_sync(limit=50)

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "users": users_data,
            "pending_requests": pending_reqs,
            "stats": stats,
            "audit_logs": audit_logs,
            "admin_username": ADMIN_USERNAME,
            "admin_email": ADMIN_EMAIL,
            "otp_ttl": OTP_TTL_SECONDS,
        }
    )


@router.post("/api/admin/approve-registration")
async def api_admin_approve_registration(
    request: Request,
    user_id: int = Form(...),
    current_user: User = Depends(get_current_user)
):
    """
    Admin approves user registration:
    1. Sets registration_status = 'APPROVED'.
    2. Generates a fresh 30-second OTP code.
    3. Sends OTP code to User's Email.
    4. Sends notification to User's Telegram.
    """
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")

    result = approve_user_registration_sync(user_id)
    if not result:
        return JSONResponse({"success": False, "error": "المستخدم غير موجود"})

    if isinstance(result, tuple):
        user_rec, otp_code = result
    else:
        user_rec = result
        otp_code = create_verification_code_sync(user_id)

    # 1. Send OTP to User's Email
    if user_rec.email:
        asyncio.create_task(
            asyncio.to_thread(
                send_user_otp_email,
                user_rec.email,
                otp_code,
                user_rec.full_name_ar or user_rec.username or "المستخدم الكريم"
            )
        )

    # 2. Send Telegram message to user if available
    if user_rec.telegram_user_id and str(user_rec.telegram_user_id) not in ("0", "-1"):
        user_tg_msg = (
            f"🎉 <b>تمت الموافقة على طلب تسجيلك في صحتي!</b>\n\n"
            f"🔑 <b>رمز الدخول المؤقت:</b> <code>{otp_code}</code>\n"
            f"⏱️ <b>صلاحية الرمز:</b> 30 ثانية فقط!\n\n"
            f"تم إرسال الرمز أيضاً إلى بريدك الإلكتروني (<code>{user_rec.email or ''}</code>).\n"
            f"أدخل الرمز الآن في نموذج التسجيل لتفعيل اشتراكك لمدة 30 يوماً."
        )
        asyncio.create_task(send_telegram_message_safe(user_rec.telegram_user_id, user_tg_msg))

    log_audit(user_id, "ADMIN_APPROVE", f"Admin approved registration for user {user_rec.username or user_id}")

    return JSONResponse({
        "success": True,
        "message": f"تمت الموافقة بنجاح وإرسال رمز التحقق (30 ثانية: {otp_code}) إلى بريد وتلغرام المستخدم.",
        "code": otp_code,
        "expires_in": OTP_TTL_SECONDS
    })


@router.post("/api/admin/reject-registration")
async def api_admin_reject_registration(
    request: Request,
    user_id: int = Form(...),
    reason:  str = Form(""),
    current_user: User = Depends(get_current_user)
):
    """Admin rejects user registration request."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")

    user_rec = reject_user_registration_sync(user_id, reason.strip())
    if not user_rec:
        return JSONResponse({"success": False, "error": "المستخدم غير موجود"})

    # Notify user via Telegram if chat available
    if user_rec.telegram_user_id and str(user_rec.telegram_user_id) not in ("0", "-1"):
        msg = (
            f"❌ <b>نأسف، تم رفض طلب التسجيل الخاص بك</b>\n\n"
            f"📝 <b>السبب:</b> {reason.strip() or 'لم يتم توضيح سبب'}\n\n"
            f"للاستفسار يمكنك التواصل مع الإدارة: @{ADMIN_USERNAME}"
        )
        asyncio.create_task(send_telegram_message_safe(user_rec.telegram_user_id, msg))

    log_audit(user_id, "ADMIN_REJECT", f"Admin rejected user {user_id}: {reason}")
    return JSONResponse({"success": True, "message": "تم رفض طلب التسجيل"})


@router.post("/api/admin/suspend-user")
async def api_admin_suspend_user(
    request: Request,
    user_id: int = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Admin suspends a user account."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")

    ok = suspend_user_sync(user_id)
    if ok:
        log_audit(user_id, "ADMIN_SUSPEND", f"Admin suspended user {user_id}")
        return JSONResponse({"success": True, "message": "تم تعليق الحساب بنجاح"})
    return JSONResponse({"success": False, "error": "المستخدم غير موجود"})


@router.post("/api/admin/activate-user")
async def api_admin_activate_user(
    request: Request,
    user_id: int = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Admin activates a suspended user account."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")

    ok = activate_user_sync(user_id)
    if ok:
        log_audit(user_id, "ADMIN_ACTIVATE", f"Admin activated user {user_id}")
        return JSONResponse({"success": True, "message": "تم تنشيط الحساب بنجاح"})
    return JSONResponse({"success": False, "error": "المستخدم غير موجود"})


@router.post("/api/admin/renew")
async def renew_subscription_api(
    request: Request,
    user_id: int = Form(...),
    days:    int = Form(30),
    current_user: User = Depends(get_current_user)
):
    """Renew user subscription for specified days (admin only)."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")

    user = renew_subscription_sync(user_id, days=days)
    log_audit(user_id, "ADMIN_RENEW", f"Admin renewed subscription for {days} days")
    return JSONResponse({
        "success": True,
        "subscription_end": user.subscription_end.isoformat() if user.subscription_end else "",
        "message": f"تم تجديد الاشتراك لمدة {days} يوم بنجاح"
    })


@router.post("/api/admin/verify-code")
async def request_verification_code(
    request: Request,
    user_id: int = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Generate a 30-second verification code for a user (admin only)."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")

    code = create_verification_code_sync(user_id)
    return JSONResponse({
        "success": True,
        "code": code,
        "expires_in": OTP_TTL_SECONDS,
        "message": f"الرمز صالح لمدة {OTP_TTL_SECONDS} ثانية فقط"
    })


@router.post("/api/admin/check-code")
async def check_verification_code_api(
    request: Request,
    user_id: int = Form(...),
    code: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Check verification code (admin only)."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")

    valid = verify_code_sync(user_id, code.strip())
    if valid:
        return JSONResponse({"success": True, "message": "الرمز صحيح"})
    return JSONResponse({"success": False, "message": "الرمز غير صحيح أو منتهي الصلاحية"})


@router.post("/api/admin/create-user")
async def admin_create_user_api(
    request: Request,
    username: str = Form(...),
    days: int = Form(30),
    current_user: User = Depends(get_current_user)
):
    """Create a new user directly with active status from admin panel."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")

    clean_u = str(username).strip()
    if not clean_u:
        return JSONResponse({"success": False, "error": "اسم المستخدم مطلوب"})

    existing = get_user_by_identifier_sync(clean_u)
    if existing:
        return JSONResponse({"success": False, "error": "المستخدم موجود بالفعل"})

    new_u = create_new_user_sync(clean_u, days=days)
    return JSONResponse({
        "success": True,
        "message": f"تم إنشاء المستخدم {clean_u} باشتراك {days} يوم بنجاح",
        "user_id": new_u.id
    })


@router.get("/api/admin/stats")
async def api_admin_stats(request: Request, current_user: User = Depends(get_current_user)):
    """System stats for admin dashboard."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")
    stats = get_system_stats_sync()
    return JSONResponse({"success": True, "data": stats})


@router.get("/api/admin/audit-logs")
async def api_admin_audit_logs(request: Request, current_user: User = Depends(get_current_user)):
    """Audit logs for admin dashboard."""
    if not is_admin_request(current_user, request):
        raise HTTPException(403, "Access denied: Admin authorization required")
    logs = get_audit_logs_sync(limit=100)
    return JSONResponse({"success": True, "data": logs})
