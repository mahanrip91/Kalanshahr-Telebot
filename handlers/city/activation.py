"""
فعال‌سازی کلان‌شهر: وقتی گروه به حد نصاب عضو برسه یا از حد نصاب پایین بیاد
همچنین: وقتی شهر تازه فعال میشه (از هر مسیری - چه با ورود عضو، چه با تایپ «کلان‌شهر»)،
مالک گروه به‌طور خودکار اولین شهردار میشه.
"""
import random
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message
from sqlalchemy import select

from database.models import City
from config import settings, CITY_LEVELS
from core.economy import get_or_create_user

router = Router(name="city_activation")

DESERT_MESSAGES = [
    "🏜️ اینجا که کویره داداش! نه شهرداری داره نه آب و برق... حداقل {min} نفر باشین تا اسمش بشه کلان‌شهر!",
    "🐫 فعلاً فقط شن و شتر اینجاست! با {min} نفر عضو، کلان‌شهر متولد میشه.",
    "🏚️ این گروه هنوز روستا هم نیست چه برسه به کلان‌شهر! حداقل {min} عضو لازمه.",
]

CITY_BORN_MESSAGES = [
    "🌆 <b>عجب کلان‌شهری شد اینجا!</b>\nاز حالا این گروه رسماً یه کلان‌شهره 🎉",
    "🏙️ <b>تبریک میگم!</b> این گروه به کلان‌شهر تبدیل شد!",
]


async def _get_or_create_city(session, chat_id: int, title: str) -> City:
    result = await session.execute(select(City).where(City.chat_id == chat_id))
    city = result.scalar_one_or_none()
    if not city:
        city = City(chat_id=chat_id, title=title, status=CITY_LEVELS[0]["name"])
        session.add(city)
        await session.commit()
        await session.refresh(city)
    return city


async def assign_owner_as_mayor(bot, session, city: City, chat_id: int):
    """وقتی شهر تازه متولد میشه، مالک واقعی گروه رو به‌عنوان اولین شهردار انتخاب می‌کنه.
    از هر مسیری که شهر فعال بشه صدا زده میشه، نه فقط موقع ورود عضو جدید."""
    if city.mayor_telegram_id:
        return None
    try:
        admins = await bot.get_chat_administrators(chat_id)
    except Exception:
        return None

    owner = next((a for a in admins if a.status == "creator"), None)
    if not owner:
        return None

    await get_or_create_user(session, owner.user.id, owner.user.username, owner.user.first_name or "")

    city.mayor_telegram_id = owner.user.id
    city.mayor_elected_at = datetime.utcnow()
    city.mayor_last_active = datetime.utcnow()
    await session.commit()
    return owner.user


async def check_and_update_city_status(message_or_event, session, bot, chat_id: int, title: str):
    """
    چک میکنه تعداد اعضا و وضعیت شهر رو آپدیت میکنه.
    اگه شهر تازه فعال شده باشه (از هر مسیری)، مالک گروه رو خودکار شهردار میکنه.
    برمیگردونه (city, member_count, status_changed, new_mayor_user_or_None)
    """
    member_count = await bot.get_chat_member_count(chat_id)
    city = await _get_or_create_city(session, chat_id, title)

    was_active = city.is_active
    now_active = member_count >= settings.MIN_GROUP_MEMBERS
    city.is_active = now_active
    city.title = title
    await session.commit()

    changed = was_active != now_active
    new_mayor = None
    if now_active:
        # چه تازه فعال شده باشه چه از قبل فعال بوده، اگه شهردار نداره الان تعیینش کن
        new_mayor = await assign_owner_as_mayor(bot, session, city, chat_id)

    return city, member_count, changed, new_mayor


@router.message(F.chat.type.in_({"group", "supergroup"}), F.new_chat_members)
async def on_members_joined(message: Message, session):
    city, count, changed, new_mayor = await check_and_update_city_status(
        message, session, message.bot, message.chat.id, message.chat.title or ""
    )
    if changed:
        if city.is_active:
            text = random.choice(CITY_BORN_MESSAGES)
            if new_mayor:
                text += (
                    f"\n\n👑 مالک گروه، <b>{new_mayor.first_name}</b>، به‌طور خودکار به‌عنوان "
                    f"اولین شهردار این کلان‌شهر انتخاب شد!"
                )
            else:
                text += "\n\nحالا وقتشه از «شهرداری» یه شهردار انتخاب کنید و شهرتون رو آباد کنید!"
            await message.answer(text)
        else:
            await message.answer(random.choice(DESERT_MESSAGES).format(min=settings.MIN_GROUP_MEMBERS))


@router.message(F.chat.type.in_({"group", "supergroup"}), F.left_chat_member)
async def on_member_left(message: Message, session):
    city, count, changed, _ = await check_and_update_city_status(
        message, session, message.bot, message.chat.id, message.chat.title or ""
    )
    if changed and not city.is_active:
        await message.answer(random.choice(DESERT_MESSAGES).format(min=settings.MIN_GROUP_MEMBERS))
