"""
bot/handlers.py — Simplified bot using Telegram WebApp.
/start  →  زرار يفتح النموذج WebApp
web_app_data  →  يستقبل service_code ويبعت PDF
"""
from __future__ import annotations
import os, sys, logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from config import REPORTS_DIR
from db.database import AsyncSessionLocal
from db.models import SickLeaveReport

logger = logging.getLogger(__name__)


# ── /start ────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    webapp_url = ctx.bot_data.get("webapp_url", "")
    if not webapp_url:
        await update.message.reply_text(
            "⚠️ لم يتم إعداد رابط النموذج بعد.\n"
            "تأكد من تشغيل الخادم وإعداد WEBAPP_URL في ملف .env"
        )
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "📋 فتح نموذج الإجازة المرضية",
            web_app=WebAppInfo(url=webapp_url)
        )
    ]])

    await update.message.reply_text(
        "🏥 *مرحباً في بوت الإجازات المرضية* (@SehtyBot)\n\n"
        "اضغط الزر أدناه لفتح النموذج وملء بيانات التقرير.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ── web_app_data (بعد إغلاق النموذج) ─────────────────────────────────────────
async def handle_webapp_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    import json
    raw = update.message.web_app_data.data
    try:
        data = json.loads(raw)
    except Exception:
        await update.message.reply_text("❌ بيانات غير صالحة.")
        return

    service_code = data.get("service_code", "")
    status       = data.get("status", "")

    if status != "success" or not service_code:
        await update.message.reply_text("❌ حدث خطأ في الإرسال. حاول مجدداً.")
        return

    # ── Send PDF ──────────────────────────────────────────────────────────
    pdf_path = REPORTS_DIR / f"{service_code}.pdf"
    if not pdf_path.exists():
        await update.message.reply_text(
            f"⏳ جاري إنشاء التقرير...\n"
            f"رمز الخدمة: `{service_code}`",
            parse_mode="Markdown",
        )
        return

    with open(pdf_path, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename=f"SickLeave_{service_code}.pdf",
            caption=(
                f"✅ *تم إنشاء التقرير بنجاح!*\n"
                f"🔑 رمز الخدمة: `{service_code}`\n\n"
                f"للتحقق: `/verify {service_code}`"
            ),
            parse_mode="Markdown",
        )


# ── /verify ───────────────────────────────────────────────────────────────────
async def verify(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "الاستخدام: `/verify <رمز_الخدمة_أو_رقم_الهوية>`",
            parse_mode="Markdown",
        )
        return

    q = args[0].strip()
    from sqlalchemy import or_, select

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SickLeaveReport).where(
                or_(SickLeaveReport.service_code == q, SickLeaveReport.national_id == q)
            )
        )
        r = result.scalar_one_or_none()

    if not r:
        await update.message.reply_text(f"❌ لا يوجد سجل لـ `{q}`", parse_mode="Markdown")
        return

    def _fmt(d): return d.strftime("%d/%m/%Y") if d else "—"

    text = (
        f"✅ *تم التحقق*\n\n"
        f"🔑 رمز الخدمة: `{r.service_code}`\n"
        f"👤 المريض: {r.patient_name_ar}\n"
        f"🪪 رقم الهوية: `{r.national_id}`\n"
        f"📅 الدخول: {_fmt(r.admission_date)}\n"
        f"📅 الخروج: {_fmt(r.discharge_date)}\n"
        f"⏱️ المدة: {r.leave_duration_days} يوم\n"
        f"🏥 المستشفى: {r.hospital_name_ar or '—'}\n"
        f"👨‍⚕️ الممارس: {r.practitioner_name_ar or '—'}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
