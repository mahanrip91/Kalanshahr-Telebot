"""
وضعیت کلی شهر و منوی ورودی «کلان‌شهر»
شهر بر اساس چند معیار با هم ارتقا پیدا می‌کنه: خزانه، تعداد اعضای گروه،
تعداد کاربران فعال (کمک‌کننده به خزانه)، و تعداد مغازه‌های اهالی شهر.
"""
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select, func

from database.models import City, CityContribution, User, Shop
from core.texts import header
from core.keyboards import city_kb
from config import settings, CITY_LEVELS
from utils.formatting import fmt_money, fmt_datetime
from handlers.city.activation import check_and_update_city_status

router = Router(name="city_status")


async def _city_metrics(session, city: City, member_count: int) -> dict:
    contributors_result = await session.execute(
        select(func.count(func.distinct(CityContribution.telegram_id)))
        .where(CityContribution.city_id == city.id)
    )
    contributors = contributors_result.scalar() or 0

    contributor_ids_result = await session.execute(
        select(CityContribution.telegram_id).distinct().where(CityContribution.city_id == city.id)
    )
    contributor_tg_ids = [row[0] for row in contributor_ids_result.all()]

    shops = 0
    if contributor_tg_ids:
        user_ids_result = await session.execute(
            select(User.id).where(User.telegram_id.in_(contributor_tg_ids))
        )
        user_ids = [row[0] for row in user_ids_result.all()]
        if user_ids:
            shops_result = await session.execute(
                select(func.count(Shop.id)).where(Shop.user_id.in_(user_ids))
            )
            shops = shops_result.scalar() or 0

    return {
        "treasury": city.treasury,
        "members": member_count,
        "contributors": contributors,
        "shops": shops,
    }


def _level_met(metrics: dict, level: dict) -> bool:
    return (
        metrics["treasury"] >= level["min_treasury"]
        and metrics["members"] >= level["min_members"]
        and metrics["contributors"] >= level["min_contributors"]
        and metrics["shops"] >= level["min_shops"]
    )


def current_city_level(metrics: dict) -> dict:
    level = CITY_LEVELS[0]
    for lv in CITY_LEVELS:
        if _level_met(metrics, lv):
            level = lv
    return level


def next_city_level(metrics: dict):
    for lv in CITY_LEVELS:
        if not _level_met(metrics, lv):
            return lv
    return None


def _progress_line(label: str, current, need) -> str:
    if isinstance(current, float) or current >= 1000:
        current_s, need_s = fmt_money(current), fmt_money(need)
    else:
        current_s, need_s = str(int(current)), str(int(need))
    mark = "✅" if current >= need else "🔸"
    return f"{mark} {label}: <code>{current_s}</code> / <code>{need_s}</code>"


async def build_city_status_text(session, city: City, member_count: int = None, bot=None) -> str:
    if not city:
        return f"{header('🏙️ کلان‌شهر')}\n\nاین گروه هنوز هیچ داده‌ای نداره. یه پیام تو گروه بفرست تا فعال بشه."

    if member_count is None and bot is not None:
        try:
            member_count = await bot.get_chat_member_count(city.chat_id)
        except Exception:
            member_count = 0
    member_count = member_count or 0

    metrics = await _city_metrics(session, city, member_count)
    level = current_city_level(metrics)
    nxt = next_city_level(metrics)

    text = (
        f"{header('🏙️ وضعیت کلان‌شهر')}\n\n"
        f"🏷️ نام: <b>{city.title}</b>\n"
        f"🌆 سطح فعلی: <b>{level['name']}</b>\n"
    )

    if not city.is_active:
        text += f"\n⚠️ این گروه هنوز به حد نصاب {settings.MIN_GROUP_MEMBERS} عضو نرسیده و کلان‌شهر رسمی نیست.\n"
        text += f"👥 اعضای فعلی: <b>{member_count}</b> / {settings.MIN_GROUP_MEMBERS}"
        return text

    if city.mayor_telegram_id:
        text += f"👑 شهردار: <a href='tg://user?id={city.mayor_telegram_id}'>مشاهده پروفایل</a>\n"
    else:
        text += "😐 این شهر هنوز شهردار نداره.\n"

    text += "\n"
    if nxt:
        text += f"📈 <b>پیشرفت تا سطح «{nxt['name']}»:</b>\n"
        text += _progress_line("💰 خزانه", metrics["treasury"], nxt["min_treasury"]) + "\n"
        text += _progress_line("👥 اعضای گروه", metrics["members"], nxt["min_members"]) + "\n"
        text += _progress_line("🙋 اهالی فعال", metrics["contributors"], nxt["min_contributors"]) + "\n"
        text += _progress_line("🛒 مغازه‌های شهر", metrics["shops"], nxt["min_shops"])
    else:
        text += "🏆 این شهر به بالاترین سطح ممکن رسیده!"

    return text


@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.in_({"🏙️ کلان‌شهر", "کلان‌شهر", "کلانشهر"}))
async def city_menu_group(message: Message, session):
    city, count, changed, new_mayor = await check_and_update_city_status(
        message, session, message.bot, message.chat.id, message.chat.title or ""
    )
    if new_mayor:
        await message.answer(
            f"👑 مالک گروه، <b>{new_mayor.first_name}</b>، به‌طور خودکار شهردار این کلان‌شهر شد!"
        )
    text = await build_city_status_text(session, city, member_count=count)
    await message.answer(text, reply_markup=city_kb(city.is_active))


@router.message(F.chat.type == "private", F.text.in_({"🏙️ کلان‌شهر", "کلان‌شهر", "کلانشهر"}))
async def city_menu_private(message: Message):
    await message.answer(
        f"{header('🏙️ کلان‌شهر')}\n\n"
        "این بخش فقط داخل گروه‌ها فعاله! ربات رو به یه گروه اضافه کن و "
        "وقتی گروه به حداقل عضو رسید، همینجا بنویس «کلان‌شهر» تا شهر متولد بشه 🌆"
    )


@router.callback_query(F.data == "city_status")
async def city_status_cb(callback: CallbackQuery, session):
    # همیشه از check_and_update_city_status استفاده میشه تا اگه شهر هنوز ساخته نشده، همینجا ساخته بشه
    city, count, changed, new_mayor = await check_and_update_city_status(
        callback, session, callback.bot, callback.message.chat.id,
        callback.message.chat.title or ""
    )
    text = await build_city_status_text(session, city, member_count=count)
    # یه خط ساعت آخرین بروزرسانی اضافه میشه تا متن همیشه با قبلش فرق کنه و دکمه
    # همیشه یه واکنش دیداری بده (وگرنه وقتی هیچی عوض نشده تلگرام ادیت رو رد می‌کنه)
    refreshed_at = fmt_datetime(datetime.utcnow(), "%H:%M:%S")
    text += f"\n\n<i>🔄 آخرین بروزرسانی: {refreshed_at}</i>"
    try:
        await callback.message.edit_text(text, reply_markup=city_kb(city.is_active if city else False))
    except TelegramBadRequest:
        pass
    if new_mayor:
        await callback.answer(f"👑 {new_mayor.first_name} به‌طور خودکار شهردار شد!", show_alert=True)
    else:
        await callback.answer()
