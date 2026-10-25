"""
pdf/generator.py — Seha Sick Leave Report Generator
Hybrid High-Precision Engine based on PyMuPDF (fitz) and the official Seha template.
Produces 100% pixel-perfect match to the official Seha reference.
"""
from __future__ import annotations

import io
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import fitz
import arabic_reshaper
from bidi.algorithm import get_display

# ── Paths & Assets ─────────────────────────────────────────────────────────────
_BASE_DIR = Path(__file__).resolve().parent
_ASSETS_DIR = _BASE_DIR / "assets"
_FONTS_DIR = _BASE_DIR / "fonts"

TEMPLATE_PATH = _ASSETS_DIR / "sickleaves_template.pdf"
FONT_BOLD_PATH = _FONTS_DIR / "NotoSansArabic-Bold.ttf"
FONT_REG_PATH = _FONTS_DIR / "NotoSansArabic-Regular.ttf"
MOH_LOGO_PATH = _ASSETS_DIR / "moh_logo.png"

# Color constants
C_DARK_VAL = (0.17255, 0.24314, 0.46667)    # #2c3e77
C_WHITE    = (1.0, 1.0, 1.0)
C_BLACK    = (0.0, 0.0, 0.0)
C_NAVY_URL = (0.08235, 0.23137, 0.76078)    # Vivid Dark Blue for link

_AR_FONT = "NSA_R"
_EN_FONT = "times-roman"


def has_ar(text: str) -> bool:
    """Check if string contains Arabic characters."""
    return any("\u0600" <= c <= "\u06ff" for c in str(text or ""))


def ar(text: str) -> str:
    """Format Arabic text for display with reshaping and bidi ordering."""
    if not text:
        return ""
    return get_display(arabic_reshaper.reshape(str(text).strip()))


def _format_date(d_str: Union[str, datetime, None]) -> str:
    """Normalize date to DD-MM-YYYY."""
    if not d_str:
        return ""
    if isinstance(d_str, datetime):
        return d_str.strftime("%d-%m-%Y")
    s = str(d_str).strip().replace("/", "-")
    parts = [p.strip() for p in s.split("-") if p.strip()]
    if len(parts) == 3:
        if len(parts[0]) == 4:  # YYYY-MM-DD -> DD-MM-YYYY
            return f"{parts[2].zfill(2)}-{parts[1].zfill(2)}-{parts[0]}"
        elif len(parts[2]) == 4:  # DD-MM-YYYY
            return f"{parts[0].zfill(2)}-{parts[1].zfill(2)}-{parts[2]}"
    return s


def _get_hijri(d_str: Union[str, datetime, None]) -> str:
    """Convert Gregorian date to Hijri DD-MM-YYYY if possible."""
    if not d_str:
        return ""
    dt = None
    if isinstance(d_str, datetime):
        dt = d_str
    else:
        norm = _format_date(d_str)
        try:
            parts = [int(p) for p in norm.split("-")]
            if len(parts) == 3:
                dt = datetime(parts[2], parts[1], parts[0])
        except Exception:
            pass
    if dt:
        try:
            from hijri_converter import convert
            h = convert.Gregorian(dt.year, dt.month, dt.day).to_hijri()
            return f"{h.day:02d}-{h.month:02d}-{h.year}"
        except Exception:
            pass
    return str(d_str)


def generate_pdf(data: dict, output_path: Union[str, Path]) -> Path:
    """
    Generate pixel-perfect Seha Sick Leave Report matching Canva reference 100%.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Template not found at: {TEMPLATE_PATH}")

    doc = fitz.open(str(TEMPLATE_PATH))
    page = doc[0]

    # Register fonts
    page.insert_font(fontname="NSA_B", fontfile=str(FONT_BOLD_PATH))
    page.insert_font(fontname="NSA_R", fontfile=str(FONT_REG_PATH))

    f_roman = fitz.Font("times-roman")
    f_bold  = fitz.Font("times-bold")
    f_nsa_r = fitz.Font(fontfile=str(FONT_REG_PATH))
    f_nsa_b = fitz.Font(fontfile=str(FONT_BOLD_PATH))

    # ── Unpack & Normalize Data ────────────────────────────────────────────────
    leave_id = str(data.get("leave_id") or data.get("service_code") or "").strip()
    dur_str  = str(data.get("leave_duration_days") or "1").strip()
    unit     = "day" if dur_str == "1" else "days"

    ad_g = _format_date(data.get("admission_date_gregorian") or data.get("admission_date"))
    dd_g = _format_date(data.get("discharge_date_gregorian") or data.get("discharge_date"))
    iss_g = _format_date(data.get("issue_date_gregorian") or data.get("issue_date") or ad_g)

    ad_h = _format_date(data.get("admission_date_hijri")) or _get_hijri(ad_g)
    dd_h = _format_date(data.get("discharge_date_hijri")) or _get_hijri(dd_g)

    p_name_en = str(data.get("patient_name_en") or "").strip()
    p_name_ar = str(data.get("patient_name_ar") or "").strip()
    nid       = str(data.get("national_id") or "").strip()
    nat_en    = str(data.get("nationality_en") or "").strip()
    nat_ar    = str(data.get("nationality") or "").strip()
    emp_en    = str(data.get("employer_en") or "").strip()
    emp_ar    = str(data.get("employer") or "").strip()

    pr_en = str(data.get("practitioner_name_en") or "").strip()
    pr_ar = str(data.get("practitioner_name_ar") or "").strip()
    pos_en = str(data.get("practitioner_position_en") or data.get("job_title_en") or "").strip()
    pos_ar = str(data.get("practitioner_position_ar") or data.get("job_title_ar") or "").strip()

    hosp_en = str(data.get("hospital_name_en") or "").strip()
    hosp_ar = str(data.get("hospital_name_ar") or "").strip()
    hosp_type = str(data.get("hospital_type") or "").strip().lower()
    report_type = str(data.get("report_type") or "").strip().upper()

    iss_time = str(data.get("issue_time") or data.get("report_time") or "").strip()
    if not iss_time:
        iss_time = datetime.now().strftime("%I:%M %p").lstrip("0")

    iss_long = str(data.get("issue_date_long") or "").strip()
    if not iss_long and iss_g:
        try:
            parts = [int(p) for p in iss_g.split("-")]
            dt = datetime(parts[2], parts[1], parts[0])
            iss_long = f"{dt.strftime('%A')} ,{dt.day} {dt.strftime('%B %Y')}"
        except Exception:
            iss_long = iss_g
    if iss_long:
        import re
        iss_long = re.sub(r"([A-Za-z]+)\s*[,،]\s*(\d+)", r"\1 ,\2", iss_long)

    with_qr = data.get("include_barcode", False)
    if isinstance(with_qr, str):
        with_qr = with_qr.lower() in ("true", "1", "yes")

    # ── Table Insertions ────────────────────────────────────────────────────────

    # Row 0: Leave ID (Merged Col 1 & 2, center = 437.53, baseline = 266.24)
    if leave_id:
        w = f_roman.text_length(leave_id, 13.5)
        page.insert_text(fitz.Point(437.53 - w / 2, 266.24), leave_id, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)

    # Row 1: Duration (White text on dark blue background)
    # English Col 1 (center = 318.27, baseline = 309.00)
    dur_en = f"{dur_str} {unit} ( {ad_g} to {dd_g} )"
    w = f_roman.text_length(dur_en, 13.5)
    page.insert_text(fitz.Point(318.27 - w / 2, 309.00), dur_en, fontname="times-roman", fontsize=13.5, color=C_WHITE)

    # Arabic Col 2 (center = 556.78, baseline = 309.52)
    s1 = f"({dd_h} "
    w1 = f_roman.text_length(s1, 13.5)
    s2 = ar("الى")
    w2 = f_nsa_r.text_length(s2, 13.5)
    s3 = f" {ad_h})"
    w3 = f_roman.text_length(s3, 13.5)
    s4 = " " + ar("يوم")
    w4 = f_nsa_r.text_length(s4, 13.5)
    s5 = f" {dur_str}"
    w5 = f_roman.text_length(s5, 13.5)

    tot_w = w1 + w2 + w3 + w4 + w5
    sx = 556.78 - tot_w / 2
    page.insert_text(fitz.Point(sx, 309.52), s1, fontname="times-roman", fontsize=13.5, color=C_WHITE)
    page.insert_text(fitz.Point(sx + w1, 309.52), s2, fontname="NSA_R", fontsize=13.5, color=C_WHITE)
    page.insert_text(fitz.Point(sx + w1 + w2, 309.52), s3, fontname="times-roman", fontsize=13.5, color=C_WHITE)
    page.insert_text(fitz.Point(sx + w1 + w2 + w3, 309.52), s4, fontname="NSA_R", fontsize=13.5, color=C_WHITE)
    page.insert_text(fitz.Point(sx + w1 + w2 + w3 + w4, 309.52), s5, fontname="times-roman", fontsize=13.5, color=C_WHITE)

    # Row 2: Admission Date (baseline = 351.01)
    if ad_g:
        w = f_roman.text_length(ad_g, 13.5)
        page.insert_text(fitz.Point(318.27 - w / 2, 351.01), ad_g, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)
    if ad_h:
        w = f_roman.text_length(ad_h, 13.5)
        page.insert_text(fitz.Point(556.78 - w / 2, 351.01), ad_h, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)

    # Row 3: Discharge Date (baseline = 393.03)
    if dd_g:
        w = f_roman.text_length(dd_g, 13.5)
        page.insert_text(fitz.Point(318.27 - w / 2, 393.03), dd_g, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)
    if dd_h:
        w = f_roman.text_length(dd_h, 13.5)
        page.insert_text(fitz.Point(556.78 - w / 2, 393.03), dd_h, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)

    # Row 4: Issue Date (Merged Col 1 & 2, center = 437.53, baseline = 435.04)
    if iss_g:
        w = f_roman.text_length(iss_g, 13.5)
        page.insert_text(fitz.Point(437.53 - w / 2, 435.04), iss_g, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)

    # Row 5: Patient Name
    if p_name_en:
        parts_n = p_name_en.split()
        if len(parts_n) > 3:
            nl1 = " ".join(parts_n[:3])
            nl2 = " ".join(parts_n[3:])
            w1 = f_roman.text_length(nl1, 13.5)
            w2 = f_roman.text_length(nl2, 13.5)
            page.insert_text(fitz.Point(318.27 - w1 / 2, 470.56), nl1, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)
            page.insert_text(fitz.Point(318.27 - w2 / 2, 486.08), nl2, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)
        else:
            w = f_roman.text_length(p_name_en, 13.5)
            page.insert_text(fitz.Point(318.27 - w / 2, 478.84), p_name_en, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)

    if p_name_ar:
        ar_name = ar(p_name_ar)
        w = f_nsa_r.text_length(ar_name, 13.5)
        page.insert_text(fitz.Point(556.78 - w / 2, 478.84), ar_name, fontname="NSA_R", fontsize=13.5, color=C_DARK_VAL)

    # Row 6: National ID / Iqama (Merged Col 1 & 2, center = 437.53, baseline = 521.60)
    if nid:
        w = f_roman.text_length(nid, 13.5)
        page.insert_text(fitz.Point(437.53 - w / 2, 521.60), nid, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)

    # Row 7: Nationality
    if nat_en:
        w = f_roman.text_length(nat_en, 13.5)
        page.insert_text(fitz.Point(318.27 - w / 2, 563.61), nat_en, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)
    if nat_ar:
        ar_nat = ar(nat_ar)
        w = f_nsa_r.text_length(ar_nat, 13.5)
        page.insert_text(fitz.Point(556.78 - w / 2, 564.13), ar_nat, fontname="NSA_R", fontsize=13.5, color=C_DARK_VAL)

    # Row 8: Employer (Strictly separate: Arabic in Col 2 ONLY, English in Col 1 if provided)
    if emp_en:
        w = f_roman.text_length(emp_en, 13.5)
        page.insert_text(fitz.Point(318.27 - w / 2, 605.62), emp_en, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)
    if emp_ar:
        ar_emp = ar(emp_ar)
        w = f_nsa_r.text_length(ar_emp, 13.5)
        page.insert_text(fitz.Point(556.78 - w / 2, 606.14), ar_emp, fontname="NSA_R", fontsize=13.5, color=C_DARK_VAL)

    # Row 9: Practitioner Name
    if pr_en:
        parts_p = pr_en.split()
        if len(parts_p) > 3:
            pl1 = " ".join(parts_p[:3])
            pl2 = " ".join(parts_p[3:])
            w1 = f_roman.text_length(pl1, 13.5)
            w2 = f_roman.text_length(pl2, 13.5)
            page.insert_text(fitz.Point(318.27 - w1 / 2, 642.00), pl1, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)
            page.insert_text(fitz.Point(318.27 - w2 / 2, 656.50), pl2, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)
        else:
            w = f_roman.text_length(pr_en, 13.5)
            page.insert_text(fitz.Point(318.27 - w / 2, 647.64), pr_en, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)

    if pr_ar:
        ar_pr = ar(pr_ar)
        w = f_nsa_r.text_length(ar_pr, 13.5)
        page.insert_text(fitz.Point(556.78 - w / 2, 648.15), ar_pr, fontname="NSA_R", fontsize=13.5, color=C_DARK_VAL)

    # Row 10: Position (Directly below practitioner name)
    if pos_en:
        w = f_roman.text_length(pos_en, 13.5)
        page.insert_text(fitz.Point(318.27 - w / 2, 689.65), pos_en, fontname="times-roman", fontsize=13.5, color=C_DARK_VAL)
    if pos_ar:
        ar_pos = ar(pos_ar)
        w = f_nsa_r.text_length(ar_pos, 13.5)
        page.insert_text(fitz.Point(556.78 - w / 2, 690.17), ar_pos, fontname="NSA_R", fontsize=13.5, color=C_DARK_VAL)

    # ── Footer Section ─────────────────────────────────────────────────────────

    # 1. Hospital Logo & Names
    # Logo selection: custom upload > MOH logo for gov/GSL
    logo_file = None
    custom_logo = data.get("hospital_logo_path")
    is_gov = (hosp_type == "government" or report_type == "GSL" or leave_id.startswith("GSL"))

    if custom_logo and Path(str(custom_logo)).exists():
        logo_file = str(custom_logo)
    elif is_gov and MOH_LOGO_PATH.exists():
        logo_file = str(MOH_LOGO_PATH)

    # Logo positioned lower, ending at logo_bottom = 844.0, sticking right to the names below
    if logo_file:
        try:
            from PIL import Image as PIL_Image
            with PIL_Image.open(logo_file) as limg:
                lw, lh = limg.size
            logo_w = 110.0
            logo_h = logo_w * (lh / lw)
            logo_bottom = 844.0
            logo_top = logo_bottom - logo_h
            page.insert_image(
                fitz.Rect(633.13 - logo_w / 2, logo_top, 633.13 + logo_w / 2, logo_bottom),
                filename=logo_file,
            )
        except Exception:
            page.insert_image(fitz.Rect(576.88, 740.0, 689.38, 844.0), filename=logo_file)

    # Hospital names directly underneath
    if hosp_ar:
        ar_hosp = ar(hosp_ar)
        w = f_nsa_b.text_length(ar_hosp, 12.75)
        page.insert_text(fitz.Point(633.13 - w / 2, 857.91), ar_hosp, fontname="NSA_B", fontsize=12.75, color=C_BLACK)

    if hosp_en:
        w = f_bold.text_length(hosp_en, 12.75)
        page.insert_text(fitz.Point(633.13 - w / 2, 878.22), hosp_en, fontname="times-bold", fontsize=12.75, color=C_BLACK)

    # 2. QR Code (Reserved space stays blank if not enabled)
    if with_qr:
        try:
            import qrcode
            qr_target = data.get("qr_data") or data.get("qr_url")
            if not qr_target:
                qr_target = f"https://seha-sea.com/#/inquiries/slenquiry?id={leave_id}"
            qr = qrcode.QRCode(
                version=None,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=1,
            )
            qr.add_data(qr_target)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            page.insert_image(fitz.Rect(56.0, 724.13, 168.5, 836.63), stream=buf.getvalue())
        except Exception:
            pass

    # 3. Verification Link: displayed text www.seha.sa/#/inquiries/slenquiry with bright blue color and underline, clickable link opens seha-sea.com
    C_BLUE_LINK = (0.0, 0.0, 1.0)  # Bright blue #0000ff
    url_text = "www.seha.sa/#/inquiries/slenquiry"
    w = f_bold.text_length(url_text, 11.25)
    ux = 226.63 - w / 2
    uy = 930.50
    page.insert_text(fitz.Point(ux, uy), url_text, fontname="times-bold", fontsize=11.25, color=C_BLUE_LINK)
    # Underline
    page.draw_line(fitz.Point(ux, uy + 1.5), fitz.Point(ux + w, uy + 1.5), color=C_BLUE_LINK, width=0.85)
    page.insert_link({
        "kind": fitz.LINK_URI,
        "from": fitz.Rect(ux - 2, 918.0, ux + w + 2, 935.0),
        "uri": "https://seha-sea.com",
    })

    # 4. Time & Date (exact original spacing and layout: Tuesday ,20 October 2026)
    page.insert_text(fitz.Point(38.25, 962.88), iss_time, fontname="times-bold", fontsize=12.75, color=C_BLACK)
    page.insert_text(fitz.Point(38.25, 990.29), iss_long, fontname="times-bold", fontsize=12.75, color=C_BLACK)

    # 5. National Health Information Center (NHIC) Logo (المركز الوطني للمعلومات الصحية) in bottom right corner
    nhic_logo_path = _ASSETS_DIR / "nhic_logo_clean.png"
    if nhic_logo_path.exists():
        page.insert_image(fitz.Rect(667.0, 948.0, 820.0, 1020.66), filename=str(nhic_logo_path))

    # Save to destination
    doc.save(str(output_path))
    doc.close()
    return output_path
