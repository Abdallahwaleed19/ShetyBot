"""
services/email_service.py — Email notification service for registrations & OTPs.
"""
import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, Any

from config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    SMTP_FROM,
    ADMIN_EMAIL,
    OTP_TTL_SECONDS,
)

logger = logging.getLogger(__name__)


def _send_email_sync(to_email: str, subject: str, html_body: str) -> bool:
    """Send an HTML email via SMTP synchronously."""
    to_clean = str(to_email).strip().lower()
    if not to_clean or "@" not in to_clean:
        logger.warning(f"Invalid recipient email: {to_email}")
        return False

    # If SMTP credentials are not configured, log email contents for debugging/development
    if not SMTP_USER or not SMTP_PASS:
        logger.info(
            f"[EMAIL NOTICE] SMTP not configured. Simulated email to: {to_clean}\n"
            f"Subject: {subject}\n"
            f"Body preview: {html_body[:250]}..."
        )
        return True

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"SehtyBot صحتي <{SMTP_FROM}>"
        msg["To"] = to_clean
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)

        logger.info(f"Email successfully sent to {to_clean} with subject: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_clean}: {e}")
        return False


async def send_email_async(to_email: str, subject: str, html_body: str) -> bool:
    """Send an email asynchronously without blocking the event loop."""
    return await asyncio.to_thread(_send_email_sync, to_email, subject, html_body)


def send_admin_new_registration_notification_sync(user_data: Dict[str, Any]) -> bool:
    """Notify Admin (ramo.711.vip@gmail.com) of a new registration request synchronously."""
    subject = f"🔔 طلب تسجيل مستخدم جديد: {user_data.get('full_name_ar', 'مستخدم جديد')}"
    html = f"""
    <div dir="rtl" style="font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:#0B2763;color:#ffffff;padding:25px;border-radius:16px;max-width:600px;margin:0 auto;">
      <h2 style="color:#38bdf8;margin-bottom:12px;border-bottom:1px solid rgba(255,255,255,0.2);padding-bottom:8px;">
        📋 إشعار طلب تسجيل حساب جديد في SehtyBot
      </h2>
      <p style="font-size:15px;color:#cbd5e1;line-height:1.6">
        تم استلام طلب تسجيل جديد بحالة <b>قيد المراجعة (PENDING_APPROVAL)</b>:
      </p>
      
      <table style="width:100%;border-collapse:collapse;margin:20px 0;background:rgba(255,255,255,0.06);border-radius:12px;overflow:hidden;">
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.1);color:#93c5fd;font-weight:bold;width:40%;">الاسم بالعربية:</td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.1);color:#fff;">{user_data.get('full_name_ar', '-')}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.1);color:#93c5fd;font-weight:bold;">الاسم بالإنجليزية:</td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.1);color:#fff;">{user_data.get('full_name_en', '-')}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.1);color:#93c5fd;font-weight:bold;">البريد الإلكتروني:</td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.1);color:#38bdf8;">{user_data.get('email', '-')}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.1);color:#93c5fd;font-weight:bold;">رقم Telegram ID:</td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.1);color:#fff;"><code>{user_data.get('telegram_user_id', '-')}</code></td>
        </tr>
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.1);color:#93c5fd;font-weight:bold;">اسم مستخدم Telegram:</td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,0.1);color:#fff;">@{user_data.get('username', '-')}</td>
        </tr>
        <tr>
          <td style="padding:10px 14px;color:#93c5fd;font-weight:bold;">تاريخ ووقت الطلب:</td>
          <td style="padding:10px 14px;color:#fff;">{user_data.get('created_at', '-')}</td>
        </tr>
      </table>

      <div style="background:rgba(56,189,248,0.15);border:1px solid #38bdf8;border-radius:10px;padding:14px;text-align:center;margin-top:20px;">
        <p style="margin:0 0 8px;font-size:14px;color:#fff;">يمكنك مراجعة هذا الطلب وقبوله أو رفضه مباشرة من لوحة الإدارة:</p>
        <a href="https://sehtybot.fly.dev/admin?key=admin123" style="display:inline-block;background:#38bdf8;color:#0B2763;font-weight:bold;text-decoration:none;padding:10px 24px;border-radius:8px;font-size:14px;">
          🔐 فتح لوحة الإدارة
        </a>
      </div>
    </div>
    """
    return _send_email_sync(ADMIN_EMAIL, subject, html)


async def send_admin_new_registration_notification(user_data: Dict[str, Any]) -> bool:
    """Notify Admin asynchronously."""
    return await asyncio.to_thread(send_admin_new_registration_notification_sync, user_data)


def send_user_otp_email_sync(user_email: str, otp_code: str, user_name: str = "") -> bool:
    """Send the 30-second verification OTP code to the approved user's email synchronously."""
    subject = "🔐 كود التحقق لتفعيل حسابك في منصة صحة"
    html = f"""
    <div dir="rtl" style="font-family:'Segoe UI',Tahoma,Arial,sans-serif;background:#0B2763;color:#ffffff;padding:25px;border-radius:18px;max-width:500px;margin:0 auto;text-align:center;">
      <div style="font-size:42px;margin-bottom:8px;">🏥</div>
      <h2 style="color:#ffffff;margin-bottom:6px;font-weight:800">مرحباً {user_name or 'بك'}</h2>
      <p style="font-size:14px;color:#cbd5e1;margin-bottom:20px;">
        رمز التحقق المؤقت لتسجيل الدخول وتفعيل حسابك في منصة صحتي:
      </p>

      <div style="background:rgba(16,185,129,0.18);border:2px dashed #10b981;border-radius:16px;padding:18px 24px;margin:20px auto;display:inline-block;min-width:220px;">
        <div style="font-size:13px;color:#6ee7b7;margin-bottom:4px;font-weight:600">رمز الدخول المؤقت:</div>
        <div style="font-size:36px;font-weight:800;color:#10b981;letter-spacing:10px;font-family:monospace;">{otp_code}</div>
      </div>

      <div style="background:rgba(239,68,68,0.15);border:1px solid #ef4444;border-radius:10px;padding:10px 14px;margin:18px 0;color:#fca5a5;font-size:13px;font-weight:bold;">
        ⏱️ تنبيه هام: هذا الرمز صالح لمدة {OTP_TTL_SECONDS} ثانية فقط!
      </div>

      <p style="font-size:12px;color:#93c5fd;margin-top:20px;opacity:0.8;">
        إذا انتهت الصلاحية، يمكنك طلب رمز جديد من خلال النموذج.
      </p>
    </div>
    """
    return _send_email_sync(user_email, subject, html)


async def send_user_otp_email(user_email: str, otp_code: str, user_name: str = "") -> bool:
    """Send the 30-second verification OTP code asynchronously."""
    return await asyncio.to_thread(send_user_otp_email_sync, user_email, otp_code, user_name)
