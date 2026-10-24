"""
web/routes.py — API + HTML routes
Routes:
- GET  /form                       : Telegram WebApp form
- POST /api/submit-report          : Save report → Cloudflare Worker, generate PDF
- GET  /verify  or /inquiries      : Verification HTML page
- GET  /api/verify                 : JSON verification API
- GET  /api/my-reports             : Reports by telegram_user_id
- GET  /api/download/{service_code}: Download PDF
- GET  /admin                      : Admin panel
- POST /api/admin/renew            : Renew subscription
- POST /api/admin/verify-code      : Request verification code
- POST /api/admin/check-code      : Check verification code
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Request, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates

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
    check_subscription,
    check_subscription_sync,
    renew_subscription,
    create_verification_code,
    create_verification_code_sync,
    verify_code,
    verify_code_sync,
    get_user_reports,
    verify_report_ownership,
    record_report_ownership,
    get_user_by_identifier_sync,
    create_new_user_sync,
    get_latest_code_for_user_sync,
)
import hashlib
from db.models import User
from config import BASE_DIR, UPLOADS_DIR, REPORTS_DIR
from web.form_logic import inclusive_duration

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
    async for session in get_session():
        user = await get_or_create_user(session, telegram_user_id, username)
        return user


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
    issue_date:           str = Form(""),          # user-editable, sent from form
    report_time:          str = Form(""),          # user-editable HH:MM
    include_barcode:      str = Form("0"),         # "1" or "0"
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
        # ── Check subscription ───────────────────────────────────────────────────
        async for session in get_session():
            sub_status = await check_subscription(session, current_user.id)
            if not sub_status["active"]:
                return JSONResponse({
                    "success": False,
                    "error": sub_status["message"],
                    "subscription_expired": True
                })

        # ── Arabia Standard Time (UTC+3) for fallback timestamps ──────────────
        now_dt = datetime.now(timezone(timedelta(hours=3)))

        # ── Parse helper ──────────────────────────────────────────────────────
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

        # ── Issue date: use form value if valid, else server date ─────────────
        iss = pd(issue_date) if issue_date.strip() else None
        if not iss:
            iss = now_dt.date()

        # ── Issue time: use form value if valid (HH:MM), else server time ─────
        rt = None
        if report_time.strip():
            try:
                rt_parsed = datetime.strptime(report_time.strip(), "%H:%M")
                rt = rt_parsed.time()
            except Exception:
                pass
        if rt is None:
            rt = now_dt.time().replace(second=0, microsecond=0)

        # ── Leave duration: sent by frontend (auto-calculated) ─────────────────
        dur = inclusive_duration(adm, dis)

        # ── Include barcode flag ───────────────────────────────────────────────
        with_barcode = (include_barcode.strip() == "1")

        # ── Upload logo to R2 ─────────────────────────────────────────────────
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

        # ── Hijri conversion helper ───────────────────────────────────────────
        def _hijri(d):
            try:
                from hijri_converter import convert
                h = convert.Gregorian(d.year, d.month, d.day).to_hijri()
                return f"{h.day:02d}-{h.month:02d}-{h.year}"
            except Exception:
                return str(d)

        def _fmt(d):
            return d.strftime("%d-%m-%Y") if d else ""

        # ── Build PDF data dict ───────────────────────────────────────────────
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

        # ── Generate PDF ──────────────────────────────────────────────────────
        from pdf.generator import generate_pdf
        pdf_path = REPORTS_DIR / f"{service_code}.pdf"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, generate_pdf, pdf_data, pdf_path)

        # ── Track ownership in database for data isolation ────────────────────
        try:
            async for s in get_session():
                await record_report_ownership(s, service_code, current_user.id, current_user.telegram_user_id)
        except Exception as e:
            pass

        # ── Save to Cloudflare Worker (D1) — best effort ──────────────────────
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
            "user_id":              current_user.id,  # For data isolation
        }
        worker_result = await create_report(report_data)
        if not worker_result.get("success"):
            import logging
            logging.getLogger(__name__).warning(
                "Worker save skipped/failed: %s",
                worker_result.get("error"),
            )

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


@router.get("/api/subscription-status")
async def subscription_status(telegram_user_id: str = Query(...)):
    """Get subscription status for user"""
    async for session in get_session():
        result = await session.execute(
            select(User).where(User.telegram_user_id == telegram_user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            return {"active": False, "message": "المستخدم غير موجود"}

        sub_status = await check_subscription(session, user.id)
        return sub_status


@router.get("/api/download/{service_code}")
async def download_pdf(service_code: str):
    """Download PDF directly for the report creator"""
    pdf = REPORTS_DIR / f"{service_code}.pdf"
    if not pdf.exists():
        raise HTTPException(404, "PDF not found")

    return FileResponse(
        str(pdf),
        media_type="application/pdf",
        filename=f"SickLeave_{service_code}.pdf",
    )



# ── Auth & Verification Code APIs ───

@router.post("/api/auth/request-code")
async def api_request_code(username: str = Form(...)):
    """Friend requests temporary 5-digit verification code (10s expiry)"""
    clean_u = str(username).strip()
    if not clean_u:
        return JSONResponse({"success": False, "error": "اسم المستخدم مطلوب"})

    user = get_user_by_identifier_sync(clean_u)
    if not user:
        # Create user with initial 30 days subscription
        user = create_new_user_sync(clean_u, days=30)

    # Check subscription
    sub = check_subscription_sync(user.id)
    if not sub["active"]:
        return JSONResponse({
            "success": False,
            "error": "عذراً، انتهت فترة اشتراك هذا الحساب (30 يوماً). يرجى التواصل مع الإدارة للتجديد.",
            "expired": True,
            "days_remaining": 0
        })

    code = create_verification_code_sync(user.id)

    # Send telegram notification to Admin
    admin_tg_id = os.getenv("ADMIN_TELEGRAM_ID", "8733335095").strip()
    bot_tok = os.getenv("BOT_TOKEN", "").strip()
    if admin_tg_id and bot_tok:
        try:
            msg = (
                f"🔔 <b>طلب رمز دخول مؤقت لنموذج التقارير</b>\n\n"
                f"👤 <b>المستخدم:</b> <code>{user.username or user.telegram_user_id}</code>\n"
                f"🔑 <b>رمز الدخول:</b> <code>{code}</code>\n"
                f"⏳ <b>المدة:</b> 10 ثوانٍ فقط!"
            )
            async with httpx.AsyncClient(timeout=4) as cl:
                await cl.post(
                    f"https://api.telegram.org/bot{bot_tok}/sendMessage",
                    json={"chat_id": admin_tg_id, "text": msg, "parse_mode": "HTML"}
                )
        except Exception as e:
            logger.warning(f"Failed to send telegram notification: {e}")

    return JSONResponse({
        "success": True,
        "message": "تم إرسال رمز التحقق إلى الأدمن (صالح لمدة 10 ثوانٍ)",
        "expires_in": 10
    })


@router.post("/api/auth/verify-code")
async def api_verify_code(username: str = Form(...), code: str = Form(...)):
    """Verify 5-digit code within 10s"""
    clean_u = str(username).strip()
    clean_c = str(code).strip()

    user = get_user_by_identifier_sync(clean_u)
    if not user:
        return JSONResponse({"success": False, "error": "المستخدم غير موجود"})

    valid = verify_code_sync(user.id, clean_c)
    if not valid:
        return JSONResponse({
            "success": False,
            "error": "الرمز غير صحيح أو انتهت صلاحيته (10 ثوانٍ). يرجى طلب رمز جديد."
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

# ── Admin Panel ───────────────────────────────────────────────────────────────
@router.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, current_user: User = Depends(get_current_user)):
    """Admin panel for user management and subscription renewal"""
    admin_key = request.query_params.get("key") or request.headers.get("x-admin-key")
    is_authorized = (current_user.role == "admin") or (admin_key and admin_key == os.getenv("ADMIN_KEY", "admin123"))
    if not is_authorized:
        raise HTTPException(403, "Access denied: Admin authorization required")

    async for session in get_session():
        # Get all users
        users = await get_all_users(session)

        users_data = []
        for user in users:
            sub_status = await check_subscription(session, user.id)
            latest_code = get_latest_code_for_user_sync(user.id)
            users_data.append({
                "id": user.id,
                "telegram_user_id": user.telegram_user_id,
                "username": user.username,
                "role": user.role,
                "subscription_start": user.subscription_start,
                "subscription_end": user.subscription_end,
                "is_active": user.is_active,
                "days_remaining": sub_status["days_remaining"],
                "subscription_message": sub_status["message"],
                "latest_code": latest_code["code"] if latest_code else None,
                "code_valid": latest_code["is_valid"] if latest_code else False,
                "code_seconds_left": latest_code["seconds_left"] if latest_code else 0,
            })

    return templates.TemplateResponse(
        request,
        "admin.html",
        {"users": users_data}
    )


@router.post("/api/admin/renew")
async def renew_subscription_api(
    request: Request,
    user_id: int = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Renew user subscription (admin only)"""
    admin_key = request.query_params.get("key") or request.headers.get("x-admin-key")
    is_authorized = (current_user.role == "admin") or (admin_key and admin_key == os.getenv("ADMIN_KEY", "admin123"))
    if not is_authorized:
        raise HTTPException(403, "Access denied: Admin authorization required")

    async for session in get_session():
        user = await renew_subscription(session, user_id, days=30)
        return JSONResponse({
            "success": True,
            "subscription_end": user.subscription_end.isoformat(),
            "message": "تم تجديد الاشتراك لمدة 30 يوم"
        })


@router.post("/api/admin/verify-code")
async def request_verification_code(
    request: Request,
    user_id: int = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Request a 5-digit verification code (admin only)"""
    admin_key = request.query_params.get("key") or request.headers.get("x-admin-key")
    is_authorized = (current_user.role == "admin") or (admin_key and admin_key == os.getenv("ADMIN_KEY", "admin123"))
    if not is_authorized:
        raise HTTPException(403, "Access denied: Admin authorization required")

    async for session in get_session():
        code = await create_verification_code(session, user_id)
        return JSONResponse({
            "success": True,
            "code": code,
            "message": "الرمز صالح لمدة 10 ثوانٍ فقط"
        })


@router.post("/api/admin/check-code")
async def check_verification_code_api(
    request: Request,
    user_id: int = Form(...),
    code: str = Form(...),
    current_user: User = Depends(get_current_user)
):
    """Check verification code (admin only)"""
    admin_key = request.query_params.get("key") or request.headers.get("x-admin-key")
    is_authorized = (current_user.role == "admin") or (admin_key and admin_key == os.getenv("ADMIN_KEY", "admin123"))
    if not is_authorized:
        raise HTTPException(403, "Access denied: Admin authorization required")

    async for session in get_session():
        valid = await verify_code(session, user_id, code)
        if valid:
            return JSONResponse({
                "success": True,
                "message": "الرمز صحيح"
            })
        else:
            return JSONResponse({
                "success": False,
                "message": "الرمز غير صحيح أو منتهي الصلاحية"
            })


@router.post("/api/admin/create-user")
async def admin_create_user_api(
    request: Request,
    username: str = Form(...),
    days: int = Form(30),
    current_user: User = Depends(get_current_user)
):
    """Create a new user with 30-day subscription from admin panel"""
    admin_key = request.query_params.get("key") or request.headers.get("x-admin-key")
    is_authorized = (current_user.role == "admin") or (admin_key and admin_key == os.getenv("ADMIN_KEY", "admin123"))
    if not is_authorized:
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
