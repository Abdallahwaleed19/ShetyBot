"""
web/routes.py — API + HTML routes
يشمل:
- GET /form        : يفتح نموذج Telegram WebApp
- POST /api/submit-report : يستقبل البيانات، يحفظ في MySQL، يولّد PDF
- GET /verify      : صفحة التحقق HTML
- GET /api/verify  : JSON API للتحقق
- GET /api/download/{id} : تحميل PDF
"""
import os, sys, uuid, asyncio
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import date, time, datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, or_

from db.database import AsyncSessionLocal
from db.models import SickLeaveReport, HospitalType
from config import BASE_DIR, UPLOADS_DIR, REPORTS_DIR

router   = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))


# ── WebApp Form ───────────────────────────────────────────────────────────────
@router.get("/form", response_class=HTMLResponse, summary="Telegram WebApp 3-page form")
async def form_page(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})


# ── Submit Report API ─────────────────────────────────────────────────────────
@router.post("/api/submit-report", summary="Receive form data, save to MySQL, generate PDF")
async def submit_report(
    # Page 1
    service_code:        str = Form(...),
    report_type:         str = Form("تقرير إجازة مرضية"),
    admission_date:      str = Form(...),
    discharge_date:      str = Form(...),
    leave_duration_days: str = Form("1"),
    issue_date:          str = Form(...),
    report_time:         str = Form(""),
    # Page 2
    national_id:         str = Form(...),
    patient_name_ar:     str = Form(...),
    patient_name_en:     str = Form(""),
    nationality:         str = Form(""),
    employer:            str = Form(""),
    # Page 3
    practitioner_name_ar: str = Form(""),
    practitioner_name_en: str = Form(""),
    job_title_ar:         str = Form(""),
    job_title_en:         str = Form(""),
    hospital_name_ar:     str = Form(""),
    hospital_name_en:     str = Form(""),
    hospital_type:        str = Form("government"),
    telegram_user_id:     str = Form("0"),
    logo: Optional[UploadFile] = File(None),
):
    try:
        # ── Auto issue date & time (server-side, now) ───────────────────────
        now_dt = datetime.now()
        auto_issue_date = now_dt.date()
        auto_time       = now_dt.time().replace(second=0, microsecond=0)

        # ── Parse dates ─────────────────────────────────────────────────────
        def pd(s):
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
                try: return datetime.strptime(s.strip(), fmt).date()
                except: pass
            return None

        adm = pd(admission_date)
        dis = pd(discharge_date)
        if not adm or not dis:
            return JSONResponse({"success": False, "error": "تاريخ غير صحيح"})

        # Use server auto-generated issue date & time
        iss = auto_issue_date
        rt  = auto_time

        dur = int(leave_duration_days) if str(leave_duration_days).strip().isdigit() else max((dis - adm).days, 1)

        h_type = HospitalType.government if hospital_type.lower() == "government" else HospitalType.private

        # ── Save logo ──────────────────────────────────────────────────────
        logo_path = None
        if logo and logo.filename:
            ext = Path(logo.filename).suffix or ".jpg"
            fname = f"logo_{service_code}{ext}"
            logo_path = str(UPLOADS_DIR / fname)
            content = await logo.read()
            with open(logo_path, "wb") as f:
                f.write(content)

        # ── Save to MySQL ──────────────────────────────────────────────────
        record = SickLeaveReport(
            service_code         = service_code,
            report_type          = report_type,
            admission_date       = adm,
            discharge_date       = dis,
            leave_duration_days  = dur,
            issue_date           = iss,
            report_time          = rt,
            national_id          = national_id[:14],
            patient_name_ar      = patient_name_ar,
            patient_name_en      = patient_name_en or None,
            nationality          = nationality or None,
            employer             = employer or None,
            practitioner_name_ar = practitioner_name_ar or None,
            practitioner_name_en = practitioner_name_en or None,
            job_title_ar         = job_title_ar or None,
            job_title_en         = job_title_en or None,
            hospital_name_ar     = hospital_name_ar or None,
            hospital_name_en     = hospital_name_en or None,
            hospital_type        = h_type,
            hospital_logo_path   = logo_path,
            companion_name       = None,
            relationship         = None,
        )

        async with AsyncSessionLocal() as session:
            session.add(record)
            await session.commit()

        # ── Generate PDF ───────────────────────────────────────────────────
        def _hijri(d: date) -> str:
            try:
                from hijri_converter import convert
                h = convert.Gregorian(d.year, d.month, d.day).to_hijri()
                return f"{h.year}/{h.month:02d}/{h.day:02d}"
            except: return str(d)

        def _fmt(d): return d.strftime("%d/%m/%Y") if d else ""

        pdf_data = {
            "leave_id":                 service_code,
            "national_id":              national_id,
            "patient_name_ar":          patient_name_ar,
            "patient_name_en":          patient_name_en,
            "nationality":              nationality,
            "employer":                 employer,
            "report_type":              report_type,
            "admission_date_gregorian": _fmt(adm),
            "admission_date_hijri":     _hijri(adm),
            "discharge_date_gregorian": _fmt(dis),
            "discharge_date_hijri":     _hijri(dis),
            "leave_duration_days":      dur,
            "issue_date_gregorian":     _fmt(iss),
            "issue_date_hijri":         _hijri(iss),
            "issue_time":               rt.strftime("%I:%M %p") if rt else "",
            "practitioner_name_ar":     practitioner_name_ar,
            "practitioner_name_en":     practitioner_name_en,
            "practitioner_position_ar": job_title_ar,
            "practitioner_position_en": job_title_en,
            "hospital_name_ar":         hospital_name_ar,
            "hospital_name_en":         hospital_name_en,
            "hospital_type":            hospital_type,
            "hospital_logo_path":       logo_path,
        }

        from pdf.generator import generate_pdf
        pdf_path = REPORTS_DIR / f"{service_code}.pdf"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, generate_pdf, pdf_data, pdf_path)

        return JSONResponse({"success": True, "service_code": service_code})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)})


# ── Verification pages ────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("verify.html", {"request": request, "record": None, "error": None, "query": ""})


@router.get("/verify", response_class=HTMLResponse)
@router.get("/inquiries", response_class=HTMLResponse)
async def verify_page(request: Request, q: Optional[str] = Query(None)):
    record = None; error = None
    if q:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(SickLeaveReport).where(
                    or_(SickLeaveReport.service_code == q, SickLeaveReport.national_id == q)
                )
            )
            record = result.scalar_one_or_none()
        if not record:
            error = f"لم يتم العثور على سجل لـ: {q}"
    return templates.TemplateResponse("verify.html", {"request": request, "record": record, "error": error, "query": q or ""})


@router.get("/api/verify")
async def api_verify(q: str = Query(...)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SickLeaveReport).where(
                or_(SickLeaveReport.service_code == q, SickLeaveReport.national_id == q)
            )
        )
        r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(404, f"No record found for: {q}")
    return {
        "service_code": r.service_code,
        "national_id":  r.national_id,
        "patient_name_ar": r.patient_name_ar,
        "patient_name_en": r.patient_name_en,
        "admission_date":  str(r.admission_date),
        "discharge_date":  str(r.discharge_date),
        "leave_duration_days": r.leave_duration_days,
        "hospital_name_ar": r.hospital_name_ar,
        "practitioner_name_ar": r.practitioner_name_ar,
        "hospital_type": r.hospital_type.value if r.hospital_type else "",
        "created_at": r.created_at.isoformat() if r.created_at else "",
    }


@router.get("/api/download/{service_code}")
async def download_pdf(service_code: str):
    pdf = REPORTS_DIR / f"{service_code}.pdf"
    if not pdf.exists():
        raise HTTPException(404, "PDF not found")
    return FileResponse(str(pdf), media_type="application/pdf",
                        filename=f"SickLeave_{service_code}.pdf")
