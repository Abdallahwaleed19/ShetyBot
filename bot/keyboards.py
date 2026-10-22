"""
bot/keyboards.py — Reusable inline keyboards.
القيم تطابق enum في MySQL: 'government' | 'private'
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def report_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("تقرير إجازة مرضية", callback_data="تقرير إجازة مرضية")],
    ])


def hospital_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🏛️ حكومي  (Government)", callback_data="government"),
            InlineKeyboardButton("🏨 خاص  (Private)",      callback_data="private"),
        ]
    ])


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأكيد وإنشاء PDF", callback_data="confirm"),
            InlineKeyboardButton("❌ إلغاء",             callback_data="cancel"),
        ]
    ])


def skip_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭️ تخطي", callback_data="skip")],
    ])
