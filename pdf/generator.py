"""
pdf/generator.py
Exact replica of the official Saudi Sick Leave Report (Seha Platform).

HEADER (3 cols):
  LEFT   → Seha logo (static, large)
  CENTER → KSA calligraphy image + "Kingdom of Saudi Arabia"
  RIGHT  → Geometric mesh image (top-right corner style)

TITLE:
  تقرير إجازة مرضية  (teal, large)
  Sick Leave Report   (dark-blue, medium)

DATA TABLE (4 cols):
  [EN label | EN value | AR value | AR label]
  Label cols: light-blue background, blue text
  Leave Duration row: full dark-blue, white text
  Alternating row tints on value cols

FOOTER (2 cols):
  LEFT  → Arabic verify text + English + URL
  RIGHT → وزارة الصحة logo + text + hospital name

BOTTOM (2 cols):
  LEFT  → timestamp (time \n date)
  RIGHT → NHIC logo  (+ uploaded hospital logo if provided)
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

# ── Static assets ─────────────────────────────────────────────────────────────
_ASSETS          = Path(__file__).parent / "assets"
_KSA_CALLIGRAPHY = _ASSETS / "ksa_calligraphy.png"   # KSA Arabic calligraphy
_GEOMETRIC_MESH  = _ASSETS / "geometric_mesh.png"     # blue triangular lines
_SEHA_LOGO       = _ASSETS / "seha_logo.png"          # صحة | Seha logo
_MOH_LOGO        = _ASSETS / "moh_logo.png"           # وزارة الصحة logo
_NHIC_LOGO       = _ASSETS / "nhic_logo.png"          # NHIC logo

# ── Fonts ─────────────────────────────────────────────────────────────────────
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

# ── Colors ────────────────────────────────────────────────────────────────────
C_DARK_BLUE  = colors.HexColor("#1B3A6B")
C_TEAL       = colors.HexColor("#1A7898")
C_LABEL_TEXT = colors.HexColor("#1A5276")
C_LABEL_BG   = colors.HexColor("#D6E4F0")
C_ALT_BG     = colors.HexColor("#EBF3FA")
C_LINK       = colors.HexColor("#1155CC")
C_GREY_TEXT  = colors.HexColor("#444444")
C_GREY_LINE  = colors.HexColor("#CCCCCC")
WHITE        = colors.white
BLACK        = colors.black

# ── Arabic helpers ────────────────────────────────────────────────────────────
def ar(text: str) -> str:
    if not text:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)

def has_ar(text) -> bool:
    return any('\u0600' <= c <= '\u06FF' for c in str(text or ""))

# ── Paragraph factory ─────────────────────────────────────────────────────────
def _p(text, font, sz, color=BLACK, align=TA_LEFT, lh=1.35) -> Paragraph:
    st = ParagraphStyle(
        "x", fontName=font, fontSize=sz, textColor=color,
        alignment=align, leading=sz * lh, spaceBefore=0, spaceAfter=0,
    )
    return Paragraph(str(text or ""), st)

def en(text, sz=9, color=BLACK, align=TA_LEFT):
    return _p(text, _EN, sz, color, align)

def arabic(text, sz=9, color=BLACK, align=TA_RIGHT):
    return _p(ar(text), _AR, sz, color, align)

def smart(text, sz=9, color=BLACK):
    """Arabic font+RTL if text contains Arabic; else EN centered."""
    s = str(text or "")
    if has_ar(s):
        return _p(ar(s), _AR, sz, color, TA_RIGHT)
    return _p(s, _EN, sz, color, TA_CENTER)

# ── Image helper ──────────────────────────────────────────────────────────────
def _img(path, w, h) -> object:
    p = Path(str(path))
    if p.exists():
        try:
            return RLImage(str(p), width=w, height=h, kind="proportional")
        except Exception:
            pass
    return en("", 7)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════
def generate_pdf(data: dict, output_path) -> Path:
    output_path = Path(output_path)
    PAGE_W, PAGE_H = A4
    M = 1.5 * cm                        # page margin

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=M, rightMargin=M, topMargin=M, bottomMargin=M,
    )
    W = PAGE_W - 2 * M                  # usable width ≈ 18.2 cm

    # ── Extract data ──────────────────────────────────────────────────────────
    ad_g      = data.get("admission_date_gregorian", "")
    ad_h      = data.get("admission_date_hijri", "")
    dd_g      = data.get("discharge_date_gregorian", "")
    dd_h      = data.get("discharge_date_hijri", "")
    iss_g     = data.get("issue_date_gregorian", "")
    iss_t     = data.get("issue_time", "")
    dur       = str(data.get("leave_duration_days", ""))
    h_en_s    = data.get("hospital_name_en", "")
    h_ar_s    = data.get("hospital_name_ar", "")
    p_en_s    = data.get("practitioner_name_en", "")
    p_ar_s    = data.get("practitioner_name_ar", "")
    pos_en    = data.get("practitioner_position_en", "")
    pos_ar    = data.get("practitioner_position_ar", "")
    nat       = data.get("nationality", "")
    emp       = data.get("employer", "")
    nid       = data.get("national_id", "")
    name_en   = data.get("patient_name_en", "")
    name_ar   = data.get("patient_name_ar", "")
    leave_id  = data.get("leave_id", "")
    hosp_logo = data.get("hospital_logo_path", "")

    dur_en_val = f"{dur} day(s)  ( {ad_g} to {dd_g} )"
    dur_ar_val = f"{ar(dur)} يوم  ( {ar(dd_h)} الى {ar(ad_h)} )"

    story = []

    # ══════════════════════════════════════════════════════════════
    # SECTION 1 — HEADER
    # LEFT : Seha logo (large, ~2.8 cm tall)
    # CENTER: KSA calligraphy + "Kingdom of Saudi Arabia"
    # RIGHT : geometric mesh (fills corner)
    # ══════════════════════════════════════════════════════════════
    seha_cell = _img(_SEHA_LOGO,       3.2*cm, 2.8*cm)
    ksa_img   = _img(_KSA_CALLIGRAPHY, 5.0*cm, 1.9*cm)
    mesh_cell = _img(_GEOMETRIC_MESH,  3.8*cm, 2.8*cm)

    ksa_block = [
        ksa_img,
        Spacer(1, 1*mm),
        en("Kingdom of Saudi Arabia", 8, C_DARK_BLUE, TA_CENTER),
    ]

    hdr = Table(
        [[seha_cell, ksa_block, mesh_cell]],
        colWidths=[W * 0.26, W * 0.48, W * 0.26],
    )
    hdr.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",         (0,0), (0,0),   "LEFT"),
        ("ALIGN",         (1,0), (1,0),   "CENTER"),
        ("ALIGN",         (2,0), (2,0),   "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 6*mm))

    # ══════════════════════════════════════════════════════════════
    # SECTION 2 — TITLE
    # ══════════════════════════════════════════════════════════════
    story.append(arabic("تقرير إجازة مرضية", 17, C_TEAL,      TA_CENTER))
    story.append(Spacer(1, 1*mm))
    story.append(en    ("Sick Leave Report",  12, C_DARK_BLUE, TA_CENTER))
    story.append(Spacer(1, 6*mm))

    # ══════════════════════════════════════════════════════════════
    # SECTION 3 — DATA TABLE
    # Columns: [EN label | EN value | AR value | AR label]
    # ══════════════════════════════════════════════════════════════
    CL = W * 0.19   # narrow label column
    CV = W * 0.31   # wide value column

    BASE_STYLE = [
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 5),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("GRID",          (0,0), (-1,-1), 0.5, C_GREY_LINE),
        ("BACKGROUND",    (0,0), (0,-1),  C_LABEL_BG),
        ("BACKGROUND",    (3,0), (3,-1),  C_LABEL_BG),
        ("TEXTCOLOR",     (0,0), (0,-1),  C_LABEL_TEXT),
        ("TEXTCOLOR",     (3,0), (3,-1),  C_LABEL_TEXT),
    ]

    def lbl_en(t): return en(t,     8.5, C_LABEL_TEXT, TA_CENTER)
    def lbl_ar(t): return arabic(t, 8.5, C_LABEL_TEXT, TA_RIGHT)

    # (row_cells, span_value_cols, bg_override)
    rows_spec = [
        ([lbl_en("Leave ID"),
          smart(leave_id, 9), "", lbl_ar("رمز الإجازة")],
         True, None),

        ([en("Leave Duration", 8.5, WHITE, TA_CENTER),
          en(dur_en_val,       8,   WHITE, TA_CENTER),
          arabic(dur_ar_val,   8,   WHITE, TA_RIGHT),
          arabic("مدة الإجازة", 8.5, WHITE, TA_RIGHT)],
         False, C_DARK_BLUE),

        ([lbl_en("Admission Date"),
          smart(ad_g, 8.5), smart(ad_h, 8.5), lbl_ar("تاريخ الدخول")],
         False, None),

        ([lbl_en("Discharge Date"),
          smart(dd_g, 8.5), smart(dd_h, 8.5), lbl_ar("تاريخ الخروج")],
         False, C_ALT_BG),

        ([lbl_en("Issue Date"),
          smart(iss_g, 8.5), "", lbl_ar("تاريخ إصدار التقرير")],
         True, None),

        ([lbl_en("Name"),
          smart(name_en, 8.5), smart(name_ar, 8.5), lbl_ar("الاسم")],
         False, C_ALT_BG),

        ([lbl_en("National ID / Iqama"),
          smart(nid, 8.5), "", lbl_ar("رقم الهوية / الإقامة")],
         True, None),

        ([lbl_en("Nationality"),
          smart(nat, 8.5), smart(nat, 8.5), lbl_ar("الجنسية")],
         False, C_ALT_BG),

        ([lbl_en("Employer"),
          smart(emp, 8.5), smart(emp, 8.5), lbl_ar("جهة العمل")],
         False, None),

        ([lbl_en("Practitioner Name"),
          smart(p_en_s, 8.5), smart(p_ar_s, 8.5), lbl_ar("اسم الممارس")],
         False, C_ALT_BG),

        ([lbl_en("Position"),
          smart(pos_en, 8.5), smart(pos_ar, 8.5), lbl_ar("المسمى الوظيفي")],
         False, None),
    ]

    table_data   = []
    extra_styles = []

    for i, (row, span_mid, bg) in enumerate(rows_spec):
        table_data.append(row)
        if span_mid:
            extra_styles += [
                ("SPAN",  (1, i), (2, i)),
                ("ALIGN", (1, i), (2, i), "CENTER"),
            ]
        if bg is not None:
            if bg == C_DARK_BLUE:
                extra_styles += [
                    ("BACKGROUND", (0, i), (-1, i), C_DARK_BLUE),
                    ("TEXTCOLOR",  (0, i), (-1, i), WHITE),
                ]
            else:
                extra_styles.append(("BACKGROUND", (1, i), (2, i), bg))

    tbl = Table(table_data, colWidths=[CL, CV, CV, CL])
    tbl.setStyle(TableStyle(BASE_STYLE + extra_styles))
    story.append(tbl)
    story.append(Spacer(1, 8*mm))

    # ══════════════════════════════════════════════════════════════
    # SECTION 4 — FOOTER
    # LEFT : verification texts (Arabic right-align, English left)
    # RIGHT: وزارة الصحة logo + text + hospital name
    # ══════════════════════════════════════════════════════════════
    verify_ar  = "للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة الرسمي"
    verify_en  = "To check the report please visit Seha's offical website"
    verify_url = "www.seha.sa/#/inquiries/slenquiry"

    # LEFT column of footer
    footer_left_cells = [
        arabic(verify_ar,  7.5, C_GREY_TEXT, TA_RIGHT),
        en(verify_en,      7.5, C_GREY_TEXT, TA_LEFT),
        Spacer(1, 3*mm),
        en(verify_url,     8,   C_LINK,      TA_LEFT),
    ]

    # RIGHT column of footer — MOH logo + text + hospital name
    moh_logo_cell = _img(_MOH_LOGO, 2.2*cm, 2.2*cm)
    footer_right_cells = [
        moh_logo_cell,
        Spacer(1, 1*mm),
        arabic(h_ar_s,          11, C_DARK_BLUE, TA_RIGHT),
        en(h_en_s,               9, C_DARK_BLUE, TA_RIGHT),
    ]

    footer_tbl = Table(
        [[footer_left_cells, footer_right_cells]],
        colWidths=[W * 0.52, W * 0.48],
    )
    footer_tbl.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("ALIGN",         (1,0), (1,0),   "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))
    story.append(footer_tbl)
    story.append(Spacer(1, 6*mm))

    # ══════════════════════════════════════════════════════════════
    # SECTION 5 — BOTTOM ROW
    # LEFT : timestamp
    # RIGHT: NHIC logo  (+ hospital uploaded logo if provided)
    # ══════════════════════════════════════════════════════════════
    ts_text = f"{iss_t}\n{iss_g}"

    nhic_img = _img(_NHIC_LOGO, 3.0*cm, 1.2*cm)

    # Build right-bottom content
    right_bottom_rows = [[nhic_img]]
    if hosp_logo and Path(hosp_logo).exists():
        hosp_img = _img(hosp_logo, 1.8*cm, 1.8*cm)
        right_bottom_rows.append([hosp_img])

    right_bottom_tbl = Table(right_bottom_rows, colWidths=[W * 0.48])
    right_bottom_tbl.setStyle(TableStyle([
        ("ALIGN",         (0,0), (-1,-1), "RIGHT"),
        ("VALIGN",        (0,0), (-1,-1), "BOTTOM"),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))

    bottom = Table(
        [[en(ts_text, 8, C_GREY_TEXT, TA_LEFT), right_bottom_tbl]],
        colWidths=[W * 0.52, W * 0.48],
    )
    bottom.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "BOTTOM"),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))
    story.append(bottom)

    doc.build(story)
    return output_path
