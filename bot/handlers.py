"""
bot/handlers.py — Simplified bot using Telegram WebApp.
/start       → sends WebApp button
/edit        → opens WebApp pre-filled with user's last report
/myreport    → shows last report summary + edit button
web_app_data → receives service_code and sends PDF
/verify      → looks up report via Cloudflare Worker API
"""
from __future__ import annotations
import os
import sys
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from telegram import (
    Update, WebAppInfo, KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import ContextTypes

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

    base_url = webapp_url.replace("/form", "")
    records_url = f"{base_url}/records"

    keyboard = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("📋 فتح نموذج الإجازة المرضية", web_app=WebAppInfo(url=webapp_url)),
                KeyboardButton("➕ البيانات السابقة", web_app=WebAppInfo(url=records_url)),
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    await update.message.reply_text(
        "🏥 *مرحباً بك في نظام الإجازات المرضية* (@SehtyBot)\n\n"
        "• اضغط *📋 فتح نموذج الإجازة المرضية* لإصدار تقرير جديد.\n"
        "• اضغط *➕ البيانات السابقة* لعرض سجلات الأشخاص ونسخها وتعديلها.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ── /edit ──────────────────────────────────────────────────────────────────────
async def edit_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Open WebApp pre-filled with the user's last report data."""
    webapp_url = ctx.bot_data.get("webapp_url", "")
    if not webapp_url:
        await update.message.reply_text("⚠️ رابط الموقع غير متاح.")
        return

    user_id = update.message.from_user.id

    # Try to get last service_code from memory first
    last_code = ctx.bot_data.get(f"last_code_{user_id}")

    # If not in memory, try fetching from D1 by telegram_user_id via Worker
    if not last_code:
        from db.worker_client import get_client
        client = await get_client()
        try:
            resp = await client.get("/api/reports", params={"telegram_user_id": str(user_id)})
            if resp.status_code == 200:
                records = resp.json().get("data", [])
                if records:
                    last_code = records[0].get("service_code")
        except Exception as e:
            logger.warning(f"Could not fetch last report for user {user_id}: {e}")

    if not last_code:
        await update.message.reply_text(
            "❌ لم يتم العثور على تقرير سابق.\n"
            "استخدم /start لإنشاء تقرير جديد.",
        )
        return

    # Open WebApp with ?edit=SERVICE_CODE so the form pre-fills
    edit_url = f"{webapp_url}?edit={last_code}"
    keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton(
            "✏️ تعديل التقرير السابق",
            web_app=WebAppInfo(url=edit_url),
        )]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await update.message.reply_text(
        f"✏️ *تعديل التقرير*\n\n"
        f"🔑 رمز الخدمة: `{last_code}`\n\n"
        f"اضغط الزر لفتح النموذج معبأً بالبيانات السابقة وعدّل ما تريد ثم أعد الإرسال.",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ── /myreport ─────────────────────────────────────────────────────────────────
async def my_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Show a summary of the user's last report with an edit option."""
    user_id = update.message.from_user.id
    webapp_url = ctx.bot_data.get("webapp_url", "")

    # Try memory first
    last_code = ctx.bot_data.get(f"last_code_{user_id}")

    # Try D1 lookup by telegram_user_id
    if not last_code:
        from db.worker_client import get_client
        client = await get_client()
        try:
            resp = await client.get("/api/reports", params={"telegram_user_id": str(user_id)})
            if resp.status_code == 200:
                records = resp.json().get("data", [])
                if records:
                    last_code = records[0].get("service_code")
        except Exception as e:
            logger.warning(f"my_report lookup error: {e}")

    if not last_code:
        await update.message.reply_text(
            "❌ لا يوجد تقرير محفوظ.\n"
            "استخدم /start لإنشاء تقرير جديد."
        )
        return

    r = await get_report(last_code)
    if not r:
        await update.message.reply_text(
            f"❌ لم يتم العثور على بيانات للرمز: `{last_code}`",
            parse_mode="Markdown",
        )
        return

    text = (
        f"📄 *آخر تقرير محفوظ*\n\n"
        f"🔑 رمز الخدمة: `{r.get('service_code', '')}`\n"
        f"👤 المريض: {r.get('patient_name_ar', '')}\n"
        f"🪪 رقم الهوية: `{r.get('national_id', '')}`\n"
        f"📅 الدخول: {r.get('admission_date', '')}\n"
        f"📅 الخروج: {r.get('discharge_date', '')}\n"
        f"⏱️ المدة: {r.get('leave_duration_days', '')} يوم\n"
        f"🏥 المستشفى: {r.get('hospital_name_ar', '')}\n"
        f"👨‍⚕️ الممارس: {r.get('practitioner_name_ar', '')}\n\n"
        f"للتعديل: /edit"
    )

    # Build inline keyboard
    buttons = []
    if webapp_url:
        edit_url = f"{webapp_url}?edit={last_code}"
        buttons.append([InlineKeyboardButton("✏️ تعديل", web_app=WebAppInfo(url=edit_url))])

    pdf_path = REPORTS_DIR / f"{last_code}.pdf"
    if pdf_path.exists():
        buttons.append([InlineKeyboardButton("📄 إعادة إرسال PDF", callback_data=f"resend_pdf:{last_code}")])

    markup = InlineKeyboardMarkup(buttons) if buttons else None
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


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

    # ── Save last service_code for this user in bot_data ──────────────────────
    user_id = update.message.from_user.id
    ctx.bot_data[f"last_code_{user_id}"] = service_code
    logger.info(f"Saved last_code_{user_id} = {service_code}")

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
                f"للتحقق: `/verify {service_code}`\n"
                f"للتعديل: /edit"
            ),
            parse_mode="Markdown",
        )


# ── callback_query (resend PDF) ────────────────────────────────────────────────
async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data and query.data.startswith("resend_pdf:"):
        service_code = query.data.split(":", 1)[1]
        pdf_path = REPORTS_DIR / f"{service_code}.pdf"
        if pdf_path.exists():
            with open(pdf_path, "rb") as f:
                await query.message.reply_document(
                    document=f,
                    filename=f"SickLeave_{service_code}.pdf",
                    caption=f"📄 إعادة إرسال — رمز الخدمة: `{service_code}`",
                    parse_mode="Markdown",
                )
        else:
            await query.message.reply_text("❌ ملف PDF غير موجود.")


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


# ── Text Handler for "+" & Records Menu ─────────────────────────────────────────
async def handle_text_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    txt = (update.message.text or "").strip()
    webapp_url = ctx.bot_data.get("webapp_url", "")
    base_url = webapp_url.replace("/form", "")
    records_url = f"{base_url}/records"

    if any(k in txt for k in ["+", "➕", "بيانات", "سابق", "سجل", "سجلات", "تعديل"]):
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 عرض البيانات السابقة", web_app=WebAppInfo(url=records_url))]
        ])
        await update.message.reply_text(
            "📋 *سجلات وبيانات الأشخاص السابقة*\n\n"
            "اضغط على الزر بالأسفل لفتح صفحة السجلات، حيث يمكنك:\n"
            "• عرض بيانات المرضى في خانات منظمة.\n"
            "• نسخ بيانات أي مريض بضغطة زر.\n"
            "• تعديل بيانات أي شخص بالضغط على علامة القلم ✏️.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
