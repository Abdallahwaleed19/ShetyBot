"""
pdf/generator.py
Exact replica of the official Saudi Sick Leave Report (Seha Platform).

Layout matches Image 1 (reference) exactly:
  ┌─────────────────────────────────────────────────┐
  │ [Seha logo]  │ KSA calligraphy + text │ [mesh]  │  HEADER
  ├─────────────────────────────────────────────────┤
  │            تقرير إجازة مرضية                    │  TITLE
  │              Sick Leave Report                   │
  ├─────────────────────────────────────────────────┤
  │ EN lbl │ EN value │ AR value │ AR lbl │          │  TABLE
  │ ...    │   ...    │   ...    │  ...   │          │
  ├─────────────────────────────────────────────────┤
  │ Verify text (left) │ MOH logo + hosp name (rt)  │  FOOTER
  ├─────────────────────────────────────────────────┤
  │ timestamp (left)   │  NHIC + hosp logo (right)  │  BOTTOM
  └─────────────────────────────────────────────────┘
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

# ── Static assets ──────────────────────────────────────────────────────────────
_ASSETS          = Path(__file__).parent / "assets"
_KSA_CALLIGRAPHY = _ASSETS / "ksa_calligraphy.png"
_GEOMETRIC_MESH  = _ASSETS / "geometric_mesh.png"
_SEHA_LOGO       = _ASSETS / "seha_logo.png"
_MOH_LOGO        = _ASSETS / "moh_logo.png"
_NHIC_LOGO       = _ASSETS / "nhic_logo.png"

# ── Fonts ──────────────────────────────────────────────────────────────────────
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

# ── Colors ─────────────────────────────────────────────────────────────────────
C_DARK_BLUE  = colors.HexColor("#1B3A6B")
C_TEAL       = colors.HexColor("#1A7898")
C_LABEL_TEXT = colors.HexColor("#1A5276")
C_LABEL_BG   = colors.HexColor("#D6E4F0")
C_ALT_BG     = colors.HexColor("#EBF3FA")
C_LINK       = colors.HexColor("#1155CC")
C_GREY_TEXT  = colors.HexColor("#444444")
C_GREY_LINE  = colors.HexColor("#BBBBBB")
WHITE        = colors.white
BLACK        = colors.black

# ── Arabic helpers ─────────────────────────────────────────────────────────────
def ar(text: str) -> str:
    if not text:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)

def has_ar(text) -> bool:
    return any('\u0600' <= c <= '\u06FF' for c in str(text or ""))

# ── Paragraph factory ──────────────────────────────────────────────────────────
def _p(text, font, sz, color=BLACK, align=TA_LEFT, lh=1.3) -> Paragraph:
    return Paragraph(
        str(text or ""),
        ParagraphStyle(
            "x", fontName=font, fontSize=sz, textColor=color,
            alignment=align, leading=sz * lh, spaceBefore=0, spaceAfter=0,
        )
    )

def en(text, sz=9, color=BLACK, align=TA_LEFT):
    return _p(text, _EN, sz, color, align)

def arabic(text, sz=9, color=BLACK, align=TA_RIGHT):
    return _p(ar(text), _AR, sz, color, align)

def smart(text, sz=9, color=BLACK):
    s = str(text or "")
    if has_ar(s):
        return _p(ar(s), _AR, sz, color, TA_RIGHT)
    return _p(s, _EN, sz, color, TA_CENTER)

# ── Image helper ───────────────────────────────────────────────────────────────
def _img(path, w, h) -> object:
    p = Path(str(path))
    if p.exists():
        try:
            return RLImage(str(p), width=w, height=h, kind="proportional")
        except Exception:
            pass
    return en("", 7)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
def generate_pdf(data: dict, output_path) -> Path:
    output_path = Path(output_path)
    PAGE_W, PAGE_H = A4          # 595.27 x 841.89 pt
    M = 1.4 * cm                 # page margin

    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=M, rightMargin=M,
        topMargin=M, bottomMargin=M,
    )
    W = PAGE_W - 2 * M           # usable width ≈ 18.3 cm
    story = []

    # ── Extract fields ────────────────────────────────────────────────────────
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
    # Hospital uploaded logo path (dynamic, from user)
    hosp_logo_path = data.get("hospital_logo_path", "")

    dur_en_val = f"{dur} day(s)  ( {ad_g} to {dd_g} )"
    dur_ar_val = f"{ar(dur)} يوم  ( {ar(dd_h)} الى {ar(ad_h)} )"

    # ══════════════════════════════════════════════════════════════
    # 1. HEADER — Seha(L) | KSA calligraphy(C) | Mesh(R)
    # ══════════════════════════════════════════════════════════════
    seha_cell = _img(_SEHA_LOGO,       3.5*cm, 2.5*cm)   # prominent, left
    ksa_img   = _img(_KSA_CALLIGRAPHY, 4.5*cm, 1.7*cm)
    mesh_cell = _img(_GEOMETRIC_MESH,  5.0*cm, 3.0*cm)   # large, fills top-right

    ksa_block = [
        ksa_img,
        Spacer(1, 1*mm),
        en("Kingdom of Saudi Arabia", 8, C_DARK_BLUE, TA_CENTER),
    ]

    hdr = Table(
        [[seha_cell, ksa_block, mesh_cell]],
        colWidths=[W * 0.27, W * 0.46, W * 0.27],
    )
    hdr.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN",         (0,0), (0,0),   "LEFT"),
        ("ALIGN",         (1,0), (1,0),   "CENTER"),
        ("ALIGN",         (2,0), (2,0),   "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 7*mm))

    # ══════════════════════════════════════════════════════════════
    # 2. TITLE
    # ══════════════════════════════════════════════════════════════
    story.append(arabic("تقرير إجازة مرضية", 18, C_TEAL,      TA_CENTER))
    story.append(Spacer(1, 1.5*mm))
    story.append(en    ("Sick Leave Report",  13, C_DARK_BLUE, TA_CENTER))
    story.append(Spacer(1, 7*mm))

    # ══════════════════════════════════════════════════════════════
    # 3. DATA TABLE  [EN label | EN value | AR value | AR label]
    # ══════════════════════════════════════════════════════════════
    CL = W * 0.185   # label columns (narrow, ~19%)
    CV = W * 0.315   # value columns (wide,  ~31%)

    BASE = [
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("RIGHTPADDING",  (0,0), (-1,-1), 5),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("GRID",          (0,0), (-1,-1), 0.5, C_GREY_LINE),
        # label column backgrounds
        ("BACKGROUND",    (0,0), (0,-1),  C_LABEL_BG),
        ("BACKGROUND",    (3,0), (3,-1),  C_LABEL_BG),
    ]

    def lbl_en(t): return en(t,     8.5, C_LABEL_TEXT, TA_CENTER)
    def lbl_ar(t): return arabic(t, 8.5, C_LABEL_TEXT, TA_RIGHT)

    rows_spec = [
        # (cells, span_value_cols_1_2, bg_override)
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

    tdata  = []
    extras = []
    for i, (row, span, bg) in enumerate(rows_spec):
        tdata.append(row)
        if span:
            extras += [("SPAN", (1,i), (2,i)), ("ALIGN", (1,i), (2,i), "CENTER")]
        if bg is not None:
            if bg == C_DARK_BLUE:
                extras += [
                    ("BACKGROUND", (0,i), (-1,i), C_DARK_BLUE),
                    ("TEXTCOLOR",  (0,i), (-1,i), WHITE),
                ]
            else:
                extras.append(("BACKGROUND", (1,i), (2,i), bg))

    tbl = Table(tdata, colWidths=[CL, CV, CV, CL])
    tbl.setStyle(TableStyle(BASE + extras))
    story.append(tbl)
    story.append(Spacer(1, 7*mm))

    # ══════════════════════════════════════════════════════════════
    # 4. FOOTER  (matches Image 1 exactly)
    # LEFT col : Arabic verify text + English + blank line + URL
    # RIGHT col: MOH logo (large) + "Ministry of Health" + hosp names
    # ══════════════════════════════════════════════════════════════
    verify_ar  = "للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة الرسمي"
    verify_en  = "To check the report please visit Seha's offical website"
    verify_url = "www.seha.sa/#/inquiries/slenquiry"

    footer_left = [
        arabic(verify_ar,  7.5, C_GREY_TEXT, TA_RIGHT),
        Spacer(1, 1*mm),
        en(verify_en,      7.5, C_GREY_TEXT, TA_LEFT),
        Spacer(1, 3*mm),
        en(verify_url,     8,   C_LINK,      TA_LEFT),
    ]

    moh_img = _img(_MOH_LOGO, 2.5*cm, 2.5*cm)
    footer_right = [
        moh_img,
        Spacer(1, 1.5*mm),
        arabic(h_ar_s,         11, C_DARK_BLUE, TA_RIGHT),
        en(h_en_s,              9, C_DARK_BLUE, TA_RIGHT),
    ]

    footer = Table(
        [[footer_left, footer_right]],
        colWidths=[W * 0.52, W * 0.48],
    )
    footer.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "TOP"),
        ("ALIGN",         (1,0), (1,0),   "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("LEFTPADDING",   (0,0), (-1,-1), 0),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))
    story.append(footer)
    story.append(Spacer(1, 5*mm))

    # ══════════════════════════════════════════════════════════════
    # 5. BOTTOM ROW
    # LEFT : timestamp
    # RIGHT: NHIC logo + hospital uploaded logo (side by side)
    #        → same row height, no stacking, page stays compact
    # ══════════════════════════════════════════════════════════════
    ts_text = f"{iss_t}\n{iss_g}"

    nhic_img = _img(_NHIC_LOGO, 2.8*cm, 1.1*cm)

    # Build right-side: NHIC always, + hospital logo if uploaded
    if hosp_logo_path and Path(hosp_logo_path).exists():
        hosp_img  = _img(hosp_logo_path, 1.8*cm, 1.8*cm)
        right_row = [[nhic_img, hosp_img]]
        right_col_widths = [W * 0.27, W * 0.21]
    else:
        right_row = [[nhic_img]]
        right_col_widths = [W * 0.48]

    nhic_tbl = Table(right_row, colWidths=right_col_widths)
    nhic_tbl.setStyle(TableStyle([
        ("VALIGN",        (0,0), (-1,-1), "BOTTOM"),
        ("ALIGN",         (0,0), (-1,-1), "RIGHT"),
        ("TOPPADDING",    (0,0), (-1,-1), 0),
        ("BOTTOMPADDING", (0,0), (-1,-1), 0),
        ("LEFTPADDING",   (0,0), (-1,-1), 2),
        ("RIGHTPADDING",  (0,0), (-1,-1), 0),
    ]))

    bottom = Table(
        [[en(ts_text, 8, C_GREY_TEXT, TA_LEFT), nhic_tbl]],
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
