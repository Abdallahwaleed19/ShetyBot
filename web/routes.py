"""
web/routes.py — API + HTML routes
Routes:
- GET  /form                       : Telegram WebApp form
- POST /api/submit-report          : Save report → Cloudflare Worker, generate PDF
- GET  /verify  or /inquiries      : Verification HTML page
- GET  /api/verify                 : JSON verification API
- GET  /api/download/{service_code}: Download PDF
"""
import os
import sys
import uuid
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.templating import Jinja2Templates

from db.worker_client import (
    create_report,
    get_report,
    search_by_national_id,
    upload_logo,
)
from config import BASE_DIR, UPLOADS_DIR, REPORTS_DIR

router    = APIRouter()
templates = Jinja2Templates(directory=str(BASE_DIR / "web" / "templates"))


# ── WebApp Form ────────────────────────────────────────────────────────────────
@router.get("/form", response_class=HTMLResponse, summary="Telegram WebApp 3-page form")
async def form_page(request: Request):
    return templates.TemplateResponse(request, "form.html", {})


# ── Submit Report API ──────────────────────────────────────────────────────────
@router.post("/api/submit-report", summary="Receive form data, save via Worker, generate PDF")
async def submit_report(
    # Page 1
    service_code:         str = Form(...),
    report_type:          str = Form("تقرير إجازة مرضية"),
    admission_date:       str = Form(...),
    discharge_date:       str = Form(...),
    leave_duration_days:  str = Form("1"),
    issue_date:           str = Form(...),
    report_time:          str = Form(""),
    # Page 2
    national_id:          str = Form(...),
    patient_name_ar:      str = Form(...),
    patient_name_en:      str = Form(""),
    nationality:          str = Form(""),
    employer:             str = Form(""),
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
        # ── Auto issue date & time (server-side) ─────────────────────────────
        now_dt          = datetime.now()
        auto_issue_date = now_dt.date()
        auto_time       = now_dt.time().replace(second=0, microsecond=0)

        # ── Parse dates ───────────────────────────────────────────────────────
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

        iss = auto_issue_date
        rt  = auto_time
        dur = (
            int(leave_duration_days)
            if str(leave_duration_days).strip().isdigit()
            else max((dis - adm).days, 1)
        )

        # ── Upload logo to R2 ─────────────────────────────────────────────────
        logo_url = None
        logo_local_path = None
        if logo and logo.filename:
            ext        = Path(logo.filename).suffix or ".jpg"
            unique_name = f"logo_{service_code}{ext}"
            file_bytes  = await logo.read()

            # Save locally for PDF generation
            local_path = UPLOADS_DIR / unique_name
            local_path.write_bytes(file_bytes)
            logo_local_path = str(local_path)

            # Upload to R2 via Worker
            content_type = logo.content_type or "image/jpeg"
            logo_url = await upload_logo(unique_name, file_bytes, content_type)

        # ── Save to Cloudflare D1 via Worker ──────────────────────────────────
        report_data = {
            "service_code":        service_code,
            "report_type":         report_type,
            "admission_date":      str(adm),
            "discharge_date":      str(dis),
            "leave_duration_days": dur,
            "issue_date":          str(iss),
            "report_time":         rt.strftime("%H:%M"),
            "national_id":         national_id,
            "patient_name_ar":     patient_name_ar,
            "patient_name_en":     patient_name_en,
            "nationality":         nationality,
            "employer":            employer,
            "practitioner_name_ar": practitioner_name_ar,
            "practitioner_name_en": practitioner_name_en,
            "job_title_ar":        job_title_ar,
            "job_title_en":        job_title_en,
            "hospital_name_ar":    hospital_name_ar,
            "hospital_name_en":    hospital_name_en,
            "hospital_type":       hospital_type,
            "logo_url":            logo_url or "",
            "telegram_user_id":    telegram_user_id,
        }
        worker_result = await create_report(report_data)
        if not worker_result.get("success"):
            return JSONResponse({"success": False, "error": worker_result.get("error", "Worker error")})

        # ── Generate PDF ──────────────────────────────────────────────────────
        def _hijri(d):
            try:
                from hijri_converter import convert
                h = convert.Gregorian(d.year, d.month, d.day).to_hijri()
                return f"{h.year}/{h.month:02d}/{h.day:02d}"
            except Exception:
                return str(d)

        def _fmt(d):
            return d.strftime("%d/%m/%Y") if d else ""

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
            "issue_date_long":          f"{iss.strftime('%A')}, {iss.day} {iss.strftime('%B %Y')}",
            "issue_time":               rt.strftime("%I:%M %p").lstrip("0"),
            "practitioner_name_ar":     practitioner_name_ar,
            "practitioner_name_en":     practitioner_name_en,
            "practitioner_position_ar": job_title_ar,
            "practitioner_position_en": job_title_en,
            "hospital_name_ar":         hospital_name_ar,
            "hospital_name_en":         hospital_name_en,
            "hospital_type":            hospital_type,
            "hospital_logo_path":       logo_local_path,
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


# ── Verification pages ─────────────────────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "verify.html",
        {"record": None, "error": None, "query": ""},
    )


@router.get("/verify",     response_class=HTMLResponse)
@router.get("/inquiries",  response_class=HTMLResponse)
async def verify_page(request: Request, q: Optional[str] = Query(None)):
    record = None
    error  = None
    if q:
        # Try exact service_code first, then national_id search
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
    """Get reports by telegram_user_id."""
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
    pdf = REPORTS_DIR / f"{service_code}.pdf"
    if not pdf.exists():
        raise HTTPException(404, "PDF not found")
    return FileResponse(
        str(pdf),
        media_type="application/pdf",
        filename=f"SickLeave_{service_code}.pdf",
    )
