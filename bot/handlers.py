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
from config import ADMIN_USERNAMES
from db.database import (
    get_user_by_identifier_sync,
    check_subscription_sync,
    record_user_activity_sync,
    get_latest_code_for_user_sync,
    get_all_saved_reports_sync,
    ADMIN_TELEGRAM_ID,
    ADMIN_USERNAME,
)

logger = logging.getLogger(__name__)


async def reply_safe(message, text: str, reply_markup=None, parse_mode: str = "HTML"):
    """Sends message with HTML; falls back to plain text if Telegram parse error occurs."""
    try:
        return await message.reply_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"Failed to send with {parse_mode}: {e}. Retrying with plain text.")
        clean_text = text.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", "").replace("<i>", "").replace("</i>", "")
        return await message.reply_text(clean_text, reply_markup=reply_markup)


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
    record_user_activity_sync(telegram_user_id=user_tg_id)

    is_admin = (user_tg_id == ADMIN_TELEGRAM_ID) or (user_name.lower() in [u.lower() for u in ADMIN_USERNAMES])

    # Look up user in database (including checking if deleted)
    user_rec = get_user_by_identifier_sync(user_tg_id, include_deleted=True)
    if not user_rec and user_name:
        user_rec = get_user_by_identifier_sync(user_name, include_deleted=True)

    if user_rec and (getattr(user_rec, "is_deleted", False) or user_rec.registration_status == "DELETED"):
        await update.message.reply_text("⛔ <b>عذراً، هذا الحساب محظور أو تم حذفه من قِبل إدارة المنصة.</b>", parse_mode="HTML")
        return

    # Always link Telegram User ID if missing or mismatched
    if user_rec and user_tg_id and user_tg_id not in ("0", "-1") and str(user_rec.telegram_user_id) != user_tg_id:
        from db.database import update_user_telegram_id_sync
        update_user_telegram_id_sync(user_rec.id, user_tg_id)
        user_rec.telegram_user_id = user_tg_id

    # 1. Admin Access
    if is_admin:
        admin_url = f"{base_url}/admin?key=admin123"
        admin_form_url = f"{webapp_url}?telegram_user_id={user_tg_id}&role=admin&u={ADMIN_USERNAME}"
        admin_records_url = f"{records_url}?telegram_user_id={user_tg_id}&role=admin&u={ADMIN_USERNAME}"

        keyboard = ReplyKeyboardMarkup(
            [
                [
                    KeyboardButton("📝 تقديم تقرير جديد", web_app=WebAppInfo(url=admin_form_url)),
                    KeyboardButton("📋 البيانات السابقة", web_app=WebAppInfo(url=admin_records_url)),
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=False,
        )

        inline_admin = InlineKeyboardMarkup([
            [InlineKeyboardButton("👑 فتح لوحة تحكم الأدمن", url=admin_url)],
            [InlineKeyboardButton("📋 فتح النموذج كمدير", web_app=WebAppInfo(url=admin_form_url))],
            [InlineKeyboardButton("📂 استعراض كافة السجلات", web_app=WebAppInfo(url=admin_records_url))]
        ])

        admin_msg = (
            f"👑 <b>مرحباً بك يا مدير النظام (@{ADMIN_USERNAME})</b>\n\n"
            f"لديك صلاحيات إدارية كاملة لإدارة البوت والموافقة على المستخدمين واستعراض كافة السجلات."
        )
        await reply_safe(update.message, admin_msg, reply_markup=keyboard)
        await reply_safe(update.message, "⚙️ <b>لوحة التحكم والإدارة:</b>", reply_markup=inline_admin)
        return

    # 2. Unregistered User (First-time /start)
    if not user_rec:
        reg_url = f"{webapp_url}?telegram_user_id={user_tg_id}"
        inline_reg = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 تقديم طلب إنشاء تقرير جديد", web_app=WebAppInfo(url=reg_url))],
            [InlineKeyboardButton("💬 تواصل مع المشرف (@RE_i1i)", url="https://t.me/RE_i1i")]
        ])
        unreg_msg = (
            "🔴 <b>اسعار الاشتراك</b> 🔴\n"
            "اشتراك شهر =٥٠ ريال\n"
            "اشتراك ٣ أشهر = ١١٠ ريال\n"
            "اشتراك ٦ أشهر = ٢٠٠ريال\n"
            "اشتراك ٩ أشهر ٣٥٠ ريال\n\n"
            "🛑 <b>قم بدعوة ٣ من أصدقائك واحصل على شهر مجاني</b> 🛑\n"
            "⭕ <b>لشحن رصيدك تواصل مع المشرف</b>⭕\n\n"
            "• التحويل على حسابي الكريمي\n"
            "• رقم الحساب اليمني: <code>3126519272</code>\n"
            "• رقم الحساب السعودي: <code>3142525843</code>\n"
            "✅ <b>أرسل صورة الإشعار بعد التحويل</b> ✅\n\n"
            "&اذا عندك طريقة دفع اخرى علمنا وش هي &\n"
            "وانتظر حتى يتم الرد عليك 🫡\n"
            "رابط التواصل تلجرام:\n"
            "@RE_i1i"
        )
        await reply_safe(update.message, unreg_msg, reply_markup=inline_reg)
        return

    # 3. User with PENDING_APPROVAL status
    if user_rec.registration_status == "PENDING_APPROVAL":
        inline_pending = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 تواصل مع الإدارة (@RE_i1i)", url="https://t.me/RE_i1i")],
            [InlineKeyboardButton("💬 تواصل مع المشرف (@WS2030W)", url="https://t.me/WS2030W")]
        ])
        pending_msg = (
            "⏳ <b>طلب تسجيلك قيد المراجعة</b>\n\n"
            "تم استلام بياناتك بنجاح وهي قيد التدقيق حالياً.\n\n"
            "🔴 <b>إذا كنت ترغب في الاشتراك وتفعيل الحساب فوراً:</b>\n"
            "يرجى التواصل مع الإدارة أو المشرف:\n"
            "👑 <b>الإدارة:</b> @RE_i1i\n"
            "🛡️ <b>المشرف:</b> @WS2030W\n\n"
            "• التحويل على حساب الكريمي:\n"
            "• رقم الحساب اليمني: <code>3126519272</code>\n"
            "• رقم الحساب السعودي: <code>3142525843</code>\n"
            "✅ أرسل صورة الإشعار بعد التحويل لتفعيل حسابك فوراً."
        )
        await reply_safe(update.message, pending_msg, reply_markup=inline_pending)
        return

    # 4. User with REJECTED status
    if user_rec.registration_status == "REJECTED":
        reason = getattr(user_rec, "rejection_reason", None) or "البيانات المقدمة غير كافية"
        rejected_msg = (
            "❌ <b>تم رفض طلب التسجيل الخاص بك</b>\n\n"
            f"📝 <b>السبب:</b> {reason}\n\n"
            f"يمكنك التواصل مع الإدارة للاستفسار: @{ADMIN_USERNAME}"
        )
        await reply_safe(update.message, rejected_msg, reply_markup=ReplyKeyboardRemove())
        return

    # 5. User with APPROVED status (waiting for 50s OTP)
    if user_rec.registration_status == "APPROVED":
        otp_url = f"{webapp_url}?telegram_user_id={user_tg_id}&u={user_rec.username or user_tg_id}"
        code_info = get_latest_code_for_user_sync(user_rec.id)
        if code_info and code_info.get("is_valid"):
            code_str = code_info.get("code", "")
            sec_left = code_info.get("seconds_left", 50)
            approved_msg = (
                "🎉 <b>تمت الموافقة على طلب تسجيلك في صحتي!</b>\n\n"
                f"🔑 <b>رمز الدخول المؤقت:</b> <code>{code_str}</code>\n"
                f"⏱️ <b>متبقي من الصلاحية:</b> {sec_left} ثانية!\n\n"
                "اضغط على الزر أدناه لإدخال الرمز وتفعيل اشتراكك لمدة 30 يوماً فوراً:"
            )
        else:
            approved_msg = (
                "🎉 <b>تمت الموافقة على طلب تسجيلك في صحتي!</b>\n\n"
                "اضغط على الزر أدناه لإدخال رمز التحقق المؤقت الخاص بك وتفعيل اشتراكك لمدة 30 يوماً:"
            )
        inline_otp = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 إدخال رمز التحقق وتفعيل البوت", web_app=WebAppInfo(url=otp_url))]
        ])
        await reply_safe(update.message, approved_msg, reply_markup=inline_otp)
        return

    # 6. User with SUSPENDED status
    if user_rec.registration_status == "SUSPENDED" or not user_rec.is_active:
        suspended_msg = (
            "⏸️ <b>حسابك معلق حالياً</b>\n\n"
            f"تم تعليق حسابك من قبل إدارة النظام. يرجى التواصل مع الإدارة لإعادة التفعيل: @{ADMIN_USERNAME}"
        )
        await reply_safe(update.message, suspended_msg, reply_markup=ReplyKeyboardRemove())
        return

    # 7. User with ACTIVE status: Check Subscription
    sub = check_subscription_sync(user_rec.id)
    if not sub["active"]:
        expired_msg = (
            "⚠️ <b>انتهت فترة اشتراكك (30 يوماً)</b>\n\n"
            f"عذراً، لقد انتهت صلاحية استخدامك لنظام الإجازات المرضية. يرجى التواصل مع الإدارة (@{ADMIN_USERNAME}) لتجديد صلاحية حسابك لمدة 30 يوماً أخرى."
        )
        await reply_safe(update.message, expired_msg, reply_markup=ReplyKeyboardRemove())
        return

    # Active and verified! Check if user has any submitted report
    user_reports = get_all_saved_reports_sync(user_id=user_rec.id, telegram_user_id=str(user_tg_id))
    latest_code = user_reports[0]["service_code"] if user_reports else None

    keyboard_rows = [
        [
            KeyboardButton("📝 تقديم تقرير جديد", web_app=WebAppInfo(url=f"{webapp_url}?telegram_user_id={user_tg_id}")),
            KeyboardButton("📋 البيانات السابقة", web_app=WebAppInfo(url=f"{records_url}?telegram_user_id={user_tg_id}")),
        ]
    ]


    keyboard = ReplyKeyboardMarkup(
        keyboard_rows,
        resize_keyboard=True,
        one_time_keyboard=False,
    )

    active_msg = (
        "🏥 <b>مرحباً بك مجدداً في نظام الإجازات المرضية (@SehtyBot)</b>\n\n"
        f"🟢 <b>حالة الاشتراك:</b> نشط (متبقي {sub['days_remaining']} يوم)"
    )


    await reply_safe(update.message, active_msg, reply_markup=keyboard)


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
    msg = (
        f"✏️ <b>تعديل التقرير</b>\n\n"
        f"🔑 رمز الخدمة: <code>{last_code}</code>\n\n"
        "اضغط الزر لفتح النموذج معبأً بالبيانات السابقة وعدّل ما تريد ثم أعد الإرسال."
    )
    await reply_safe(update.message, msg, reply_markup=keyboard)


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
        await update.message.reply_text(f"❌ لم يتم العثور على بيانات للرمز: {last_code}")
        return

    text = (
        f"📄 <b>آخر تقرير محفوظ</b>\n\n"
        f"🔑 رمز الخدمة: <code>{r.get('service_code', '')}</code>\n"
        f"👤 المريض: {r.get('patient_name_ar', '')}\n"
        f"🪪 رقم الهوية: <code>{r.get('national_id', '')}</code>\n"
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
    await reply_safe(update.message, text, reply_markup=markup)


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
            f"رمز الخدمة: {service_code}"
        )
        return

    record_user_activity_sync(telegram_user_id=user_id)
    buttons = [
        [
            InlineKeyboardButton("🔗 التحقق في منصة صحة", url=f"https://seha-sea.com/#/inquiries/slenquiry?id={service_code}"),
        ]
    ]
    markup = InlineKeyboardMarkup(buttons)

    with open(pdf_path, "rb") as f:
        caption = (
            f"✅ <b>تم إنشاء الإجازة المرضية بنجاح!</b>\n"
            f"🔑 رمز الخدمة: <code>{service_code}</code>\n\n"
            f"للتحقق المباشر: اضغط الزر أدناه\n"
            f"أو أرسل: <code>/verify {service_code}</code>"
        )
        try:
            await update.message.reply_document(
                document=f,
                filename=f"SickLeave_{service_code}.pdf",
                caption=caption,
                parse_mode="HTML",
                reply_markup=markup,
            )
        except Exception:
            f.seek(0)
            await update.message.reply_document(
                document=f,
                filename=f"SickLeave_{service_code}.pdf",
                caption=f"تم إنشاء الإجازة المرضية بنجاح! رمز الخدمة: {service_code}",
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
                    caption=f"📄 إعادة إرسال — رمز الخدمة: {service_code}",
                )
        else:
            await query.message.reply_text("❌ ملف PDF غير موجود.")


# ── /verify ────────────────────────────────────────────────────────────────────
async def verify(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    args = ctx.args
    if not args:
        await update.message.reply_text("الاستخدام: /verify <رمز_الخدمة_أو_رقم_الهوية>")
        return

    q = args[0].strip()
    # Check if soft-deleted locally or creator user is soft-deleted
    from db.database import get_single_saved_report_sync, get_user_by_identifier_sync
    trashed = get_single_saved_report_sync(q, include_deleted=True)
    is_hidden = False
    if trashed:
        if trashed.get("is_deleted"):
            is_hidden = True
        else:
            u_id = trashed.get("user_id")
            tg_id = trashed.get("telegram_user_id")
            if u_id or tg_id:
                u = get_user_by_identifier_sync(str(u_id or tg_id), include_deleted=True)
                if u and getattr(u, 'is_deleted', 0):
                    is_hidden = True

    if is_hidden:
        await update.message.reply_text(f"❌ لا يوجد سجل لـ: {q}")
        return

    local_rec = get_single_saved_report_sync(q)
    if local_rec:
        r = local_rec
    else:
        r_w = await get_report(q)
        if not r_w:
            results = await search_by_national_id(q)
            r_w = results[0] if results else None
        if r_w:
            sc_code = r_w.get("service_code", "")
            chk = get_single_saved_report_sync(sc_code, include_deleted=True)
            if chk and (chk.get("is_deleted") or getattr(get_user_by_identifier_sync(str(chk.get("user_id") or chk.get("telegram_user_id")), include_deleted=True), 'is_deleted', 0)):
                r = None
            else:
                r = r_w
        else:
            r = None

    if not r:
        await update.message.reply_text(f"❌ لا يوجد سجل لـ: {q}")
        return

    text = (
        f"✅ <b>نتيجة التحقق</b>\n\n"
        f"🔑 رمز الخدمة: <code>{r.get('service_code', '')}</code>\n"
        f"👤 المريض: {r.get('patient_name_ar', '')}\n"
        f"🪪 رقم الهوية: <code>{r.get('national_id', '')}</code>\n"
        f"📅 الدخول: {r.get('admission_date', '')}\n"
        f"📅 الخروج: {r.get('discharge_date', '')}\n"
        f"⏱️ المدة: {r.get('leave_duration_days', '')} يوم\n"
        f"🏥 المستشفى: {r.get('hospital_name_ar', '')}\n"
        f"👨‍⚕️ الممارس: {r.get('practitioner_name_ar', '')}\n"
    )
    await reply_safe(update.message, text)


# ── Text Handler for "+" & Records Menu ─────────────────────────────────────────
async def handle_text_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    txt = (update.message.text or "").strip()
    webapp_url = ctx.bot_data.get("webapp_url", "")
    base_url = webapp_url.replace("/form", "")
    records_url = f"{base_url}/records"

    user = update.message.from_user
    user_tg_id = str(user.id).strip()
    user_name = (user.username or "").lstrip("@").strip()

    is_admin = (user_tg_id == ADMIN_TELEGRAM_ID) or (user_name.lower() in [u.lower() for u in ADMIN_USERNAMES])
    user_rec = get_user_by_identifier_sync(user_tg_id)

    # If user wants previous records
    if any(k in txt for k in ["+", "➕", "بيانات", "سابق", "سجل", "سجلات", "تعديل"]):
        if not is_admin and (not user_rec or user_rec.registration_status != "ACTIVE"):
            msg = (
                "⚠️ <b>عذراً، لا يمكنك الوصول للبيانات السابقة</b>\n\n"
                "يتطلب فتح السجلات أن يكون حسابك مسجلاً ومفعلاً بموافقة الإدارة.\n"
                "استخدم الأمر /start للتحقق من حالة حسابك أو تقديم طلب تسجيل."
            )
            await reply_safe(update.message, msg)
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📂 عرض البيانات السابقة", web_app=WebAppInfo(url=f"{records_url}?telegram_user_id={user_tg_id}"))]
        ])
        msg = (
            "📋 <b>سجلات وبيانات الأشخاص السابقة</b>\n\n"
            "اضغط على الزر بالأسفل لفتح صفحة السجلات، حيث يمكنك:\n"
            "• عرض بيانات المرضى في خانات منظمة.\n"
            "• نسخ بيانات أي مريض بضغطة زر.\n"
            "• تعديل بيانات أي شخص بالضغط على علامة القلم ✏️.\n"
            "• نقل السجلات إلى سلة المحذوفات أو استرجاعها."
        )
        await reply_safe(update.message, msg, reply_markup=keyboard)
