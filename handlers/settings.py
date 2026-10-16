"""
منوی تنظیمات ساده
"""
from aiogram import Router, F
from aiogram.types import Message

from database.models import User
from core.texts import header
from core.economy import ensure_account_number
from utils.formatting import fmt_datetime

router = Router(name="settings")


@router.message(F.text.in_({"⚙️ تنظیمات", "تنظیمات"}))
async def settings_menu(message: Message, session, db_user: User):
    await ensure_account_number(session, db_user)
    text = (
        f"{header('⚙️ تنظیمات')}\n\n"
        f"🆔 آیدی عددی تو: <code>{db_user.telegram_id}</code>\n"
        f"💳 شماره حساب بانکی: <code>{db_user.account_number}</code>\n"
        f"📅 تاریخ عضویت: <code>{fmt_datetime(db_user.created_at, '%Y-%m-%d')}</code>\n\n"
        f"دستورات مفید:\n"
        f"• <code>انتقال پول</code> — فرستادن پول نقدی به کاربر دیگه (با آیدی/یوزرنیم)\n"
        f"• «🏦 بانک → انتقال به حساب» — فرستادن پول بانکی با شماره حساب\n"
        f"• <code>/لغو</code> — لغو هر عملیات نیمه‌کاره\n\n"
        f"💡 همه‌ی بخش‌های ربات رو می‌تونی با تایپ کردن اسمشون هم صدا بزنی، چه تو خصوصی چه تو گروه.\n\n"
        f"ساخته‌شده با ❤️ برای کلان‌شهر"
    )
    await message.answer(text)
