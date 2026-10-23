"""
bot/handlers.py — Simplified bot using Telegram WebApp.
/start       → sends WebApp button
web_app_data → receives service_code and sends PDF
/verify      → looks up report via Cloudflare Worker API
"""
from __future__ import annotations
import os
import sys
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from telegram import Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from config import REPORTS_DIR
from db.worker_client import get_report, search_by_national_id

logger = logging.getLogger(__name__)


# ── /start ─────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    webapp_url = ctx.bot_data.get("webapp_url", "")
    if not webapp_url:
        await update.message.reply_text(
            "⚠️ لم يتم إعداد رابط الموقع بعد.\n"
            "أضف WEBAPP_URL في ملف .env"
        )
        return

    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(
            "📋 فتح نموذج الإجازة المرضية",
            web_app=WebAppInfo(url=webapp_url),
        )]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await update.message.reply_text(
        "🏥 *مرحباً في نظام الإجازات المرضية* (@SehtyBot)\n\n"
        "اضغط الزر لفتح النموذج وملء بيانات الإجازة.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ── web_app_data (بعد إرسال النموذج) ──────────────────────────────────────────
async def handle_webapp_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    import json
    raw = update.message.web_app_data.data
    try:
        data = json.loads(raw)
    except Exception:
        await update.message.reply_text("❌ البيانات المستلمة غير صالحة.")
        return

    service_code = data.get("service_code", "")
    status       = data.get("status", "")

    if status != "success" or not service_code:
        await update.message.reply_text("❌ حدث خطأ في الإرسال. حاول مرة أخرى.")
        return

    # ── Send PDF ───────────────────────────────────────────────────────────────
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
                f"✅ *تم إنشاء الإجازة المرضية بنجاح!*\n"
                f"🔑 رمز الخدمة: `{service_code}`\n\n"
                f"للتحقق: `/verify {service_code}`"
            ),
            parse_mode="Markdown",
        )


# ── /verify ────────────────────────────────────────────────────────────────────
async def verify(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    args = ctx.args
    if not args:
        await update.message.reply_text(
            "الاستخدام: `/verify <رمز_الخدمة_أو_رقم_الهوية>`",
            parse_mode="Markdown",
        )
        return

    q = args[0].strip()

    # Try service code first, then national ID
    r = await get_report(q)
    if not r:
        results = await search_by_national_id(q)
        r = results[0] if results else None

    if not r:
        await update.message.reply_text(f"❌ لا يوجد سجل لـ `{q}`", parse_mode="Markdown")
        return

    text = (
        f"✅ *نتيجة التحقق*\n\n"
        f"🔑 رمز الخدمة: `{r.get('service_code', '')}`\n"
        f"👤 المريض: {r.get('patient_name_ar', '')}\n"
        f"🪪 رقم الهوية: `{r.get('national_id', '')}`\n"
        f"📅 الدخول: {r.get('admission_date', '')}\n"
        f"📅 الخروج: {r.get('discharge_date', '')}\n"
        f"⏱️ المدة: {r.get('leave_duration_days', '')} يوم\n"
        f"🏥 المستشفى: {r.get('hospital_name_ar', '')}\n"
        f"👨‍⚕️ الممارس: {r.get('practitioner_name_ar', '')}\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
