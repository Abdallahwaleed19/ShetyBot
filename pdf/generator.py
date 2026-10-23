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
C_DARK_BLUE  = colors.HexColor("#1B3A6B")
C_TITLE      = colors.HexColor("#2A6A9A")
C_LABEL_TEXT = colors.HexColor("#1A5276")
C_VALUE      = colors.HexColor("#1B6A9A")
C_LINK       = colors.HexColor("#1155CC")
C_GREY_TEXT  = colors.HexColor("#4A4A4A")
C_GREY_LINE  = colors.HexColor("#BFBFBF")
C_DIVIDER    = colors.HexColor("#B0B0B0")
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
    hosp_logo = data.get("hospital_logo_path", "")

    dur_en_val = f"{dur} day(s) ( {ad_g} to {dd_g} )"
    dur_ar_inner = Table(
        [[
            _p(f"{dur} {ar('يوم')}", _AR, 8, WHITE, TA_CENTER),
            en(str(ad_h), 8, WHITE, TA_CENTER),
            arabic("الى", 8, WHITE, TA_CENTER),
            en(str(dd_h), 8, WHITE, TA_CENTER),
        ]],
        colWidths=[1.45 * cm, 1.45 * cm, 0.55 * cm, 1.45 * cm],
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

    logo_src = hosp_logo if hosp_logo and Path(str(hosp_logo)).exists() else str(_MOH_LOGO)

    usable_w = PAGE_W - 2 * MARGIN

    def _on_page(c, doc):
        c.saveState()

        # Geometric mesh — flush to the top-right page corner
        _draw_image(c, mesh_r, PAGE_W + 6, PAGE_H + 8, 6.4 * cm, 3.45 * cm, anchor="ne")

        # Seha logo — top-left
        _draw_image(
            c, seha_r,
            MARGIN,
            PAGE_H - 0.55 * cm - 1.95 * cm,
            4.15 * cm,
            1.95 * cm,
            anchor="sw",
        )

        # KSA calligraphy + English kingdom line, centered
        _draw_image(
            c, ksa_r,
            PAGE_W / 2,
            PAGE_H - 0.38 * cm,
            5.9 * cm,
            1.35 * cm,
            anchor="n",
        )
        c.setFillColor(C_DARK_BLUE)
        c.setFont(_EN, 9)
        c.drawCentredString(PAGE_W / 2, PAGE_H - 2.12 * cm, "Kingdom of Saudi Arabia")

        c.restoreState()

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=HEADER_H,
        bottomMargin=1.15 * cm,
    )
    story = []

    # ── TITLE (standalone, like the official template) ────────────────────────
    story.append(arabic("تقرير إجازة مرضية", 16, C_TITLE, TA_CENTER))
    story.append(Spacer(1, 1.2 * mm))
    story.append(en("Sick Leave Report", 12, C_DARK_BLUE, TA_CENTER))
    story.append(Spacer(1, 6.5 * mm))

    # ── DATA TABLE ────────────────────────────────────────────────────────────
    CL = usable_w * 0.20
    CV = usable_w * 0.30

    def lbl_en(t):
        return en(t, 9, C_LABEL_TEXT, TA_CENTER)

    def lbl_ar(t):
        return arabic(t, 9, C_LABEL_TEXT, TA_CENTER)

    rows_spec = [
        ([lbl_en("Leave ID"), smart(leave_id, 9), "", lbl_ar("رمز الإجازة")], True, False),
        (
            [
                en("Leave Duration", 9, WHITE, TA_CENTER),
                en(dur_en_val, 8, WHITE, TA_CENTER),
                dur_ar_inner,
                arabic("مدة الإجازة", 9, WHITE, TA_CENTER),
            ],
            False,
            True,
        ),
        ([lbl_en("Admission Date"), smart(ad_g, 9), smart(ad_h, 9), lbl_ar("تاريخ الدخول")], False, False),
        ([lbl_en("Discharge Date"), smart(dd_g, 9), smart(dd_h, 9), lbl_ar("تاريخ الخروج")], False, False),
        ([lbl_en("Issue Date"), smart(iss_g, 9), "", lbl_ar("تاريخ إصدار التقرير")], True, False),
        ([lbl_en("Name"), smart(name_en, 9), smart(name_ar, 9), lbl_ar("الاسم")], False, False),
        ([lbl_en("National ID / Iqama"), smart(nid, 9), "", lbl_ar("رقم الهوية / الإقامة")], True, False),
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
    for i, (row, span, dark) in enumerate(rows_spec):
        tdata.append(row)
        if span:
            extras += [("SPAN", (1, i), (2, i)), ("ALIGN", (1, i), (2, i), "CENTER")]
        if dark:
            extras += [
                ("BACKGROUND", (0, i), (-1, i), C_DARK_BLUE),
                ("TEXTCOLOR", (0, i), (-1, i), WHITE),
                ("TOPPADDING", (0, i), (-1, i), 7),
                ("BOTTOMPADDING", (0, i), (-1, i), 7),
                ("ALIGN", (1, i), (2, i), "CENTER"),
            ]

    tbl = Table(tdata, colWidths=[CL, CV, CV, CL])
    tbl.setStyle(
        TableStyle(
            [
                ("TOPPADDING", (0, 0), (-1, -1), 7.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (3, 0), (3, -1), "CENTER"),
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("GRID", (0, 0), (-1, -1), 0.55, C_GREY_LINE),
                ("BOX", (0, 0), (-1, -1), 0.7, C_GREY_LINE),
            ]
            + extras
        )
    )
    story.append(tbl)
    story.append(Spacer(1, 11 * mm))

    # ── FOOTER : verify (left) | hospital logo + name (right, MoH slot) ───────
    verify_ar = "للتحقق من بيانات التقرير يرجى التأكد من زيارة موقع منصة صحة الرسمي"
    verify_en = "To check the report please visit Seha's official website"
    verify_url = '<link href="https://www.seha.sa/#/inquiries/slenquiry"><u>www.seha.sa/#/inquiries/slenquiry</u></link>'

    footer_left = [
        arabic_bold(verify_ar, 9, BLACK, TA_CENTER),
        Spacer(1, 2.2 * mm),
        en(verify_en, 8, C_GREY_TEXT, TA_CENTER),
        Spacer(1, 4 * mm),
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
    name_block = [logo_flow, Spacer(1, 2.2 * mm)]
    if h_ar_s.strip():
        name_block.append(arabic_bold(h_ar_s.strip(), 11, BLACK, TA_CENTER))
    if h_en_s.strip():
        name_block.append(Spacer(1, 0.8 * mm))
        name_block.append(en_bold(h_en_s.strip(), 10, BLACK, TA_CENTER))
    if not h_ar_s.strip() and not h_en_s.strip():
        name_block.append(en("", 8))

    footer_tbl = Table(
        [[footer_left, name_block]],
        colWidths=[usable_w * 0.56, usable_w * 0.44],
        rowHeights=[4.7 * cm],
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
    story.append(Spacer(1, 14 * mm))

    # ── BOTTOM : time + long date (official: compact black, stacked left) ────
    time_para = en(iss_t, 10, BLACK, TA_LEFT)
    date_para = en(iss_long, 9, BLACK, TA_LEFT)
    nhic_flow = _fit_flowable(_NHIC_LOGO, 4.4 * cm, 1.55 * cm) or en("", 8)

    bottom = Table(
        [[[time_para, Spacer(1, 1.2 * mm), date_para], nhic_flow]],
        colWidths=[usable_w * 0.55, usable_w * 0.45],
    )
    bottom.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LEFTPADDING", (0, 0), (0, 0), 2),
                ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ]
        )
    )
    story.append(bottom)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return output_path
