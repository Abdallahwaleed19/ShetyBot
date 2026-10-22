"""
pdf/generator.py — ReportLab PDF generator.

Produces a document that faithfully replicates the layout of the
official Sick Leave Report (sickLeaves-28.pdf):

  ┌────────────────────────────────────────────────────┐
  │  HEADER  (logo left | KSA centre | hospital right) │
  │  Dark-blue title bar (5 columns)                   │
  ├──────────┬──────────────────────┬──────────────────┤
  │  row 1   │  field labels (EN)   │ field labels(AR) │
  │  row 2   │                      │                  │
  │  ...     │                      │                  │
  ├──────────────────────────────────────────────────────┤
  │  FOOTER  – verification notice                      │
  └──────────────────────────────────────────────────────┘
"""
from __future__ import annotations
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import textwrap
from pathlib import Path
from io import BytesIO
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, Image, HRFlowable,
)
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Arabic shaping + BiDi
import arabic_reshaper
from bidi.algorithm import get_display

# ── Font registration ────────────────────────────────────────────────────────
_FONTS_DIR = Path(__file__).parent / "fonts"
_FONTS_DIR.mkdir(exist_ok=True)

def _try_register(name: str, *candidates: str) -> str:
    """Register first available TTF; fall back to Helvetica."""
    for path in candidates:
        p = Path(path)
        if p.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(p)))
                return name
            except Exception:
                pass
    return "Helvetica"

# Try common Arabic-capable fonts on Windows
_AR_FONT = _try_register(
    "Arabic",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\times.ttf",
    str(_FONTS_DIR / "Arabic.ttf"),
)

_EN_FONT = _try_register(
    "Latin",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    str(_FONTS_DIR / "Latin.ttf"),
)

# ── Colours ──────────────────────────────────────────────────────────────────
DARK_BLUE    = colors.HexColor("#2C3E77")
LIGHT_GREY   = colors.HexColor("#F7F7F7")
MID_GREY     = colors.HexColor("#CCCCCC")
WHITE        = colors.white
BLACK        = colors.black

# ── Helpers ──────────────────────────────────────────────────────────────────
def ar(text: str) -> str:
    """Reshape + apply BiDi so Arabic renders correctly in ReportLab."""
    if not text:
        return ""
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except Exception:
        return text


def _p(text: str, font: str, size: float, color=BLACK,
        align=TA_LEFT, leading: Optional[float] = None) -> Paragraph:
    style = ParagraphStyle(
        "custom",
        fontName=font,
        fontSize=size,
        textColor=color,
        alignment=align,
        leading=leading or size * 1.3,
    )
    return Paragraph(text, style)


def _ar_p(text: str, size: float, color=BLACK,
           align=TA_RIGHT, leading: Optional[float] = None) -> Paragraph:
    return _p(ar(text), _AR_FONT, size, color, align, leading)


def _en_p(text: str, size: float, color=BLACK,
           align=TA_LEFT, leading: Optional[float] = None) -> Paragraph:
    return _p(text, _EN_FONT, size, color, align, leading)


# ── Main generator ────────────────────────────────────────────────────────────
def generate_pdf(data: dict, output_path: str | Path) -> Path:
    """
    Generate the sick-leave PDF.

    Parameters
    ----------
    data : dict
        Keys mirror the SickLeave ORM model fields.
    output_path : str | Path
        Where to write the PDF file.

    Returns
    -------
    Path
        The resolved path of the written PDF.
    """
    output_path = Path(output_path)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=1.0 * cm,
        leftMargin=1.0 * cm,
        topMargin=0.8 * cm,
        bottomMargin=0.8 * cm,
    )

    PAGE_W = A4[0] - 2.0 * cm   # usable width
    story: list = []

    # ── HEADER ────────────────────────────────────────────────────────────────
    logo_path = data.get("hospital_logo_path")
    if logo_path and Path(logo_path).exists():
        logo_img = Image(logo_path, width=3.5 * cm, height=2.5 * cm,
                         kind="proportional")
    else:
        logo_img = _en_p("", 8)  # empty placeholder

    header_left = [
        logo_img,
        _ar_p(data.get("hospital_name_ar", ""), 9, DARK_BLUE, TA_CENTER),
        _en_p(data.get("hospital_name_en", ""), 8, DARK_BLUE, TA_CENTER),
    ]

    # Hospital type badge
    h_type = data.get("hospital_type", "")
    h_type_ar = "حكومي" if "gov" in h_type.lower() else "خاص"
    h_type_en = "Government" if "gov" in h_type.lower() else "Private"
    header_right = [
        _en_p(f"{data.get('issue_time', '')}  {data.get('issue_date_gregorian', '')}",
              8, BLACK, TA_RIGHT),
        _ar_p(f"{data.get('issue_date_hijri', '')}", 8, BLACK, TA_RIGHT),
        _en_p(f"Type: {h_type_en}", 8, DARK_BLUE, TA_RIGHT),
        _ar_p(f"نوع: {h_type_ar}", 8, DARK_BLUE, TA_RIGHT),
    ]

    header_centre = [
        _en_p("Kingdom of Saudi Arabia", 9, DARK_BLUE, TA_CENTER),
        _ar_p("المملكة العربية السعودية", 9, DARK_BLUE, TA_CENTER),
        Spacer(1, 4),
        _ar_p("تقرير إجازة مرضية", 11, DARK_BLUE, TA_CENTER),
        _en_p("Sick Leave Report", 11, DARK_BLUE, TA_CENTER),
    ]

    col_w = PAGE_W / 3
    header_table = Table(
        [[header_left, header_centre, header_right]],
        colWidths=[col_w, col_w, col_w],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("ALIGN",       (0, 0), (0, 0),  "LEFT"),
        ("ALIGN",       (1, 0), (1, 0),  "CENTER"),
        ("ALIGN",       (2, 0), (2, 0),  "RIGHT"),
        ("TOPPADDING",  (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))

    # ── TITLE BAR ─────────────────────────────────────────────────────────────
    # 5-column dark-blue bar matching the SVG template
    title_cols = [
        _ar_p("اسم الممارس", 8, WHITE, TA_CENTER),
        _ar_p("رقم الهوية / الإقامة", 8, WHITE, TA_CENTER),
        _ar_p("الاسم / المسمى الوظيفي", 8, WHITE, TA_CENTER),
        _ar_p("رمز الإجازة / جهة العمل", 8, WHITE, TA_CENTER),
        _ar_p("التواريخ / المدة", 8, WHITE, TA_CENTER),
    ]
    cw5 = PAGE_W / 5
    bar_table = Table([title_cols], colWidths=[cw5] * 5)
    bar_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), DARK_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, -1), WHITE),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_GREY),
    ]))
    story.append(bar_table)

    # ── DATA ROWS ─────────────────────────────────────────────────────────────
    # Each row: [EN label | EN value | separator | AR value | AR label]
    # Laid out as a 4-column table:  col0=EN label, col1=EN value,
    #                                col2=AR value, col3=AR label
    # Col widths mirror the SVG (4 equal sections + narrow outer cols):
    #   narrow | wide | wide | narrow

    CW_OUTER = PAGE_W * 0.13
    CW_INNER = PAGE_W * 0.37

    def _row(en_label: str, en_val: str,
             ar_label: str, ar_val: str,
             shaded: bool = False) -> list:
        bg = LIGHT_GREY if shaded else WHITE
        return [
            _en_p(en_label, 8, DARK_BLUE, TA_LEFT),
            _en_p(en_val,   9, BLACK,     TA_LEFT),
            _ar_p(ar_val,   9, BLACK,     TA_RIGHT),
            _ar_p(ar_label, 8, DARK_BLUE, TA_RIGHT),
        ]

    ad_g = data.get("admission_date_gregorian", "")
    ad_h = data.get("admission_date_hijri", "")
    dd_g = data.get("discharge_date_gregorian", "")
    dd_h = data.get("discharge_date_hijri", "")

    rows_data = [
        # (EN label, EN val, AR label, AR val, shaded)
        ("Name",            data.get("patient_name_en", ""),
         "الاسم",            data.get("patient_name_ar", ""),    False),

        ("National ID / Iqama", data.get("national_id", ""),
         "رقم الهوية / الإقامة", "",                               True),

        ("Position",        data.get("practitioner_position_en", ""),
         "المسمى الوظيفي",  data.get("practitioner_position_ar", ""), False),

        ("Leave ID",        data.get("leave_id", ""),
         "رمز الإجازة",     "",                                   True),

        ("Employer",        data.get("employer", ""),
         "جهة العمل",       "",                                   False),

        ("Issue Date",      data.get("issue_date_gregorian", ""),
         "تاريخ إصدار التقرير", data.get("issue_date_hijri", ""), True),

        ("Nationality",     data.get("nationality", ""),
         "الجنسية",         "",                                   False),

        ("Leave Duration",  f"{data.get('leave_duration_days', '')} day(s)",
         "مدة الإجازة",     f"{data.get('leave_duration_days', '')} يوم", True),

        ("Admission Date",  f"{ad_g}  |  {ad_h}",
         "تاريخ الدخول",    f"{ar(ad_h)}  |  {ad_g}",            False),

        ("Discharge Date",  f"{dd_g}  |  {dd_h}",
         "تاريخ الخروج",    f"{ar(dd_h)}  |  {dd_g}",            True),

        ("Practitioner Name", data.get("practitioner_name_en", ""),
         "اسم الممارس",     data.get("practitioner_name_ar", ""), False),
    ]

    table_rows = []
    row_styles: list[tuple] = []
    for i, (el, ev, al, av, shaded) in enumerate(rows_data):
        table_rows.append(_row(el, ev, al, av, shaded))
        if shaded:
            row_styles.append(("BACKGROUND", (0, i), (-1, i), LIGHT_GREY))

    col_widths = [CW_OUTER, CW_INNER, CW_INNER, CW_OUTER]
    data_table = Table(table_rows, colWidths=col_widths, repeatRows=0)
    base_style = [
        ("GRID",          (0, 0), (-1, -1), 0.5, MID_GREY),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
    ]
    data_table.setStyle(TableStyle(base_style + row_styles))
    story.append(data_table)
    story.append(Spacer(1, 4 * mm))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=1, color=MID_GREY))
    story.append(Spacer(1, 2 * mm))

    footer_ar = "للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة الرسمي"
    footer_en = ("To check the report please visit Seha's official website  "
                 "www.seha.sa/#/inquiries/slenquiry")
    story.append(_ar_p(footer_ar, 7.5, colors.grey, TA_CENTER))
    story.append(_en_p(footer_en, 7.5, colors.grey, TA_CENTER))

    # ── Issue date/time — bottom-left, small black text ───────────────────────
    story.append(Spacer(1, 3 * mm))
    issue_dt_str = (
        f"{data.get('issue_date_gregorian', '')}  {data.get('issue_time', '')}"
    ).strip()
    footer_bottom = Table(
        [[_en_p(issue_dt_str, 7, BLACK, TA_LEFT), _ar_p("", 7)]],
        colWidths=[PAGE_W * 0.5, PAGE_W * 0.5],
    )
    footer_bottom.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN",   (0, 0), (0, 0),  "LEFT"),
        ("ALIGN",   (1, 0), (1, 0),  "RIGHT"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(footer_bottom)

    doc.build(story)
    return output_path
