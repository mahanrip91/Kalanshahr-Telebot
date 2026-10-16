"""
هسته اقتصادی مرکزی ربات.
تمام تغییرات پولی و XP باید از اینجا عبور کنن تا یکپارچه و اتمیک باشن
و از دوبل‌اسپند و باگ جلوگیری بشه.
"""
import random
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, Transaction
from config import xp_needed_for_level


async def _generate_unique_account_number(session: AsyncSession) -> str:
    while True:
        candidate = f"KLS-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"
        existing = await session.execute(select(User).where(User.account_number == candidate))
        if not existing.scalar_one_or_none():
            return candidate


async def ensure_account_number(session: AsyncSession, user: User) -> str:
    """اگه کاربر شماره حساب نداشت، یکی میسازه (برای کاربرای قدیمی هم کار میکنه)"""
    if user.account_number:
        return user.account_number
    user.account_number = await _generate_unique_account_number(session)
    await session.commit()
    return user.account_number


async def get_or_create_user(session: AsyncSession, telegram_id: int,
                              username: str = None, first_name: str = "") -> tuple[User, bool]:
    """کاربر رو برمیگردونه، اگه نبود میسازتش. bool دوم یعنی تازه ساخته شده یا نه"""
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        changed = False
        if username and user.username != username:
            user.username = username
            changed = True
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            changed = True
        if changed:
            await session.commit()
        return user, False

    account_number = await _generate_unique_account_number(session)
    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name or "",
        account_number=account_number,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user, True


async def log_transaction(session: AsyncSession, user_id: int, ttype: str,
                           amount: float, description: str = ""):
    tx = Transaction(user_id=user_id, type=ttype, amount=amount, description=description)
    session.add(tx)


async def add_cash(session: AsyncSession, user: User, amount: float,
                    reason: str = "") -> None:
    """افزایش نقدی کاربر - atomic در سطح session"""
    user.cash += amount
    await log_transaction(session, user.id, "cash_add", amount, reason)
    await session.commit()


async def remove_cash(session: AsyncSession, user: User, amount: float,
                       reason: str = "") -> bool:
    """کاهش نقدی کاربر. اگه پول کافی نبود False برمیگردونه و کاری نمیکنه"""
    if user.cash < amount:
        return False
    user.cash -= amount
    await log_transaction(session, user.id, "cash_remove", -amount, reason)
    await session.commit()
    return True


async def add_xp(session: AsyncSession, user: User, amount: int) -> dict:
    """
    اضافه کردن XP و بررسی لول‌آپ.
    خروجی: {"leveled_up": bool, "new_level": int, "levels_gained": int}
    """
    user.xp += amount
    levels_gained = 0
    while user.xp >= xp_needed_for_level(user.level):
        user.xp -= xp_needed_for_level(user.level)
        user.level += 1
        levels_gained += 1
    await session.commit()
    return {
        "leveled_up": levels_gained > 0,
        "new_level": user.level,
        "levels_gained": levels_gained,
    }


def is_in_prison(user: User) -> bool:
    return bool(user.prison_until and user.prison_until > datetime.utcnow())
