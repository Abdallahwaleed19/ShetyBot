"""
pdf/generator.py — Seha Sick Leave Report
Pixel-matched to the official reference (B5: 842×1190pt ≈ 297×420mm).

Reference analysis (from DOC-20260703-WA0005.pdf):
  Page       : 842.25 × 1190.25 pt  (B5 landscape-long)
  Margin L/R : ~36 pt (≈1.27cm)
  Header imgs: xref91=mesh(top-right 543-806, 36-143), xref92=seha(36-186,36-102),
               xref90=ksa_calligraphy(288-551,36-160)
  Titles     : "Kingdom of Saudi Arabia" y=104, sz=17.2, color=#000000
               "تقرير إجازة مرضية" y=150, sz=22.5, bold, color=#306db5
               "Sick Leave Report"  y=194, sz=19.7, bold, color=#2e3f7b
  Table      : xref89, y=235-709  ← entire table is an image in original
               EN labels bold #366fb5 sz=13.5; AR labels bold #366fb5 sz=13.5
               Values #2c3e77 sz=13.5; Leave Duration row: white text on #2c3e77 bg
  Footer     : QR xref127 (170-283, 719-832)
               Ministry logo xref96 (563-685, 733-844)
               NHIC logo xref95 (655-806, 934-1006)
               verify text y≈831-909; time y=945; date y=982
  Colors     : Label blue #366fb5, value blue #2c3e77, dark row #2c3e77, link #153bc2
"""
from __future__ import annotations

import io
import os
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import B5          # 499×709pt — WRONG, we need landscape-long B5
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
pt = 1.0   # 1 point = 1 ReportLab unit
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

import arabic_reshaper
from bidi.algorithm import get_display

# ── Page size — B5 portrait as in reference: 842.25 × 1190.25 pt ───────────────
# reportlab B5 = (498.9, 708.7) — that's standard B5
# Reference is ISO B5 = 176×250mm but the extracted is 297×420mm = A3!
# Actually 842.25pt = 842.25/72*25.4 = 297.1mm, 1190.25pt = 419.9mm → this is A3!
# Wait — let me re-check: A3 = 297×420mm ✓
PAGE_W = 842.25 * pt   # ≈ 297mm  (A3 width)
PAGE_H = 1190.25 * pt  # ≈ 420mm  (A3 height)

# Reference measurements (in points, y from TOP since PDF y=0 is bottom)
# We'll work top-down: y_from_top = PAGE_H - y_pdf
MAR_L = 36 * pt    # left margin
MAR_R = 36 * pt    # right margin  
MAR_T = 36 * pt    # top margin
MAR_B = 36 * pt    # bottom margin

USABLE_W = PAGE_W - MAR_L - MAR_R   # ≈ 770pt

# ── Static assets ───────────────────────────────────────────────────────────────
_ASSETS          = Path(__file__).parent / "assets"
_KSA_CALLIGRAPHY = _ASSETS / "ksa_calligraphy.png"
_GEOMETRIC_MESH  = _ASSETS / "geometric_mesh.png"
_SEHA_LOGO       = _ASSETS / "seha_logo.png"
_MOH_LOGO        = _ASSETS / "moh_logo.png"
_NHIC_LOGO       = _ASSETS / "nhic_logo.png"

# ── Fonts ────────────────────────────────────────────────────────────────────────
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
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    _FONTS_DIR / "Arabic.ttf",
)
_ARB = _try_register(
    "ARB",
    "/usr/share/fonts/truetype/fonts-hosny-amiri/Amiri-Bold.ttf",
    "/usr/share/fonts/truetype/amiri/Amiri-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
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
_ENB = _try_register(
    "ENB",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    _FONTS_DIR / "Latin.ttf",
)

# ── Exact colors from reference ──────────────────────────────────────────────────
C_LABEL   = colors.HexColor("#366fb3")   # EN/AR label text (bold blue)
C_VALUE   = colors.HexColor("#2a3c76")   # cell values (dark blue)
C_DARK    = colors.HexColor("#2c3e77")   # Leave Duration row bg  
C_TITLE   = colors.HexColor("#2e6cb3")   # Arabic title
C_TITLE_EN= colors.HexColor("#2d3e7a")   # English title
C_LINK    = colors.HexColor("#153bc2")   # URL link
C_GREY    = colors.HexColor("#555555")   # verify text
C_LBLBG   = colors.HexColor("#ffffff")   # label column background
C_ALTBG   = colors.HexColor("#f7f7f7")   # alt row background (soft grey in original)
C_BORDER  = colors.HexColor("#dedede")   # table border (crisp light grey)
C_DIVIDER = colors.HexColor("#c8c8c8")   # vertical divider in footer
WHITE     = colors.white
BLACK     = colors.black


# ── Arabic helpers ───────────────────────────────────────────────────────────────
def ar(text: str) -> str:
    if not text:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)


def has_ar(text) -> bool:
    return any("\u0600" <= c <= "\u06FF" for c in str(text or ""))


def _p(text, font, sz, color=BLACK, align=TA_LEFT, lh=1.2) -> Paragraph:
    return Paragraph(
        str(text or ""),
        ParagraphStyle(
            "x",
            fontName=font,
            fontSize=sz,
            textColor=color,
            alignment=align,
            leading=sz * lh,
            spaceBefore=0,
            spaceAfter=0,
            wordWrap="LTR" if align == TA_LEFT else "RTL",
        ),
    )


def en(text, sz=9.5, color=BLACK, align=TA_LEFT):
    return _p(str(text or ""), _EN, sz, color, align)


def enb(text, sz=9.5, color=BLACK, align=TA_LEFT):
    return _p(str(text or ""), _ENB if _ENB else _EN, sz, color, align)


def arabic(text, sz=9.5, color=BLACK, align=TA_RIGHT):
    return _p(ar(text), _AR, sz, color, align)


def arb(text, sz=9.5, color=BLACK, align=TA_RIGHT):
    return _p(ar(text), _ARB if _ARB else _AR, sz, color, align)


# ── Image helpers ────────────────────────────────────────────────────────────────
def _crop_content(im: PILImage.Image, alpha_thr: int = 15) -> PILImage.Image:
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > alpha_thr:
                xs.append(x); ys.append(y)
    if not xs:
        return im
    pad = 3
    return im.crop((max(0,min(xs)-pad), max(0,min(ys)-pad),
                    min(w,max(xs)+pad+1), min(h,max(ys)+pad+1)))


def _reader(path) -> ImageReader | None:
    p = Path(str(path or ""))
    if not p.exists():
        return None
    try:
        im = _crop_content(PILImage.open(p))
        buf = BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


def _fit(path, max_w, max_h) -> RLImage | None:
    """Return RLImage fitted proportionally into max_w × max_h box."""
    p = Path(str(path or ""))
    if not p.exists():
        return None
    try:
        im = _crop_content(PILImage.open(p))
        iw, ih = im.size
        if iw <= 0 or ih <= 0:
            return None
        scale = min(max_w / iw, max_h / ih)
        buf = BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        img = RLImage(buf, width=iw * scale, height=ih * scale)
        img.hAlign = "CENTER"
        return img
    except Exception:
        return None


def _draw_img(c, reader, x, y, max_w, max_h, anchor="sw"):
    """Draw image onto canvas, fitted in max_w×max_h. anchor: sw|ne|se|n|c"""
    if reader is None:
        return 0, 0
    iw, ih = reader.getSize()
    if iw <= 0 or ih <= 0:
        return 0, 0
    scale = min(max_w / iw, max_h / ih)
    w, h = iw * scale, ih * scale
    if anchor == "ne":
        x, y = x - w, y - h
    elif anchor == "se":
        x, y = x - w, y
    elif anchor == "n":
        x, y = x - w / 2, y - h
    elif anchor == "c":
        x, y = x - w / 2, y - h / 2
    elif anchor == "nw":
        y = y - h
    c.drawImage(reader, x, y, width=w, height=h, mask="auto")
    return w, h


# ══════════════════════════════════════════════════════════════════════════════════
def generate_pdf(data: dict, output_path) -> Path:
    output_path = Path(output_path)

    # ── Unpack data ────────────────────────────────────────────────────────────
    def _norm(d):
        if not d:
            return ""
        return str(d).strip().replace("/", "-")

    ad_g      = _norm(data.get("admission_date_gregorian", ""))
    ad_h      = _norm(data.get("admission_date_hijri", ""))
    dd_g      = _norm(data.get("discharge_date_gregorian", ""))
    dd_h      = _norm(data.get("discharge_date_hijri", ""))
    iss_g     = _norm(data.get("issue_date_gregorian", ""))
    iss_long  = data.get("issue_date_long", iss_g)    # "Friday ،3 July 2026"
    if iss_long:
        iss_long = str(iss_long).replace(" ,", " ،").replace(",", " ،").replace("  ", " ")
    iss_t     = data.get("issue_time", "")             # "6:20 PM"
    dur       = str(data.get("leave_duration_days", ""))
    h_en      = (data.get("hospital_name_en", "") or "").strip()
    h_ar      = (data.get("hospital_name_ar", "") or "").strip()
    p_en      = data.get("practitioner_name_en", "")
    p_ar      = data.get("practitioner_name_ar", "")
    pos_en    = data.get("practitioner_position_en", "")
    pos_ar    = data.get("practitioner_position_ar", "")
    nat_ar    = data.get("nationality", "")
    nat_en    = data.get("nationality_en", "")
    emp_ar    = data.get("employer", "")
    emp_en    = data.get("employer_en", "")
    nid       = data.get("national_id", "")
    name_en   = data.get("patient_name_en", "")
    name_ar   = data.get("patient_name_ar", "")
    leave_id  = data.get("leave_id", "")
    hosp_logo = data.get("hospital_logo_path", "")
    with_qr   = data.get("include_barcode", False)

    # Duration display strings — match reference: "1 day (03-07-2026 to 03-07-2026)"
    day_word = "day" if dur == "1" else "days"
    dur_en   = f"{dur} {day_word} ({ad_g} to {dd_g})"
    dur_ar   = f"{ar(dur)} يوم ({ar(ad_h)} الى {ar(dd_h)})"

    # ── Load images ─────────────────────────────────────────────────────────────
    seha_r = _reader(_SEHA_LOGO)
    ksa_r  = _reader(_KSA_CALLIGRAPHY)
    mesh_r = _reader(_GEOMETRIC_MESH)
    nhic_r = _reader(_NHIC_LOGO)
    logo_src = hosp_logo if hosp_logo and Path(str(hosp_logo)).exists() else str(_MOH_LOGO)
    logo_r   = _reader(logo_src)

    # ── Canvas callback: header + bottom elements (fixed positions) ──────────────
    def on_page(c, doc):
        c.saveState()
        H = PAGE_H  # total page height in points

        # ── GEOMETRIC MESH — top-right corner ─────────────────────────────────
        # Reference: rect(543, 36, 806, 143)
        mesh_w_ref = 806 - 543   # ≈ 263pt
        mesh_h_ref = 143 - 36    # ≈ 107pt
        _draw_img(c, mesh_r,
                  PAGE_W - MAR_R - 10, H - MAR_T - 5,
                  mesh_w_ref, mesh_h_ref,
                  anchor="ne")

        # ── SEHA LOGO — top-left ───────────────────────────────────────────────
        # Reference: rect(36, 36, 186, 102) → 150×66pt
        _draw_img(c, seha_r,
                  MAR_L + 10, H - MAR_T - 5,
                  150, 66,
                  anchor="nw")

        # ── KSA CALLIGRAPHY — center top ──────────────────────────────────────
        # Reference: rect(288, 36, 551, 160) → center of page at top
        ksa_w_ref = 551 - 288    # ≈ 263pt
        ksa_h_ref = 160 - 36     # ≈ 124pt
        _draw_img(c, ksa_r,
                  PAGE_W / 2, H - MAR_T - 5,
                  ksa_w_ref, ksa_h_ref,
                  anchor="n")

        # "Kingdom of Saudi Arabia" — directly under KSA calligraphy
        # Reference: y≈104 from top (calligraphy bottom is at 160, text is at ~170)
        ksa_bottom_y = H - 150   # bottom of KSA calligraphy in pdf coords
        c.setFillColor(BLACK)
        c.setFont(_ENB if _ENB else "Helvetica-Bold", 11)
        c.drawCentredString(PAGE_W / 2, ksa_bottom_y - 12, "Kingdom of Saudi Arabia")

        # ── TIME & DATE — bottom left (footer in story, not canvas) ─────────────
        # Moved to story for better positioning control

        c.restoreState()

    # ── Build story (flowable content) ──────────────────────────────────────────
    # Top margin covers header area (~200pt). Footer fully in story → small bottom margin.
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=(PAGE_W, PAGE_H),
        leftMargin=MAR_L,
        rightMargin=MAR_R,
        topMargin=158 * pt,
        bottomMargin=36 * pt,   # minimal — all footer content is in the story
    )

    story = []
    BODY_W = USABLE_W  # 770pt

    # ── TITLES ─────────────────────────────────────────────────────────────────
    story.append(arb("تقرير إجازة مرضية", 23, C_TITLE, TA_CENTER))
    story.append(Spacer(1, 6 * pt))
    story.append(enb("Sick Leave Report", 19.5, C_TITLE_EN, TA_CENTER))
    story.append(Spacer(1, 16 * pt))

    # ── DATA TABLE ──────────────────────────────────────────────────────────────
    CL_EN = BODY_W * 0.18
    CV    = BODY_W * 0.29
    CV2   = BODY_W * 0.29
    CL_AR = BODY_W * 0.24

    LSZ = 11.0   # label font size
    VSZ = 11.0   # value font size
    NSZ = 10.0   # smaller for long names

    def lbl_e(t):
        return enb(t, LSZ, C_LABEL, TA_CENTER)

    def lbl_a(t):
        return arb(t, LSZ, C_LABEL, TA_CENTER)

    def val_e(t, sz=VSZ):
        return en(str(t or ""), sz, C_VALUE, TA_CENTER)

    def val_a(t, sz=VSZ):
        return arabic(str(t or ""), sz, C_VALUE, TA_CENTER)

    ROW_H = 41.5 * pt

    LSZ = 11.5   # label font size
    VSZ = 11.0   # value font size
    NSZ = 10.0   # smaller for long names

    rows = [
        (lbl_e("Leave ID"),            val_e(leave_id),       "",                     lbl_a("رمز الإجازة"),           True,  False),
        (enb("Leave Duration", LSZ, WHITE, TA_CENTER),
                                       en(dur_en, 9.5, WHITE, TA_CENTER),
                                                              arabic(dur_ar, 10.0, WHITE, TA_CENTER),
                                                                                      arb("مدة الإجازة", LSZ, WHITE, TA_CENTER),
                                                                                                      False, True),
        (lbl_e("Admission Date"),      val_e(ad_g),            val_a(ad_h),            lbl_a("تاريخ الدخول"),          False, False),
        (lbl_e("Discharge Date"),      val_e(dd_g),            val_a(dd_h),            lbl_a("تاريخ الخروج"),          False, False),
        (lbl_e("Issue Date"),          val_e(iss_g),           "",                     lbl_a("تاريخ إصدار التقرير"),   True,  False),
        (lbl_e("Name"),                val_e(name_en, NSZ),    val_a(name_ar, NSZ),    lbl_a("الاسم"),                 False, False),
        (lbl_e("National ID / Iqama"), val_e(nid),             "",                     arb("رقم الهوية / الإقامة", LSZ, C_LABEL, TA_CENTER),
                                                                                                      True,  False),
        (lbl_e("Nationality"),         val_e(nat_en),          val_a(nat_ar),          lbl_a("الجنسية"),               False, False),
        (lbl_e("Employer"),            val_e(emp_en),          val_a(emp_ar),          lbl_a("جهة العمل"),             False, False),
        (lbl_e("Practitioner Name"),   val_e(p_en, NSZ),       val_a(p_ar, NSZ),       lbl_a("اسم الممارس"),           False, False),
        (lbl_e("Position"),            val_e(pos_en),          val_a(pos_ar),          lbl_a("المسمى الوظيفى"),        False, False),
    ]

    tdata  = []
    extras = []
    alt_rows = {3, 5, 7, 9}

    for i, (le, ve, va, la, span, dark) in enumerate(rows):
        tdata.append([le, ve, va, la])
        if span:
            extras += [
                ("SPAN",  (1, i), (2, i)),
                ("ALIGN", (1, i), (2, i), "CENTER"),
            ]
        if dark:
            extras += [
                ("BACKGROUND",    (0, i), (-1, i), C_DARK),
                ("TOPPADDING",    (0, i), (-1, i), 10),
                ("BOTTOMPADDING", (0, i), (-1, i), 10),
            ]
        elif i in alt_rows:
            extras.append(("BACKGROUND", (0, i), (-1, i), C_ALTBG))
        else:
            extras.append(("BACKGROUND", (0, i), (-1, i), WHITE))

    tbl = Table(tdata, colWidths=[CL_EN, CV, CV2, CL_AR], rowHeights=[ROW_H] * len(rows))
    tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("GRID",          (0, 0), (-1, -1), 0.6, C_BORDER),
        ("BOX",           (0, 0), (-1, -1), 1.0, C_BORDER),
    ] + extras))

    story.append(tbl)
    story.append(Spacer(1, 35 * pt))

    # ══════════════════════════════════════════════════════════════════════════
    # FOOTER — 2-row table (exact match to original reference):
    #
    #  Row 1:  QR + verify text  (left) | hospital logo + name (right)
    #  Row 2:  time + date       (left) | NHIC logo + text (right)
    # ══════════════════════════════════════════════════════════════════════════

    verify_ar       = "للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة الرسمي"
    verify_en       = "To check the report please visit Seha's offical website"
    verify_url_text = "https://seha-8xj.pages.dev/"
    verify_url_href = "https://seha-8xj.pages.dev/"

    url_para = Paragraph(
        f'<link href="{verify_url_href}"><u>{verify_url_text}</u></link>',
        ParagraphStyle("url", fontName=_ENB if _ENB else _EN,
                       fontSize=9.5, textColor=C_LINK,
                       alignment=TA_CENTER, leading=12),
    )

    # ── QR code ────────────────────────────────────────────────────────────────
    qr_flowable = None
    if with_qr:
        try:
            import qrcode as qr_lib
            # QR code opens the exact inquiry portal link shown underneath
            target = "https://seha-8xj.pages.dev/"
            qr_obj = qr_lib.QRCode(version=3,
                                   error_correction=qr_lib.constants.ERROR_CORRECT_M,
                                   box_size=8, border=2)
            qr_obj.add_data(target)
            qr_obj.make(fit=True)
            qr_img = qr_obj.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            qr_img.save(buf, "PNG")
            buf.seek(0)
            qr_size = 120 * pt  # Exact reference size
            qr_flowable = RLImage(buf, width=qr_size, height=qr_size)
            qr_flowable.hAlign = "CENTER"
        except ImportError:
            pass

    # Row 1 LEFT: QR + verify text (centered under QR)
    r1_left = []
    if qr_flowable:
        r1_left.append(qr_flowable)
        r1_left.append(Spacer(1, 8 * pt))
    r1_left += [
        arb(verify_ar,  11, BLACK, TA_CENTER),
        Spacer(1, 4 * pt),
        enb(verify_en,  10, BLACK, TA_CENTER),
        Spacer(1, 4 * pt),
        url_para,
    ]

    # Row 1 RIGHT: hospital logo + name (centered)
    logo_src = hosp_logo if hosp_logo and Path(str(hosp_logo)).exists() else str(_MOH_LOGO)
    logo_fit = _fit(logo_src, 135 * pt, 115 * pt)
    r1_right = []
    if logo_fit:
        logo_fit.hAlign = "CENTER"
        r1_right.append(logo_fit)
        r1_right.append(Spacer(1, 8 * pt))
    if h_ar:
        r1_right.append(arb(h_ar, 13.5, BLACK, TA_CENTER))
    if h_en:
        r1_right.append(Spacer(1, 3 * pt))
        r1_right.append(enb(h_en, 11.5, BLACK, TA_CENTER))
    if not r1_right:
        r1_right = [en("", 9)]

    # Row 2 LEFT: time + date (left-aligned)
    r2_left = [
        Spacer(1, 15 * pt),
        enb(str(iss_t or ""),    13, BLACK, TA_LEFT),
        Spacer(1, 4 * pt),
        enb(str(iss_long or ""), 11.5, BLACK, TA_LEFT),
    ]

    # Row 2 RIGHT: NHIC logo (single image that already contains the text)
    nhic_fit = _fit(_NHIC_LOGO, 195 * pt, 90 * pt)

    r2_right = []
    if nhic_fit:
        r2_right.append(Spacer(1, 10 * pt))
        nhic_fit.hAlign = "RIGHT"
        r2_right.append(nhic_fit)

    if not r2_right:
        r2_right = [en("", 9)]

    FW_L = BODY_W * 0.50
    FW_R = BODY_W * 0.50

    footer_tbl = Table(
        [
            [r1_left,  r1_right],   # Row 1: QR+verify | hospital logo+name
            [r2_left,  r2_right],   # Row 2: time+date | NHIC logo
        ],
        colWidths=[FW_L, FW_R],
    )
    footer_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ALIGN",         (0, 0), (0, 0),   "CENTER"),
        ("ALIGN",         (1, 0), (1, 0),   "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (0, -1),  4),
        ("RIGHTPADDING",  (0, 0), (0, -1),  10),
        ("LEFTPADDING",   (1, 0), (1, -1),  10),
        ("RIGHTPADDING",  (1, 0), (1, -1),  4),
        # Vertical divider between columns on Row 1 only
        ("LINEAFTER",     (0, 0), (0, 0),   1.0, C_DIVIDER),
        # Row 2: Left column left-aligned, right column right-aligned
        ("VALIGN",        (0, 1), (-1, 1),  "TOP"),
        ("ALIGN",         (0, 1), (0, 1),   "LEFT"),
        ("ALIGN",         (1, 1), (1, 1),   "RIGHT"),
    ]))
    story.append(footer_tbl)

    # Add whitespace at bottom to match reference
    story.append(Spacer(1, 35 * pt))

    # ── Build PDF ────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return output_path
