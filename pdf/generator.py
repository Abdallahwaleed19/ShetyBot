"""
pdf/generator.py — ReportLab PDF generator.
Exact replica of the official Saudi Sick Leave Report layout.
"""
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
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

_AR_FONT = _try_register(
    "Arabic",
    "/usr/share/fonts/truetype/fonts-hosny-amiri/Amiri-Regular.ttf",
    "/usr/share/fonts/truetype/amiri/Amiri-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    str(_FONTS_DIR / "Arabic.ttf"),
)

_EN_FONT = _try_register(
    "Latin",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    str(_FONTS_DIR / "Latin.ttf"),
)

# ── Colors ─────────────────────────────────────────────────────────────────────
DARK_BLUE  = colors.HexColor("#2C3E77")
TEAL_BLUE  = colors.HexColor("#1A6B8A")
LABEL_BG   = colors.HexColor("#D6E4F0")
ALT_BG     = colors.HexColor("#EBF3FA")
WHITE      = colors.white
BLACK      = colors.black
GREY       = colors.HexColor("#888888")
MID_GREY   = colors.HexColor("#CCCCCC")

# ── Arabic helper ──────────────────────────────────────────────────────────────
def ar(text: str) -> str:
    if not text:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)

def _has_arabic(text: str) -> bool:
    return any('\u0600' <= c <= '\u06FF' for c in str(text or ""))

# ── Paragraph helpers ──────────────────────────────────────────────────────────
def _p(text, font, size, color=BLACK, align=TA_LEFT) -> Paragraph:
    style = ParagraphStyle(
        "s", fontName=font, fontSize=size,
        textColor=color, alignment=align,
        leading=size * 1.5, spaceBefore=0, spaceAfter=0,
    )
    return Paragraph(str(text or ""), style)

def _ar(text, size=9, color=BLACK, align=TA_RIGHT):
    return _p(ar(text), _AR_FONT, size, color, align)

def _en(text, size=9, color=BLACK, align=TA_LEFT):
    return _p(str(text or ""), _EN_FONT, size, color, align)

def _val(text, size=9, color=BLACK, align=TA_CENTER):
    """Auto-detect Arabic text and render with correct font."""
    s = str(text or "")
    if _has_arabic(s):
        return _p(ar(s), _AR_FONT, size, color, TA_RIGHT)
    return _p(s, _EN_FONT, size, color, align)


# ── Main generator ─────────────────────────────────────────────────────────────
def generate_pdf(data: dict, output_path) -> Path:
    output_path = Path(output_path)
    PAGE_W, PAGE_H = A4
    M = 1.5 * cm

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=M, rightMargin=M,
        topMargin=M, bottomMargin=M,
    )
    story = []
    W = PAGE_W - 2 * M

    # ── Data helpers ───────────────────────────────────────────────────────────
    ad_g  = data.get("admission_date_gregorian", "")
    ad_h  = data.get("admission_date_hijri", "")
    dd_g  = data.get("discharge_date_gregorian", "")
    dd_h  = data.get("discharge_date_hijri", "")
    iss_g = data.get("issue_date_gregorian", "")
    iss_h = data.get("issue_date_hijri", "")
    iss_t = data.get("issue_time", "")
    dur   = data.get("leave_duration_days", "")
    hosp_ar = data.get("hospital_name_ar", "")
    hosp_en = data.get("hospital_name_en", "")

    # ── HEADER ─────────────────────────────────────────────────────────────────
    # Left: uploaded hospital logo
    logo_path = data.get("hospital_logo_path", "")
    if logo_path and Path(logo_path).exists():
        try:
            from reportlab.platypus import Image as RLImage
            logo_cell = RLImage(logo_path, width=2.2*cm, height=2.2*cm, kind="proportional")
        except Exception:
            logo_cell = _en("", 8)
    else:
        logo_cell = _en("", 8)

    # Center: KSA title
    center_content = [
        _ar("المملكة العربية السعودية", 11, DARK_BLUE, TA_CENTER),
        _en("Kingdom of Saudi Arabia", 9, DARK_BLUE, TA_CENTER),
    ]

    # Right: decorative placeholder (empty in our case)
    right_content = _en("", 8)

    header_tbl = Table(
        [[logo_cell, center_content, right_content]],
        colWidths=[W*0.25, W*0.5, W*0.25],
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",   (0,0), (0,0),   "LEFT"),
        ("ALIGN",   (1,0), (1,0),   "CENTER"),
        ("ALIGN",   (2,0), (2,0),   "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 3*mm))

    # ── TITLE ──────────────────────────────────────────────────────────────────
    story.append(_ar("تقرير إجازة مرضية", 14, TEAL_BLUE, TA_CENTER))
    story.append(_en("Sick Leave Report",  11, DARK_BLUE, TA_CENTER))
    story.append(Spacer(1, 4*mm))

    # ── DATA TABLE ─────────────────────────────────────────────────────────────
    # 4 columns: [EN label | EN value | AR value | AR label]
    CL = W * 0.20   # label width
    CV = W * 0.30   # value width

    # Column widths list
    cw = [CL, CV, CV, CL]

    # ── Row builder ────────────────────────────────────────────────────────────
    # Normal 4-col row
    def row4(en_lbl, en_val, ar_val, ar_lbl, lbl_sz=8.5, val_sz=8.5):
        return [
            _en(en_lbl,  lbl_sz, DARK_BLUE, TA_CENTER),
            _val(en_val, val_sz, BLACK,     TA_CENTER),
            _val(ar_val, val_sz, BLACK,     TA_RIGHT),
            _ar(ar_lbl,  lbl_sz, DARK_BLUE, TA_RIGHT),
        ]

    # Span row: value spans cols 1+2 (merged center)
    def row_span(en_lbl, center_val, ar_lbl, val_sz=8.5):
        return [
            _en(en_lbl,    8.5, DARK_BLUE, TA_CENTER),
            _val(center_val, val_sz, BLACK, TA_CENTER),
            "",  # will be spanned
            _ar(ar_lbl, 8.5, DARK_BLUE, TA_RIGHT),
        ]

    dur_en = f"{dur} day(s)  ( {ad_g} to {dd_g} )"
    dur_ar = f"{ar(str(dur))} يوم  ( {ar(dd_h)} الى {ar(ad_h)} )"

    rows_data = [
        # (type, row_data, is_span_col23, is_dark_header, is_alt_bg)
        ("span", row_span("Leave ID",       data.get("leave_id",""),           "رمز الإجازة"),    False, False),
        ("4col", row4("Leave Duration",     dur_en,                 dur_ar,    "مدة الإجازة",  8, 7.5), False, True),   # dark header
        ("4col", row4("Admission Date",     ad_g,                   ad_h,      "تاريخ الدخول"), False, False),
        ("4col", row4("Discharge Date",     dd_g,                   dd_h,      "تاريخ الخروج"), True,  False),
        ("span", row_span("Issue Date",     iss_g,                             "تاريخ إصدار التقرير"), False, False),
        ("4col", row4("Name",               data.get("patient_name_en",""),    data.get("patient_name_ar",""),    "الاسم"),   True, False),
        ("span", row_span("National ID / Iqama", data.get("national_id",""),   "رقم الهوية / الإقامة"),            False, False),
        ("4col", row4("Nationality",        data.get("nationality",""),        data.get("nationality",""),        "الجنسية"), True, False),
        ("4col", row4("Employer",           data.get("employer",""),           data.get("employer",""),           "جهة العمل"), False, False),
        ("4col", row4("Practitioner Name",  data.get("practitioner_name_en",""), data.get("practitioner_name_ar",""), "اسم الممارس"), True, False),
        ("4col", row4("Position",           data.get("practitioner_position_en",""), data.get("practitioner_position_ar",""), "المسمى الوظيفي"), False, False),
    ]

    table_data  = []
    span_cmds   = []
    style_cmds  = [
        ("GRID",          (0,0), (-1,-1), 0.4, MID_GREY),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 5),
        # Label cols background
        ("BACKGROUND",    (0,0), (0,-1), LABEL_BG),
        ("BACKGROUND",    (3,0), (3,-1), LABEL_BG),
    ]

    dark_header_idx = None

    for i, entry in enumerate(rows_data):
        if len(entry) == 5:
            rtype, rdata, is_alt, is_dark, _ = entry
        else:
            rtype, rdata, is_alt, is_dark = entry[0], entry[1], entry[2], entry[3]

        table_data.append(rdata)

        if rtype == "span":
            span_cmds.append(("SPAN", (1, i), (2, i)))
            style_cmds.append(("ALIGN", (1, i), (2, i), "CENTER"))

        if is_dark:
            dark_header_idx = i
            style_cmds.extend([
                ("BACKGROUND", (0, i), (-1, i), DARK_BLUE),
                ("TEXTCOLOR",  (0, i), (-1, i), WHITE),
            ])
        elif is_alt:
            style_cmds.append(("BACKGROUND", (1, i), (2, i), ALT_BG))

    all_cmds = style_cmds + span_cmds
    data_table = Table(table_data, colWidths=cw, repeatRows=0)
    data_table.setStyle(TableStyle(all_cmds))
    story.append(data_table)
    story.append(Spacer(1, 5*mm))

    # ── FOOTER ─────────────────────────────────────────────────────────────────
    # Left: verification text + link
    footer_left = [
        _ar("للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة الرسمي", 7.5, GREY, TA_LEFT),
        _en("To check the report please visit Seha's official website", 7.5, GREY, TA_LEFT),
        _en("www.seha.sa/#/inquiries/slenquiry", 7.5, TEAL_BLUE, TA_LEFT),
    ]

    # Right: hospital info
    footer_right = [
        _ar(hosp_ar, 8, DARK_BLUE, TA_RIGHT),
        _en(hosp_en, 8, DARK_BLUE, TA_RIGHT),
    ]

    footer_tbl = Table(
        [[footer_left, footer_right]],
        colWidths=[W*0.6, W*0.4],
    )
    footer_tbl.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY))
    story.append(Spacer(1, 2*mm))
    story.append(footer_tbl)
    story.append(Spacer(1, 4*mm))

    # Bottom: timestamp left
    issue_dt = f"{iss_t}\n{iss_g}"
    story.append(_en(issue_dt, 8, BLACK, TA_LEFT))

    doc.build(story)
    return output_path
