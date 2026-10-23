"""
pdf/generator.py — Official Saudi Sick Leave Report (Seha Platform) replica.
Uses static assets: ksa_calligraphy.png, geometric_mesh.png, seha_logo.png, nhic_logo.png
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
    Spacer, HRFlowable, Image as RLImage,
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import arabic_reshaper
from bidi.algorithm import get_display

# ── Static asset paths ────────────────────────────────────────────────────────
_ASSETS = Path(__file__).parent / "assets"
_KSA_CALLIGRAPHY = _ASSETS / "ksa_calligraphy.png"
_GEOMETRIC_MESH  = _ASSETS / "geometric_mesh.png"
_SEHA_LOGO       = _ASSETS / "seha_logo.png"
_NHIC_LOGO       = _ASSETS / "nhic_logo.png"

# ── Font registration ─────────────────────────────────────────────────────────
_FONTS_DIR = Path(__file__).parent / "fonts"
_FONTS_DIR.mkdir(exist_ok=True)

def _try_register(name: str, *candidates) -> str:
    for path in candidates:
        p = Path(str(path))
        if p.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(p)))
                return name
            except Exception:
                pass
    return "Helvetica"

_AR = _try_register(
    "AR",
    "/usr/share/fonts/truetype/fonts-hosny-amiri/Amiri-Regular.ttf",
    "/usr/share/fonts/truetype/amiri/Amiri-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    _FONTS_DIR / "Arabic.ttf",
)
_EN = _try_register(
    "EN",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    _FONTS_DIR / "Latin.ttf",
)

# ── Color palette ─────────────────────────────────────────────────────────────
C_DARK_BLUE  = colors.HexColor("#1B3A6B")
C_TEAL       = colors.HexColor("#1A6B8A")
C_LABEL_TEXT = colors.HexColor("#1A5276")
C_LABEL_BG   = colors.HexColor("#D6E4F0")
C_ALT_BG     = colors.HexColor("#EBF3FA")
C_LINK       = colors.HexColor("#2874A6")
C_GREY_LINE  = colors.HexColor("#CCCCCC")
C_GREY_TEXT  = colors.HexColor("#666666")
WHITE        = colors.white
BLACK        = colors.black

# ── Arabic shaping ────────────────────────────────────────────────────────────
def ar(text) -> str:
    if not text:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)

def has_ar(text) -> bool:
    return any('\u0600' <= c <= '\u06FF' for c in str(text or ""))

# ── Paragraph factories ───────────────────────────────────────────────────────
def _p(text, font, sz, color=BLACK, align=TA_LEFT, leading_ratio=1.4) -> Paragraph:
    st = ParagraphStyle(
        "x", fontName=font, fontSize=sz, textColor=color,
        alignment=align, leading=sz * leading_ratio, spaceBefore=0, spaceAfter=0,
    )
    return Paragraph(str(text or ""), st)

def en(text, sz=9, color=BLACK, align=TA_LEFT):
    return _p(text, _EN, sz, color, align)

def arabic(text, sz=9, color=BLACK, align=TA_RIGHT):
    return _p(ar(text), _AR, sz, color, align)

def smart(text, sz=9, color=BLACK):
    """Render using Arabic font+RTL if text contains Arabic chars, else LTR."""
    s = str(text or "")
    if has_ar(s):
        return _p(ar(s), _AR, sz, color, TA_RIGHT)
    return _p(s, _EN, sz, color, TA_CENTER)

def _img(path, w, h) -> object:
    """Load image or return empty string if missing."""
    p = Path(str(path))
    if p.exists():
        try:
            return RLImage(str(p), width=w, height=h, kind="proportional")
        except Exception:
            pass
    return en("", 8)


# ── Main PDF generator ────────────────────────────────────────────────────────
def generate_pdf(data: dict, output_path) -> Path:
    output_path = Path(output_path)
    PAGE_W, PAGE_H = A4
    M = 1.4 * cm

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=M,
    )
    story = []
    W = PAGE_W - 2 * M   # usable width

    # ── Unpack data ───────────────────────────────────────────────────────────
    ad_g    = data.get("admission_date_gregorian", "")
    ad_h    = data.get("admission_date_hijri", "")
    dd_g    = data.get("discharge_date_gregorian", "")
    dd_h    = data.get("discharge_date_hijri", "")
    iss_g   = data.get("issue_date_gregorian", "")
    iss_h   = data.get("issue_date_hijri", "")
    iss_t   = data.get("issue_time", "")
    dur     = str(data.get("leave_duration_days", ""))
    h_en    = data.get("hospital_name_en", "")
    h_ar    = data.get("hospital_name_ar", "")
    p_en    = data.get("practitioner_name_en", "")
    p_ar    = data.get("practitioner_name_ar", "")
    pos_en  = data.get("practitioner_position_en", "")
    pos_ar  = data.get("practitioner_position_ar", "")
    nat     = data.get("nationality", "")
    emp     = data.get("employer", "")
    nid     = data.get("national_id", "")
    name_en = data.get("patient_name_en", "")
    name_ar = data.get("patient_name_ar", "")
    leave_id = data.get("leave_id", "")

    # Leave Duration formatted strings
    dur_en_val = f"{dur} day(s)  ( {ad_g} to {dd_g} )"
    dur_ar_val = f"{ar(dur)} يوم  ( {ar(dd_h)} الى {ar(ad_h)} )"

    # ── HEADER ────────────────────────────────────────────────────────────────
    # LEFT: hospital logo (dynamic, user-uploaded) OR Seha logo as fallback
    logo_path = data.get("hospital_logo_path", "")
    if logo_path and Path(logo_path).exists():
        left_logo = _img(logo_path, 2.5*cm, 2.5*cm)
    else:
        left_logo = _img(_SEHA_LOGO, 2.8*cm, 1.2*cm)

    # CENTER: KSA calligraphy image + "Kingdom of Saudi Arabia" text
    ksa_img   = _img(_KSA_CALLIGRAPHY, 5.5*cm, 2.0*cm)
    ksa_block = [ksa_img, en("Kingdom of Saudi Arabia", 8, C_DARK_BLUE, TA_CENTER)]

    # RIGHT: geometric mesh image (decorative)
    mesh_img = _img(_GEOMETRIC_MESH, 3.5*cm, 2.5*cm)

    header_tbl = Table(
        [[left_logo, ksa_block, mesh_img]],
        colWidths=[W * 0.25, W * 0.50, W * 0.25],
    )
    header_tbl.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",         (0,0), (0,0),   "LEFT"),
        ("ALIGN",         (1,0), (1,0),   "CENTER"),
        ("ALIGN",         (2,0), (2,0),   "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(header_tbl)
    story.append(Spacer(1, 5*mm))

    # ── TITLE ─────────────────────────────────────────────────────────────────
    story.append(arabic("تقرير إجازة مرضية", 15, C_TEAL, TA_CENTER))
    story.append(en("Sick Leave Report",     11, C_DARK_BLUE, TA_CENTER))
    story.append(Spacer(1, 5*mm))

    # ── MAIN TABLE ────────────────────────────────────────────────────────────
    # Column widths: [EN label | EN value | AR value | AR label]
    CL = W * 0.20   # label columns (narrow)
    CV = W * 0.30   # value columns (wide)

    PAD = [
        ("TOPPADDING",    (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 5),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("GRID",          (0,0), (-1,-1), 0.4, C_GREY_LINE),
    ]

    LABEL_STYLE = [
        ("BACKGROUND", (0,0), (0,-1), C_LABEL_BG),
        ("BACKGROUND", (3,0), (3,-1), C_LABEL_BG),
    ]

    def lbl_en(t): return en(t,     8.5, C_LABEL_TEXT, TA_CENTER)
    def lbl_ar(t): return arabic(t, 8.5, C_LABEL_TEXT, TA_RIGHT)

    # ── Row definitions ───────────────────────────────────────────────────────
    # (row_data, span_cols_1_2, bg_override)
    rows_spec = [
        # Leave ID — centered span
        ([lbl_en("Leave ID"), smart(leave_id, 9), "", lbl_ar("رمز الإجازة")],
         True, None),

        # Leave Duration — dark blue full row
        ([
            en("Leave Duration", 8, WHITE, TA_CENTER),
            en(dur_en_val,       7.5, WHITE, TA_CENTER),
            arabic(dur_ar_val,   7.5, WHITE, TA_RIGHT),
            arabic("مدة الإجازة", 8, WHITE, TA_RIGHT),
         ], False, C_DARK_BLUE),

        # Admission Date
        ([lbl_en("Admission Date"), smart(ad_g, 8.5), smart(ad_h, 8.5), lbl_ar("تاريخ الدخول")],
         False, None),

        # Discharge Date (alt)
        ([lbl_en("Discharge Date"), smart(dd_g, 8.5), smart(dd_h, 8.5), lbl_ar("تاريخ الخروج")],
         False, C_ALT_BG),

        # Issue Date — centered span
        ([lbl_en("Issue Date"), smart(iss_g, 8.5), "", lbl_ar("تاريخ إصدار التقرير")],
         True, None),

        # Name (alt)
        ([lbl_en("Name"), smart(name_en, 8.5), smart(name_ar, 8.5), lbl_ar("الاسم")],
         False, C_ALT_BG),

        # National ID — centered span
        ([lbl_en("National ID / Iqama"), smart(nid, 8.5), "", lbl_ar("رقم الهوية / الإقامة")],
         True, None),

        # Nationality (alt)
        ([lbl_en("Nationality"), smart(nat, 8.5), smart(nat, 8.5), lbl_ar("الجنسية")],
         False, C_ALT_BG),

        # Employer
        ([lbl_en("Employer"), smart(emp, 8.5), smart(emp, 8.5), lbl_ar("جهة العمل")],
         False, None),

        # Practitioner Name (alt)
        ([lbl_en("Practitioner Name"), smart(p_en, 8.5), smart(p_ar, 8.5), lbl_ar("اسم الممارس")],
         False, C_ALT_BG),

        # Position
        ([lbl_en("Position"), smart(pos_en, 8.5), smart(pos_ar, 8.5), lbl_ar("المسمى الوظيفي")],
         False, None),
    ]

    table_data   = []
    extra_styles = []

    for i, (row, span_mid, bg) in enumerate(rows_spec):
        table_data.append(row)

        if span_mid:
            extra_styles.append(("SPAN",  (1, i), (2, i)))
            extra_styles.append(("ALIGN", (1, i), (2, i), "CENTER"))

        if bg is not None:
            if bg == C_DARK_BLUE:
                extra_styles.append(("BACKGROUND", (0, i), (-1, i), C_DARK_BLUE))
                extra_styles.append(("TEXTCOLOR",  (0, i), (-1, i), WHITE))
            else:
                extra_styles.append(("BACKGROUND", (1, i), (2, i), bg))

    tbl = Table(table_data, colWidths=[CL, CV, CV, CL])
    tbl.setStyle(TableStyle(PAD + LABEL_STYLE + extra_styles))
    story.append(tbl)
    story.append(Spacer(1, 6*mm))

    # ── FOOTER ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_GREY_LINE))
    story.append(Spacer(1, 3*mm))

    verify_ar  = "للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة الرسمي"
    verify_en  = "To check the report please visit Seha's official website"
    verify_url = "www.seha.sa/#/inquiries/slenquiry"

    left_col = [
        arabic(verify_ar,  7.5, C_GREY_TEXT, TA_LEFT),
        en(verify_en,      7.5, C_GREY_TEXT, TA_LEFT),
        en(verify_url,     7.5, C_LINK,      TA_LEFT),
    ]

    right_col = [
        arabic("وزارة الصحة",    9, C_DARK_BLUE, TA_RIGHT),
        en("Ministry of Health",  8, C_DARK_BLUE, TA_RIGHT),
        arabic(h_ar,              8, C_DARK_BLUE, TA_RIGHT),
        en(h_en,                  8, C_DARK_BLUE, TA_RIGHT),
    ]

    footer_tbl = Table(
        [[left_col, right_col]],
        colWidths=[W * 0.58, W * 0.42],
    )
    footer_tbl.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(footer_tbl)
    story.append(Spacer(1, 5*mm))

    # ── BOTTOM ROW: timestamp (left) | NHIC logo + text (right) ──────────────
    ts = f"{iss_t}\n{iss_g}"
    nhic_logo_cell = _img(_NHIC_LOGO, 3.5*cm, 1.0*cm)

    bottom = Table(
        [[en(ts, 8, BLACK, TA_LEFT), nhic_logo_cell]],
        colWidths=[W * 0.5, W * 0.5],
    )
    bottom.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "BOTTOM"),
        ("ALIGN",         (1,0), (1,0),   "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
    ]))
    story.append(bottom)

    doc.build(story)
    return output_path
