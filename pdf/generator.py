"""
pdf/generator.py — ReportLab bilingual PDF generator.
Matches the official Saudi Sick Leave Report layout.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, Image, HRFlowable,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import arabic_reshaper
from bidi.algorithm import get_display

# ── Font registration ──────────────────────────────────────────────────────────
_FONTS_DIR = Path(__file__).parent / "fonts"
_FONTS_DIR.mkdir(exist_ok=True)

def _try_register(name: str, *candidates: str) -> str:
    for path in candidates:
        p = Path(path)
        if p.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(p)))
                return name
            except Exception:
                pass
    return "Helvetica"

# Arabic font — Amiri (Linux) first, then Noto, then Windows fallbacks
_AR_FONT = _try_register(
    "Arabic",
    # Linux — Amiri (fonts-hosny-amiri)
    "/usr/share/fonts/truetype/fonts-hosny-amiri/Amiri-Regular.ttf",
    "/usr/share/fonts/truetype/amiri/Amiri-Regular.ttf",
    # Linux — Noto Naskh Arabic (fonts-noto-core)
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    # Windows fallbacks
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\times.ttf",
    str(_FONTS_DIR / "Arabic.ttf"),
)

# English font — Liberation or system
_EN_FONT = _try_register(
    "Latin",
    # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    # Windows
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    str(_FONTS_DIR / "Latin.ttf"),
)

# ── Colours ────────────────────────────────────────────────────────────────────
DARK_BLUE  = colors.HexColor("#2C3E77")
LIGHT_GREY = colors.HexColor("#F2F4F8")
MID_GREY   = colors.HexColor("#CCCCCC")
WHITE      = colors.white
BLACK      = colors.black

# ── Arabic helper ──────────────────────────────────────────────────────────────
def ar(text: str) -> str:
    if not text:
        return ""
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

# ── Paragraph helpers ──────────────────────────────────────────────────────────
def _p(text, font, size, color=BLACK, align=TA_LEFT, bold=False) -> Paragraph:
    style = ParagraphStyle(
        "s",
        fontName=font,
        fontSize=size,
        textColor=color,
        alignment=align,
        leading=size * 1.4,
        wordWrap="LTR" if align != TA_RIGHT else "RTL",
    )
    return Paragraph(str(text) if text else "", style)

def _ar_p(text, size=9, color=BLACK, align=TA_RIGHT) -> Paragraph:
    return _p(ar(text), _AR_FONT, size, color, align)

def _en_p(text, size=9, color=BLACK, align=TA_LEFT) -> Paragraph:
    return _p(text or "", _EN_FONT, size, color, align)

def _ar_bold(text, size=9, color=WHITE, align=TA_RIGHT) -> Paragraph:
    return _p(ar(text), _AR_FONT, size, color, align)

def _en_bold(text, size=9, color=WHITE, align=TA_LEFT) -> Paragraph:
    return _p(text or "", _EN_FONT, size, color, align)


# ── Main generator ─────────────────────────────────────────────────────────────
def generate_pdf(data: dict, output_path) -> Path:
    output_path = Path(output_path)
    PAGE_W, PAGE_H = A4
    M = 1.5 * cm  # margin

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=M, rightMargin=M,
        topMargin=M, bottomMargin=M,
    )
    story = []
    W = PAGE_W - 2 * M  # usable width

    # ── Helper: format dates ───────────────────────────────────────────────────
    ad_g = data.get("admission_date_gregorian", "")
    ad_h = data.get("admission_date_hijri", "")
    dd_g = data.get("discharge_date_gregorian", "")
    dd_h = data.get("discharge_date_hijri", "")
    iss_g = data.get("issue_date_gregorian", "")
    iss_h = data.get("issue_date_hijri", "")
    iss_t = data.get("issue_time", "")
    dur   = data.get("leave_duration_days", "")
    h_type_en = "Government" if str(data.get("hospital_type","")).lower() == "government" else "Private"
    h_type_ar = "حكومي" if h_type_en == "Government" else "خاص"

    # ── HEADER ─────────────────────────────────────────────────────────────────
    logo_path = data.get("hospital_logo_path", "")
    if logo_path and Path(logo_path).exists():
        try:
            logo_img = Image(logo_path, width=2.5*cm, height=2.5*cm, kind="proportional")
        except Exception:
            logo_img = _en_p("", 8)
    else:
        logo_img = _en_p("", 8)

    header_center = [
        _ar_p("المملكة العربية السعودية", 12, DARK_BLUE, TA_CENTER),
        _ar_p("تقرير إجازة مرضية", 11, DARK_BLUE, TA_CENTER),
        _en_p("Sick Leave Report", 10, DARK_BLUE, TA_CENTER),
    ]

    issue_info = [
        _en_p(f"{iss_t}  {iss_g}", 8, DARK_BLUE, TA_RIGHT),
        _en_p(f"{iss_h}", 8, DARK_BLUE, TA_RIGHT),
        _en_p(f"Type: {h_type_en}", 8, DARK_BLUE, TA_RIGHT),
        _ar_p(h_type_ar, 8, DARK_BLUE, TA_RIGHT),
    ]

    # Hospital name under logo
    hosp_ar = data.get("hospital_name_ar", "")
    hosp_en = data.get("hospital_name_en", "")
    logo_cell = [
        logo_img,
        _ar_p(hosp_ar, 8, DARK_BLUE, TA_LEFT),
        _en_p(hosp_en, 8, DARK_BLUE, TA_LEFT),
    ]

    header_table = Table(
        [[logo_cell, header_center, issue_info]],
        colWidths=[W * 0.22, W * 0.55, W * 0.23],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",   (0, 0), (0, 0),   "LEFT"),
        ("ALIGN",   (1, 0), (1, 0),   "CENTER"),
        ("ALIGN",   (2, 0), (2, 0),   "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, 0), 1.5, DARK_BLUE),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))

    # ── DATA TABLE ─────────────────────────────────────────────────────────────
    # Columns: [EN label | EN value | AR value | AR label]
    CL = W * 0.18   # label columns (narrow)
    CV = W * 0.32   # value columns (wide)

    def _row(en_label, en_val, ar_val, ar_label, shaded=False):
        bg = LIGHT_GREY if shaded else WHITE
        return [
            _en_p(en_label, 8, DARK_BLUE, TA_LEFT),
            _en_p(en_val,   8, BLACK,     TA_LEFT),
            _ar_p(ar_val,   8, BLACK,     TA_RIGHT),
            _ar_p(ar_label, 8, DARK_BLUE, TA_RIGHT),
        ]

    # Title bar (header row)
    title_row = [
        _en_bold("Practitioner Name",       9, WHITE, TA_LEFT),
        _en_bold("National ID / Iqama",     9, WHITE, TA_CENTER),
        _ar_bold("الاسم / جهة العمل",       9, WHITE, TA_RIGHT),
        _ar_bold("التواريخ / رمز الإجازة",  9, WHITE, TA_RIGHT),
    ]

    rows = [
        # (en_label, en_val, ar_val, ar_label, shaded)
        ("Name",             data.get("patient_name_en",""),
         data.get("patient_name_ar",""),        "الاسم",              False),

        ("National ID / Iqama", data.get("national_id",""),
         "",                                    "رقم الهوية / الإقامة", True),

        ("Practitioner Name", data.get("practitioner_name_en",""),
         data.get("practitioner_name_ar",""),   "اسم الممارس",        False),

        ("Position",         data.get("practitioner_position_en",""),
         data.get("practitioner_position_ar",""), "المسمى الوظيفي",   True),

        ("Leave ID",         data.get("leave_id",""),
         "",                                    "رمز الإجازة",        False),

        ("Employer",         data.get("employer",""),
         "",                                    "جهة العمل",          True),

        ("Nationality",      data.get("nationality",""),
         "",                                    "الجنسية",            False),

        ("Admission Date",   f"{ad_g}  |  {ad_h}",
         f"{ar(ad_h)}  |  {ad_g}",             "تاريخ الدخول",       True),

        ("Discharge Date",   f"{dd_g}  |  {dd_h}",
         f"{ar(dd_h)}  |  {dd_g}",             "تاريخ الخروج",       False),

        ("Leave Duration",   f"{dur} day(s)",
         f"{ar(str(dur))} يوم",                "مدة الإجازة",        True),

        ("Hospital Name",    data.get("hospital_name_en",""),
         data.get("hospital_name_ar",""),       "اسم المستشفى",       False),

        ("Hospital Type",    h_type_en,
         ar(h_type_ar),                        "نوع المستشفى",       True),

        ("Issue Date",       f"{iss_g}  |  {iss_h}",
         f"{ar(iss_h)}  |  {iss_g}",           "تاريخ الإصدار",      False),
    ]

    table_data  = [title_row]
    row_styles  = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK_BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), WHITE),
    ]
    for i, (el, ev, av, al, shaded) in enumerate(rows, start=1):
        table_data.append(_row(el, ev, av, al, shaded))
        if shaded:
            row_styles.append(("BACKGROUND", (0, i), (-1, i), LIGHT_GREY))

    data_table = Table(table_data, colWidths=[CL, CV, CV, CL], repeatRows=1)
    data_table.setStyle(TableStyle([
        ("GRID",          (0, 0), (-1, -1), 0.4, MID_GREY),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ] + row_styles))
    story.append(data_table)
    story.append(Spacer(1, 5 * mm))

    # ── FOOTER ─────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY))
    story.append(Spacer(1, 2 * mm))

    footer_ar = "للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة الرسمي"
    footer_en = "To check the report please visit Seha's official website  www.seha.sa/#/inquiries/slenquiry"
    story.append(_ar_p(footer_ar, 7.5, colors.grey, TA_CENTER))
    story.append(_en_p(footer_en, 7.5, colors.grey, TA_CENTER))
    story.append(Spacer(1, 3 * mm))

    # Bottom row: timestamp left | hospital right
    issue_dt = f"{iss_g}  {iss_t}".strip()
    bottom = Table(
        [[
            _en_p(issue_dt, 7.5, BLACK, TA_LEFT),
            _ar_p(hosp_ar,  7.5, DARK_BLUE, TA_RIGHT),
        ]],
        colWidths=[W * 0.5, W * 0.5],
    )
    bottom.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(bottom)

    doc.build(story)
    return output_path
