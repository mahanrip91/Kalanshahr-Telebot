"""
برای اکشن‌های ساده (کار، سود بانکی، جمع‌آوری اجاره، فروش مغازه، جایزه روزانه):
نتیجه رو نشون بده، بعد از چند ثانیه خودش برگرده به همون منویی که قبلش بود.
برای چیزای مهم‌تر مثل کازینو و خلاف استفاده نمیشه (اونجا نتیجه باید بمونه).
"""
import asyncio
from aiogram.types import Message


async def revert_after(message: Message, text: str, reply_markup=None, delay: int = 5):
    """بعد از delay ثانیه، پیام رو به متن/کیبورد قبلی برمی‌گردونه. خطاها رو بی‌سروصدا نادیده میگیره
    (مثلاً اگه کاربر پیام رو پاک کرده باشه یا پیام قبلاً ادیت شده باشه)."""
    await asyncio.sleep(delay)
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except Exception:
        pass


def schedule_revert(message: Message, text: str, reply_markup=None, delay: int = 5):
    """نسخه‌ی fire-and-forget - همینو صدا بزن، منتظر نمون."""
    asyncio.create_task(revert_after(message, text, reply_markup, delay))
