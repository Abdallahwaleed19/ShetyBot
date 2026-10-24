"""
bot/handlers.py — Simplified bot using Telegram WebApp.
/start       → checks authorization, registration status, approval, sends WebApp buttons
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
    InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove,
)
from telegram.ext import ContextTypes

from config import REPORTS_DIR
from db.worker_client import get_report, search_by_national_id
from db.database import (
    get_user_by_identifier_sync,
    check_subscription_sync,
    ADMIN_TELEGRAM_ID,
    ADMIN_USERNAME,
)

logger = logging.getLogger(__name__)


# ── /start ─────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user:
        return

    webapp_url = ctx.bot_data.get("webapp_url", "")
    if not webapp_url:
        await update.message.reply_text(
            "⚠️ لم يتم إعداد رابط الموقع بعد.\n"
            "أضف WEBAPP_URL في ملف .env"
        )
        return

    base_url = webapp_url.replace("/form", "")
    records_url = f"{base_url}/records"

    user = update.message.from_user
    user_tg_id = str(user.id).strip()
    user_name = (user.username or "").lstrip("@").strip()

    is_admin = (user_tg_id == ADMIN_TELEGRAM_ID) or (user_name.lower() == ADMIN_USERNAME.lower())

    # Look up user in database
    user_rec = get_user_by_identifier_sync(user_tg_id)
    if not user_rec and user_name:
        user_rec = get_user_by_identifier_sync(user_name)

    # 1. Admin Access
    if is_admin:
        admin_url = f"{base_url}/admin?key=admin123"
        keyboard = ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton("📋 فتح نموذج الإجازة المرضية", web_app=WebAppInfo(url=f"{webapp_url}?telegram_user_id={user_tg_id}")),
                    KeyboardButton("➕ البيانات السابقة", web_app=WebAppInfo(url=f"{records_url}?telegram_user_id={user_tg_id}")),
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
        )

        inline_admin = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ لوحة الإدارة الشاملة", url=admin_url)],
            [InlineKeyboardButton("📂 استعراض كافة السجلات", web_app=WebAppInfo(url=f"{records_url}?telegram_user_id={user_tg_id}"))]
        ])

        await update.message.reply_text(
            f"👑 *مرحباً بك يا مدير النظام* (@{ADMIN_USERNAME})\n\n"
            f"لديك صلاحيات إدارية كاملة لإدارة البوت والموافقة على المستخدمين واستعراض كافة السجلات.\n\n"
            f"• اضغط *📋 فتح نموذج الإجازة المرضية* لإصدار تقرير جديد.\n"
            f"• اضغط *➕ البيانات السابقة* لإدارة جميع السجلات وسلة المحذوفات.\n"
            f"• اضغط الزر أدناه لفتح لوحة الإدارة:",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        await update.message.reply_text(
            "⚙️ لوحة التحكم والإدارة:",
            reply_markup=inline_admin
        )
        return

    # 2. Unregistered User
    if not user_rec:
        reg_url = f"{webapp_url}?telegram_user_id={user_tg_id}"
        inline_reg = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 تقديم طلب تسجيل جديد", web_app=WebAppInfo(url=reg_url))]
        ])
        await update.message.reply_text(
            "🏥 *مرحباً بك في نظام الإجازات المرضية صحتي* (@SehtyBot)\n\n"
            "⚠️ *تنبيه:* يتطلب استخدام البوت تسجيلاً مسبقاً وموافقة من الإدارة (@As1_oi).\n\n"
            "يرجى الضغط على الزر أدناه لإرسال طلب تسجيلك (الاسم والبريد الإلكتروني)، وفور مراجعة الطلب والموافقة عليه ستصلك رسالة تحتوي على رمز التفعيل المؤقت.",
            parse_mode="Markdown",
            reply_markup=inline_reg,
        )
        return

    # 3. User with PENDING_APPROVAL status
    if user_rec.registration_status == "PENDING_APPROVAL":
        await update.message.reply_text(
            "⏳ *طلب تسجيلك قيد المراجعة لدى الإدارة (@As1_oi)*\n\n"
            "تم استلام بياناتك وهي قيد التدقيق حالياً. بمجرد قبول الطلب، سيصلك رمز التحقق المؤقت (صالح لمدة 30 ثانية) على بريدك الإلكتروني وهاتفك لتفعيل الاشتراك لمدة 30 يوماً.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # 4. User with REJECTED status
    if user_rec.registration_status == "REJECTED":
        reason = getattr(user_rec, "rejection_reason", None) or "البيانات المقدمة غير كافية"
        await update.message.reply_text(
            f"❌ *تم رفض طلب التسجيل الخاص بك*\n\n"
            f"📝 *السبب:* {reason}\n\n"
            f"يمكنك التواصل مع الإدارة للاستفسار: @{ADMIN_USERNAME}",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # 5. User with APPROVED status (waiting for 30s OTP)
    if user_rec.registration_status == "APPROVED":
        otp_url = f"{webapp_url}?telegram_user_id={user_tg_id}&u={user_rec.username or user_tg_id}"
        inline_otp = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 إدخال رمز التحقق (30 ثانية)", web_app=WebAppInfo(url=otp_url))]
        ])
        await update.message.reply_text(
            "🎉 *تمت الموافقة على طلب تسجيلك!*\n\n"
            f"تم إرسال رمز التحقق المؤقت (صالح لمدة 30 ثانية) إلى بريدك الإلكتروني (`{user_rec.email}`).\n\n"
            "اضغط على الزر أدناه لإدخال الرمز المكون من 5 أرقام فوراً وتفعيل اشتراكك لمدة 30 يوماً:",
            parse_mode="Markdown",
            reply_markup=inline_otp,
        )
        return

    # 6. User with SUSPENDED status
    if user_rec.registration_status == "SUSPENDED" or not user_rec.is_active:
        await update.message.reply_text(
            f"⏸️ *حسابك معلق حالياً*\n\n"
            f"تم تعليق حسابك من قبل إدارة النظام. يرجى التواصل مع الإدارة لإعادة التفعيل: @{ADMIN_USERNAME}",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # 7. User with ACTIVE status: Check Subscription
    sub = check_subscription_sync(user_rec.id)
    if not sub["active"]:
        await update.message.reply_text(
            f"⚠️ *انتهت فترة اشتراكك (30 يوماً)*\n\n"
            f"عذراً، لقد انتهت صلاحية استخدامك لنظام الإجازات المرضية. يرجى التواصل مع الإدارة (@{ADMIN_USERNAME}) لتجديد صلاحية حسابك لمدة 30 يوماً أخرى.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # Active and verified! Display both main buttons
    keyboard = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("📋 فتح نموذج الإجازة المرضية", web_app=WebAppInfo(url=f"{webapp_url}?telegram_user_id={user_tg_id}")),
                KeyboardButton("➕ البيانات السابقة", web_app=WebAppInfo(url=f"{records_url}?telegram_user_id={user_tg_id}")),
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    await update.message.reply_text(
        f"🏥 *مرحباً بك مجدداً في نظام الإجازات المرضية* (@SehtyBot)\n\n"
        f"🟢 *حالة الاشتراك:* نشط (متبقي {sub['days_remaining']} يوم)\n\n"
        f"• اضغط *📋 فتح نموذج الإجازة المرضية* لإصدار تقرير جديد.\n"
        f"• اضغط *➕ البيانات السابقة* لعرض سجلاتك وتعديلها واسترجاعها من سلة المحذوفات.",
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
    last_code = ctx.bot_data.get(f"last_code_{user_id}")

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

    edit_url = f"{webapp_url}?edit={last_code}&telegram_user_id={user_id}"
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
    last_code = ctx.bot_data.get(f"last_code_{user_id}")

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

    buttons = []
    if webapp_url:
        edit_url = f"{webapp_url}?edit={last_code}&telegram_user_id={user_id}"
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

    user_id = update.message.from_user.id
    ctx.bot_data[f"last_code_{user_id}"] = service_code
    logger.info(f"Saved last_code_{user_id} = {service_code}")

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

    user = update.message.from_user
    user_tg_id = str(user.id).strip()
    user_name = (user.username or "").lstrip("@").strip()

    is_admin = (user_tg_id == ADMIN_TELEGRAM_ID) or (user_name.lower() == ADMIN_USERNAME.lower())
    user_rec = get_user_by_identifier_sync(user_tg_id)

    # If user wants previous records
    if any(k in txt for k in ["+", "➕", "بيانات", "سابق", "سجل", "سجلات", "تعديل"]):
        if not is_admin and (not user_rec or user_rec.registration_status != "ACTIVE"):
            await update.message.reply_text(
                "⚠️ *عذراً، لا يمكنك الوصول للبيانات السابقة*\n\n"
                "يتطلب فتح السجلات أن يكون حسابك مسجلاً ومفعلاً بموافقة الإدارة.\n"
                "استخدم الأمر /start للتحقق من حالة حسابك أو تقديم طلب تسجيل.",
                parse_mode="Markdown",
            )
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 عرض البيانات السابقة", web_app=WebAppInfo(url=f"{records_url}?telegram_user_id={user_tg_id}"))]
        ])
        await update.message.reply_text(
            "📋 *سجلات وبيانات الأشخاص السابقة*\n\n"
            "اضغط على الزر بالأسفل لفتح صفحة السجلات، حيث يمكنك:\n"
            "• عرض بيانات المرضى في خانات منظمة.\n"
            "• نسخ بيانات أي مريض بضغطة زر.\n"
            "• تعديل بيانات أي شخص بالضغط على علامة القلم ✏️.\n"
            "• نقل السجلات إلى سلة المحذوفات أو استرجاعها.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
