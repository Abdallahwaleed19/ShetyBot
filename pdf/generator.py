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
C_LABEL   = colors.HexColor("#366fb5")   # EN/AR label text (bold blue)
C_VALUE   = colors.HexColor("#2c3e77")   # cell values (dark blue)
C_DARK    = colors.HexColor("#2c3e77")   # Leave Duration row bg  
C_TITLE   = colors.HexColor("#306db5")   # Arabic title
C_TITLE_EN= colors.HexColor("#2e3f7b")   # English title
C_LINK    = colors.HexColor("#153bc2")   # URL link
C_GREY    = colors.HexColor("#555555")   # verify text
C_LBLBG   = colors.HexColor("#f0f0f0")   # label column background (light grey)
C_ALTBG   = colors.HexColor("#f8f8f8")   # alt row background
C_BORDER  = colors.HexColor("#d0d0d0")   # table border
C_DIVIDER = colors.HexColor("#bbbbbb")   # vertical divider in footer
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
    ad_g      = data.get("admission_date_gregorian", "")
    ad_h      = data.get("admission_date_hijri", "")
    dd_g      = data.get("discharge_date_gregorian", "")
    dd_h      = data.get("discharge_date_hijri", "")
    iss_g     = data.get("issue_date_gregorian", "")
    iss_long  = data.get("issue_date_long", iss_g)    # "Friday ,3 July 2026"
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
                  PAGE_W - MAR_R, H - MAR_T,
                  mesh_w_ref, mesh_h_ref,
                  anchor="ne")

        # ── SEHA LOGO — top-left ───────────────────────────────────────────────
        # Reference: rect(36, 36, 186, 102) → 150×66pt
        _draw_img(c, seha_r,
                  MAR_L, H - MAR_T,
                  150, 66,
                  anchor="nw")

        # ── KSA CALLIGRAPHY — center top ──────────────────────────────────────
        # Reference: rect(288, 36, 551, 160) → center of page at top
        ksa_w_ref = 551 - 288    # ≈ 263pt
        ksa_h_ref = 160 - 36     # ≈ 124pt
        _draw_img(c, ksa_r,
                  PAGE_W / 2, H - MAR_T,
                  ksa_w_ref, ksa_h_ref,
                  anchor="n")

        # "Kingdom of Saudi Arabia" — directly under KSA calligraphy
        # Reference: y≈104 from top (calligraphy bottom is at 160, text is at ~170)
        ksa_bottom_y = H - 160   # bottom of KSA calligraphy in pdf coords
        c.setFillColor(BLACK)
        c.setFont(_EN if _EN != "Helvetica" else "Helvetica", 10.5)
        c.drawCentredString(PAGE_W / 2, ksa_bottom_y - 14, "Kingdom of Saudi Arabia")

        # ── NHIC LOGO — bottom right ───────────────────────────────────────────
        # Reference: rect(655, 934, 806, 1006) — placed in bottom-right area
        # We position it relative to page bottom with adjusted values
        nhic_w_ref = 806 - 655   # ≈ 151pt
        nhic_h_ref = 1006 - 934  # ≈ 72pt
        # In our coordinate system: y from BOTTOM
        nhic_bottom = H - 1006   # bottom edge of NHIC box (from page bottom)
        nhic_right  = PAGE_W - MAR_R
        _draw_img(c, nhic_r,
                  nhic_right, nhic_bottom,
                  nhic_w_ref * 1.5, nhic_h_ref * 1.5,
                  anchor="se")

        # ── TIME & DATE — bottom left ──────────────────────────────────────────
        # Reference: time y=945 from top, date y=982 from top
        time_y = H - 945    # convert to ReportLab y (from bottom)
        date_y = H - 982
        c.setFillColor(BLACK)
        c.setFont(_ENB if _ENB else "Helvetica-Bold", 12)
        c.drawString(MAR_L, time_y, str(iss_t or ""))
        c.setFont(_ENB if _ENB else "Helvetica-Bold", 12)
        c.drawString(MAR_L, date_y, str(iss_long or ""))

        c.restoreState()

    # ── Build story (flowable content) ──────────────────────────────────────────
    # Top margin covers header area (from top to just below KSA text ~200pt)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=(PAGE_W, PAGE_H),
        leftMargin=MAR_L,
        rightMargin=MAR_R,
        topMargin=200 * pt,     # header occupies top ~200pt
        bottomMargin=270 * pt,  # footer + time/date area at bottom
    )

    story = []
    BODY_W = USABLE_W  # 770pt

    # ── TITLES ─────────────────────────────────────────────────────────────────
    # Reference: "تقرير إجازة مرضية" sz=22.5 bold #306db5, y=150 (from top)
    #            "Sick Leave Report"  sz=19.7 bold #2e3f7b, y=194
    story.append(arb("تقرير إجازة مرضية", 22.5, C_TITLE, TA_CENTER))
    story.append(Spacer(1, 6 * pt))
    story.append(enb("Sick Leave Report", 19.7, C_TITLE_EN, TA_CENTER))
    story.append(Spacer(1, 20 * pt))

    # ── DATA TABLE ──────────────────────────────────────────────────────────────
    # Reference: 4 columns.
    # Col widths from reference image: label-EN ~17%, val-EN ~30%, val-AR ~30%, label-AR ~23%
    CL_EN = BODY_W * 0.175   # EN label column
    CV    = BODY_W * 0.300   # value column (EN values)
    CV2   = BODY_W * 0.300   # value column (AR values)
    CL_AR = BODY_W * 0.225   # AR label column

    # Reference font sizes: labels sz=13.5 bold; values sz=13.5 (12.4 for long names)
    LSZ = 9.5    # label font size (scaled for our doc)
    VSZ = 9.5    # value font size
    NSZ = 8.8    # smaller for long names

    def lbl_e(t):
        return enb(t, LSZ, C_LABEL, TA_CENTER)

    def lbl_a(t):
        return arb(t, LSZ, C_LABEL, TA_CENTER)

    def val_e(t, sz=VSZ):
        return en(str(t or ""), sz, C_VALUE, TA_CENTER)

    def val_a(t, sz=VSZ):
        return arabic(str(t or ""), sz, C_VALUE, TA_CENTER)

    # Row heights — reference rows ~42pt each
    ROW_H = 32 * pt

    # Build rows — order matches reference exactly:
    rows = [
        # (en_label, en_val, ar_val, ar_label, span_val, dark_bg)
        (lbl_e("Leave ID"),           val_e(leave_id),  "",                   lbl_a("رمز الإجازة"),        True,  False),
        (enb("Leave Duration", LSZ, WHITE, TA_CENTER),
                                      en(dur_en, 8.2, WHITE, TA_CENTER),
                                                        arabic(dur_ar, 8.2, WHITE, TA_CENTER),
                                                                              arb("مدة الإجازة", LSZ, WHITE, TA_CENTER),
                                                                                              False, True),
        (lbl_e("Admission Date"),     val_e(ad_g),       val_a(ad_h),         lbl_a("تاريخ الدخول"),      False, False),
        (lbl_e("Discharge Date"),     val_e(dd_g),       val_a(dd_h),         lbl_a("تاريخ الخروج"),      False, False),
        (lbl_e("Issue Date"),         val_e(iss_g),      "",                  lbl_a("تاريخ إصدار التقرير"), True, False),
        (lbl_e("Name"),               val_e(name_en, NSZ), val_a(name_ar, NSZ), lbl_a("الاسم"),           False, False),
        (lbl_e("National ID / Iqama"),val_e(nid),        "",                  arb("رقم الهوية / الإقامة", LSZ, C_LABEL, TA_CENTER),
                                                                                              True,  False),
        (lbl_e("Nationality"),        val_e(nat_en),     val_a(nat_ar),       lbl_a("الجنسية"),           False, False),
        (lbl_e("Employer"),           val_e(emp_en),     val_a(emp_ar),       lbl_a("جهة العمل"),         False, False),
        (lbl_e("Practitioner Name"),  val_e(p_en, NSZ),  val_a(p_ar, NSZ),    lbl_a("اسم الممارس"),       False, False),
        (lbl_e("Position"),           val_e(pos_en),     val_a(pos_ar),       lbl_a("المسمى الوظيفى"),    False, False),
    ]

    tdata  = []
    extras = []
    alt_rows = {2, 4, 6, 8, 10}   # 0-indexed rows that get alt background

    for i, (le, ve, va, la, span, dark) in enumerate(rows):
        tdata.append([le, ve, va, la])
        if span:
            extras += [
                ("SPAN",  (1, i), (2, i)),
                ("ALIGN", (1, i), (2, i), "CENTER"),
            ]
        if dark:
            extras += [
                ("BACKGROUND", (0, i), (-1, i), C_DARK),
                ("TOPPADDING",    (0, i), (-1, i), 8),
                ("BOTTOMPADDING", (0, i), (-1, i), 8),
            ]
        elif i in alt_rows:
            extras.append(("BACKGROUND", (1, i), (2, i), C_ALTBG))

    tbl = Table(tdata, colWidths=[CL_EN, CV, CV2, CL_AR], rowHeights=[ROW_H] * len(rows))
    tbl.setStyle(TableStyle([
        # base
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        # backgrounds
        ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
        ("BACKGROUND",    (0, 0), (0, -1),  C_LBLBG),
        ("BACKGROUND",    (3, 0), (3, -1),  C_LBLBG),
        # grid
        ("GRID",          (0, 0), (-1, -1), 0.5, C_BORDER),
        ("BOX",           (0, 0), (-1, -1), 1.0, C_BORDER),
    ] + extras))

    story.append(tbl)
    story.append(Spacer(1, 24 * pt))

    # ── FOOTER: QR left | hospital logo+name right (with vertical divider) ──────
    # Reference: QR at (170-283, 719-832) → ~113×113pt; logo at (563-685, 733-844)
    # verify text: y≈831-909; URL: y≈907

    verify_ar  = "للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة الرسمي"
    verify_en  = "To check the report please visit Seha's offical website"
    verify_url_text = "www.seha.sa/#/inquiries/slenquiry"
    verify_url_href = "https://www.seha.sa/#/inquiries/slenquiry"

    url_para = Paragraph(
        f'<link href="{verify_url_href}"><u>{verify_url_text}</u></link>',
        ParagraphStyle("url", fontName=_ENB if _ENB else _EN,
                       fontSize=9, textColor=C_LINK,
                       alignment=TA_LEFT, leading=11),
    )

    # ── QR code (optional) ────────────────────────────────────────────────────
    qr_flowable = None
    if with_qr:
        try:
            import qrcode as qr_lib
            target = f"https://sehtybot.fly.dev/verify?q={leave_id}" if leave_id else verify_url_href
            qr_obj = qr_lib.QRCode(version=3,
                                   error_correction=qr_lib.constants.ERROR_CORRECT_M,
                                   box_size=7, border=2)
            qr_obj.add_data(target)
            qr_obj.make(fit=True)
            qr_img = qr_obj.make_image(fill_color="black", back_color="white")
            buf = BytesIO()
            qr_img.save(buf, "PNG")
            buf.seek(0)
            qr_size = 95 * pt   # reference ≈113pt but slightly smaller looks better
            qr_flowable = RLImage(buf, width=qr_size, height=qr_size)
            qr_flowable.hAlign = "LEFT"
        except ImportError:
            pass

    # Footer LEFT column
    footer_left_items = []
    if qr_flowable:
        footer_left_items.append(qr_flowable)
        footer_left_items.append(Spacer(1, 6 * pt))
    footer_left_items += [
        arb(verify_ar,  10, BLACK, TA_LEFT),
        Spacer(1, 4 * pt),
        enb(verify_en,  9,  BLACK, TA_LEFT),
        Spacer(1, 4 * pt),
        url_para,
    ]

    # Footer RIGHT column: hospital logo + name
    logo_fit = _fit(logo_src, 100 * pt, 90 * pt)
    footer_right_items = []
    if logo_fit:
        footer_right_items.append(logo_fit)
        footer_right_items.append(Spacer(1, 5 * pt))
    if h_ar:
        footer_right_items.append(arb(h_ar, 12, BLACK, TA_CENTER))
    if h_en:
        footer_right_items.append(Spacer(1, 2 * pt))
        footer_right_items.append(enb(h_en, 10, BLACK, TA_CENTER))
    if not footer_right_items:
        footer_right_items = [en("", 9)]

    FW_L = BODY_W * 0.52
    FW_R = BODY_W * 0.48

    footer_tbl = Table(
        [[footer_left_items, footer_right_items]],
        colWidths=[FW_L, FW_R],
    )
    footer_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("ALIGN",         (0, 0), (0, 0),   "LEFT"),
        ("ALIGN",         (1, 0), (1, 0),   "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (0, 0),   4),
        ("RIGHTPADDING",  (0, 0), (0, 0),   12),
        ("LEFTPADDING",   (1, 0), (1, 0),   12),
        ("RIGHTPADDING",  (1, 0), (1, 0),   4),
        ("LINEAFTER",     (0, 0), (0, -1),  1.0, C_DIVIDER),
    ]))
    story.append(footer_tbl)

    # ── Build PDF ────────────────────────────────────────────────────────────────
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return output_path
