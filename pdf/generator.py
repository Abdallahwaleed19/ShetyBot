"""
pdf/generator.py — Official Seha Sick Leave Report replica.

Matches the blank official template:
  HEADER : Seha (left) | KSA calligraphy + Kingdom of Saudi Arabia (center) | mesh (top-right corner)
  TITLE  : تقرير إجازة مرضية + Sick Leave Report  (standalone, below header)
  TABLE  : white cells, dark-navy Leave Duration row only
  FOOTER : verify text (left) | uploaded hospital logo + hospital name (right, MoH slot)
  BOTTOM : time + weekday date (left) | NHIC (right)
"""
from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
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
)

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
_ENB = _try_register(
    "ENB",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    _FONTS_DIR / "Latin.ttf",
)
_ARB = _try_register(
    "ARB",
    "/usr/share/fonts/truetype/fonts-hosny-amiri/Amiri-Bold.ttf",
    "/usr/share/fonts/truetype/amiri/Amiri-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    _FONTS_DIR / "Arabic.ttf",
)

# ── Colors (from official template) ────────────────────────────────────────────
C_DARK_BLUE  = colors.HexColor("#1A365D")
C_TITLE      = colors.HexColor("#3B8FBF")
C_TITLE_EN   = colors.HexColor("#2A4F70")
C_LABEL_TEXT = colors.HexColor("#3A7A9A")
C_VALUE      = colors.HexColor("#4A90A8")
C_LABEL_BG   = colors.HexColor("#E9E9E9")
C_ALT_BG     = colors.HexColor("#F4F4F4")
C_LINK       = colors.HexColor("#2B6CB0")
C_GREY_TEXT  = colors.HexColor("#555555")
C_GREY_LINE  = colors.HexColor("#C8C8C8")
C_DIVIDER    = colors.HexColor("#A8B0B8")
WHITE        = colors.white
BLACK        = colors.black

PAGE_W, PAGE_H = A4
MARGIN         = 1.35 * cm
HEADER_H       = 3.15 * cm


# ── Arabic helpers ─────────────────────────────────────────────────────────────
def ar(text: str) -> str:
    if not text:
        return ""
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except Exception:
        return str(text)


def has_ar(text) -> bool:
    return any("\u0600" <= c <= "\u06FF" for c in str(text or ""))


def _p(text, font, sz, color=BLACK, align=TA_LEFT, lh=1.25) -> Paragraph:
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
        ),
    )


def en(text, sz=9, color=BLACK, align=TA_LEFT):
    return _p(text, _EN, sz, color, align)


def en_bold(text, sz=9, color=BLACK, align=TA_LEFT):
    return _p(text, _ENB if _ENB else _EN, sz, color, align)


def arabic(text, sz=9, color=BLACK, align=TA_RIGHT):
    return _p(ar(text), _AR, sz, color, align)


def arabic_bold(text, sz=9, color=BLACK, align=TA_RIGHT):
    return _p(ar(text), _ARB if _ARB else _AR, sz, color, align)


def smart(text, sz=9, color=None, align=TA_CENTER):
    if color is None:
        color = C_VALUE
    s = str(text or "")
    if has_ar(s):
        return _p(ar(s), _AR, sz, color, TA_CENTER)
    return _p(s, _EN, sz, color, align)


# ── Image helpers ──────────────────────────────────────────────────────────────
def _crop_content(im: PILImage.Image, pad: int = 4, alpha: int = 18) -> PILImage.Image:
    im = im.convert("RGBA")
    px = im.load()
    w, h = im.size
    min_x, min_y, max_x, max_y = w, h, 0, 0
    found = False
    for y in range(h):
        for x in range(w):
            if px[x, y][3] > alpha:
                found = True
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y
    if not found:
        return im
    min_x = max(0, min_x - pad)
    min_y = max(0, min_y - pad)
    max_x = min(w - 1, max_x + pad)
    max_y = min(h - 1, max_y + pad)
    return im.crop((min_x, min_y, max_x + 1, max_y + 1))


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


def _fit_flowable(path, max_w, max_h):
    p = Path(str(path or ""))
    if not p.exists():
        return None
    try:
        im = _crop_content(PILImage.open(p))
        iw, ih = im.size
        if iw <= 0 or ih <= 0:
            return None
        scale = min(max_w / iw, max_h / ih)
        w, h = iw * scale, ih * scale
        buf = BytesIO()
        im.save(buf, format="PNG")
        buf.seek(0)
        return RLImage(buf, width=w, height=h)
    except Exception:
        return None


def _draw_image(c, reader, x, y, max_w, max_h, anchor="sw"):
    """Draw image fitted into max box. anchor: sw (x,y is bottom-left) or ne / n / c."""
    if reader is None:
        return
    iw, ih = reader.getSize()
    if iw <= 0 or ih <= 0:
        return
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
    c.drawImage(reader, x, y, width=w, height=h, mask="auto")


# ══════════════════════════════════════════════════════════════════════════════
def generate_pdf(data: dict, output_path) -> Path:
    output_path = Path(output_path)

    ad_g      = data.get("admission_date_gregorian", "")
    ad_h      = data.get("admission_date_hijri", "")
    dd_g      = data.get("discharge_date_gregorian", "")
    dd_h      = data.get("discharge_date_hijri", "")
    iss_g     = data.get("issue_date_gregorian", "")
    iss_long  = data.get("issue_date_long", iss_g)
    iss_t     = data.get("issue_time", "")
    dur       = str(data.get("leave_duration_days", ""))
    h_en_s    = data.get("hospital_name_en", "") or ""
    h_ar_s    = data.get("hospital_name_ar", "") or ""
    p_en_s    = data.get("practitioner_name_en", "")
    p_ar_s    = data.get("practitioner_name_ar", "")
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
    hosp_logo     = data.get("hospital_logo_path", "")
    include_barcode = data.get("include_barcode", False)

    day_word = "day" if str(dur) == "1" else "days"
    dur_en_val = f"{dur} {day_word} ( {ad_g} to {dd_g} )"
    dur_ar_inner = Table(
        [[
            _p(f"{dur} {ar('يوم')}", _AR, 8, WHITE, TA_CENTER),
            en(f"( {ad_h}", 8, WHITE, TA_CENTER),
            arabic("الى", 8, WHITE, TA_CENTER),
            en(f"{dd_h} )", 8, WHITE, TA_CENTER),
        ]],
        colWidths=[1.15 * cm, 1.65 * cm, 0.48 * cm, 1.55 * cm],
        hAlign="CENTER",
    )
    dur_ar_inner.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_DARK_BLUE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    seha_r = _reader(_SEHA_LOGO)
    ksa_r  = _reader(_KSA_CALLIGRAPHY)
    mesh_r = _reader(_GEOMETRIC_MESH)
    nhic_r = _reader(_NHIC_LOGO)

    logo_src = hosp_logo if hosp_logo and Path(str(hosp_logo)).exists() else str(_MOH_LOGO)

    usable_w = PAGE_W - 2 * MARGIN

    def _on_page(c, doc):
        c.saveState()

        _draw_image(c, mesh_r, PAGE_W + 4, PAGE_H + 6, 6.2 * cm, 3.2 * cm, anchor="ne")
        _draw_image(
            c, seha_r,
            MARGIN,
            PAGE_H - 0.58 * cm - 1.85 * cm,
            4.0 * cm,
            1.85 * cm,
            anchor="sw",
        )
        _draw_image(
            c, ksa_r,
            PAGE_W / 2,
            PAGE_H - 0.40 * cm,
            5.6 * cm,
            1.28 * cm,
            anchor="n",
        )
        c.setFillColor(C_DARK_BLUE)
        c.setFont(_EN, 8.5)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 2.05 * cm, "Kingdom of Saudi Arabia")

        # Timestamp + NHIC pinned to the page bottom (official layout)
        c.setFillColor(BLACK)
        c.setFont(_ENB if _ENB else _EN, 10)
        c.drawString(MARGIN, 1.70 * cm, str(iss_t or ""))
        c.setFont(_ENB if _ENB else _EN, 9)
        c.drawString(MARGIN, 1.28 * cm, str(iss_long or ""))
        _draw_image(
            c, nhic_r,
            PAGE_W - MARGIN,
            1.05 * cm,
            4.15 * cm,
            1.45 * cm,
            anchor="se",
        )
        c.setFillColor(C_GREY_TEXT)
        c.setFont(_EN, 8)
        c.drawString(MARGIN, 0.48 * cm, "1/1")

        c.restoreState()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=HEADER_H,
        bottomMargin=2.55 * cm,
    )
    story = []

    # ── TITLE (standalone, like the official template) ────────────────────────
    story.append(arabic_bold("تقرير إجازة مرضية", 18, C_TITLE, TA_CENTER))
    story.append(Spacer(1, 1.2 * mm))
    story.append(en_bold("Sick Leave Report", 13, C_TITLE_EN, TA_CENTER))
    story.append(Spacer(1, 6.5 * mm))

    # ── DATA TABLE ────────────────────────────────────────────────────────────
    CL = usable_w * 0.20
    CV = usable_w * 0.30

    def lbl_en(t):
        return en(t, 8.5, C_LABEL_TEXT, TA_CENTER)

    def lbl_ar(t):
        return arabic_bold(t, 9.5, C_LABEL_TEXT, TA_CENTER)

    rows_spec = [
        ([lbl_en("Leave ID"), smart(leave_id, 9), "", lbl_ar("رمز الإجازة")], True, False),
        (
            [
                en_bold("Leave Duration", 8.5, WHITE, TA_CENTER),
                en(dur_en_val, 8, WHITE, TA_CENTER),
                dur_ar_inner,
                arabic_bold("مدة الإجازة", 9.5, WHITE, TA_CENTER),
            ],
            False,
            True,
        ),
        ([lbl_en("Admission Date"), smart(ad_g, 9), smart(ad_h, 9), lbl_ar("تاريخ الدخول")], False, False),
        ([lbl_en("Discharge Date"), smart(dd_g, 9), smart(dd_h, 9), lbl_ar("تاريخ الخروج")], False, False),
        ([lbl_en("Issue Date"), smart(iss_g, 9), "", lbl_ar("تاريخ إصدار التقرير")], True, False),
        ([lbl_en("Name"), smart(name_en, 9), smart(name_ar, 9), lbl_ar("الاسم")], False, False),
        ([lbl_en("National ID / Iqama"), smart(nid, 9), "", lbl_ar("رقم الهوية/الاقامه")], True, False),
        ([lbl_en("Nationality"), smart(nat_en, 9), smart(nat_ar, 9), lbl_ar("الجنسية")], False, False),
        ([lbl_en("Employer"), smart(emp_en, 9), smart(emp_ar, 9), lbl_ar("جهة العمل")], False, False),
        (
            [lbl_en("Practitioner Name"), smart(p_en_s, 9), smart(p_ar_s, 9), lbl_ar("اسم الممارس")],
            False,
            False,
        ),
        ([lbl_en("Position"), smart(pos_en, 9), smart(pos_ar, 9), lbl_ar("المسمى الوظيفي")], False, False),
    ]

    tdata, extras = [], []
    alt_rows = {3, 5, 7, 9}
    for i, (row, span, dark) in enumerate(rows_spec):
        tdata.append(row)
        if span:
            extras += [("SPAN", (1, i), (2, i)), ("ALIGN", (1, i), (2, i), "CENTER")]
        if dark:
            extras += [
                ("BACKGROUND", (0, i), (-1, i), C_DARK_BLUE),
                ("TEXTCOLOR", (0, i), (-1, i), WHITE),
                ("TOPPADDING", (0, i), (-1, i), 6),
                ("BOTTOMPADDING", (0, i), (-1, i), 6),
                ("ALIGN", (1, i), (2, i), "CENTER"),
            ]
        elif i in alt_rows:
            extras.append(("BACKGROUND", (1, i), (2, i), C_ALT_BG))

    tbl = Table(tdata, colWidths=[CL, CV, CV, CL])
    tbl.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 6.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (1, 0), (2, -1), "CENTER"),
                ("ALIGN", (3, 0), (3, -1), "CENTER"),
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("BACKGROUND", (0, 0), (0, -1), C_LABEL_BG),
                ("BACKGROUND", (3, 0), (3, -1), C_LABEL_BG),
                ("GRID", (0, 0), (-1, -1), 0.45, C_GREY_LINE),
                ("BOX", (0, 0), (-1, -1), 0.55, C_GREY_LINE),
            ]
            + extras
        )
    )
    story.append(tbl)
    story.append(Spacer(1, 12 * mm))

    # ── FOOTER : verify (centered under table, left) | logo + hospital name ──
    verify_ar_1 = "للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة"
    verify_ar_2 = "الرسمي"
    verify_en = "To check the report please visit Seha's official website"
    verify_url = '<link href="https://www.seha.sa/#/inquiries/slenquiry"><u>www.seha.sa/#/inquiries/slenquiry</u></link>'

    footer_left = [
        arabic_bold(verify_ar_1, 10.5, BLACK, TA_CENTER),
        arabic_bold(verify_ar_2, 10.5, BLACK, TA_CENTER),
        Spacer(1, 2.4 * mm),
        en(verify_en, 8, C_GREY_TEXT, TA_CENTER),
        Spacer(1, 3.5 * mm),
        Paragraph(
            verify_url,
            ParagraphStyle(
                "url",
                fontName=_EN,
                fontSize=9,
                textColor=C_LINK,
                alignment=TA_CENTER,
                leading=12,
            ),
        ),
    ]

    logo_flow = _fit_flowable(logo_src, 3.15 * cm, 3.15 * cm) or en("", 8)
    name_block = [logo_flow, Spacer(1, 2.4 * mm)]
    if h_ar_s.strip():
        name_block.append(arabic_bold(h_ar_s.strip(), 12, BLACK, TA_CENTER))
    if h_en_s.strip():
        name_block.append(Spacer(1, 0.6 * mm))
        name_block.append(en_bold(h_en_s.strip(), 11, BLACK, TA_CENTER))
    if not h_ar_s.strip() and not h_en_s.strip():
        name_block.append(en("", 8))

    footer_tbl = Table(
        [[footer_left, name_block]],
        colWidths=[usable_w * 0.52, usable_w * 0.48],
        rowHeights=[4.3 * cm],
    )
    footer_tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (0, 0), 6),
                ("RIGHTPADDING", (0, 0), (0, 0), 10),
                ("LEFTPADDING", (1, 0), (1, 0), 10),
                ("RIGHTPADDING", (1, 0), (1, 0), 4),
                ("LINEAFTER", (0, 0), (0, -1), 0.9, C_DIVIDER),
            ]
        )
    )
    story.append(footer_tbl)

    # ── OPTIONAL QR BARCODE ────────────────────────────────────────────────────
    if include_barcode:
        try:
            import qrcode
            from qrcode.image.pil import PilImage
            # Use the seha verification link (or demo link if no real code)
            verify_target = f"https://www.seha.sa/#/inquiries/slenquiry"
            if leave_id:
                verify_target = f"https://sehtybot.fly.dev/verify?q={leave_id}"

            qr = qrcode.QRCode(
                version=3,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=8,
                border=2,
            )
            qr.add_data(verify_target)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")

            # Convert to reportlab-compatible buffer
            buf = BytesIO()
            qr_img.save(buf, format="PNG")
            buf.seek(0)
            qr_size = 2.8 * cm
            qr_flowable = RLImage(buf, width=qr_size, height=qr_size)

            barcode_label_ar = arabic("امسح الرمز للتحقق", 8, C_GREY_TEXT, TA_CENTER)
            barcode_label_en = en("Scan to verify report", 7, C_GREY_TEXT, TA_CENTER)

            barcode_tbl = Table(
                [[qr_flowable, [barcode_label_ar, Spacer(1, 1*mm), barcode_label_en]]],
                colWidths=[qr_size + 4*mm, usable_w - qr_size - 4*mm],
                hAlign="CENTER",
            )
            barcode_tbl.setStyle(TableStyle([
                ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
                ("ALIGN",         (0,0), (0,0),   "CENTER"),
                ("ALIGN",         (1,0), (1,0),   "CENTER"),
                ("TOPPADDING",    (0,0), (-1,-1), 4),
                ("BOTTOMPADDING", (0,0), (-1,-1), 4),
                ("LEFTPADDING",   (0,0), (-1,-1), 0),
                ("RIGHTPADDING",  (0,0), (-1,-1), 0),
            ]))
            story.append(Spacer(1, 5*mm))
            story.append(barcode_tbl)
        except ImportError:
            # qrcode not installed — skip silently
            pass
        except Exception:
            pass

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return output_path
