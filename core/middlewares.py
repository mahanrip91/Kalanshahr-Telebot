"""
میان‌افزارهای مشترک:
- باز کردن session دیتابیس برای هر آپدیت
- ساخت/دریافت خودکار کاربر
- چک اخراج/بن بودن کاربر
"""
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import Update, Message, CallbackQuery

from database.engine import async_session
from core.economy import get_or_create_user
from core.texts import KICKED_TEXT


class DBUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Update, Dict[str, Any]], Awaitable[Any]],
        event: Update,
        data: Dict[str, Any],
    ) -> Any:
        tg_user = data.get("event_from_user")

        async with async_session() as session:
            data["session"] = session

            if tg_user is not None and not tg_user.is_bot:
                user, is_new = await get_or_create_user(
                    session, tg_user.id, tg_user.username, tg_user.first_name
                )
                data["db_user"] = user
                data["is_new_user"] = is_new

                if user.is_banned:
                    if isinstance(event, Message):
                        await event.answer(KICKED_TEXT)
                    elif isinstance(event, CallbackQuery):
                        await event.answer("🚫 شما توسط مالک ربات اخراج شدید.", show_alert=True)
                    return
            else:
                data["db_user"] = None

            return await handler(event, data)
