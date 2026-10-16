"""
پنل ادمین شهر — ۱۰۰٪ شیشه‌ای (Inline Keyboard)
فقط ادمین‌های واقعی گروه بهش دسترسی دارن.
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, desc, func

from database.models import User, City, CityContribution
from core.texts import header
from utils.formatting import fmt_money

router = Router(name="city_admin_panel")


class CityAdminStates(StatesGroup):
    set_tax = State()


async def _is_group_admin(message: Message) -> bool:
    try:
        member = await message.bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def city_admin_kb() -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.button(text="📊 آمار شهر", callback_data="city_admin:stats", style="primary")
    b.button(text="🏆 کمک‌کنندگان", callback_data="city_admin:contributors", style="primary")
    b.button(text="💰 تنظیم مالیات", callback_data="city_admin:tax", style="success")
    b.button(text="🔙 بستن", callback_data="city_admin:close", style="danger")
    b.adjust(2, 2)
    return b


@router.message(F.chat.type.in_({"group", "supergroup"}), Command("مدیریت_شهر"))
@router.message(F.chat.type.in_({"group", "supergroup"}), F.text.in_({"⚙️ مدیریت شهر", "مدیریت شهر"}))
async def city_admin_panel(message: Message, session):
    if not await _is_group_admin(message):
        await message.answer("❌ این بخش فقط برای ادمین‌های گروهه!")
        return
    result = await session.execute(select(City).where(City.chat_id == message.chat.id))
    city = result.scalar_one_or_none()
    if not city:
        await message.answer("این گروه هنوز فعال نشده. اول «فعال‌سازی شهر» رو بزن.")
        return
    await message.answer(
        f"{header('⚙️ پنل مدیریت شهر')}\n\n"
        f"🏙️ نام: <b>{city.title}</b>\n"
        f"🌆 سطح: <b>{city.status}</b>\n"
        f"💰 خزانه: <code>{fmt_money(city.treasury)}</code>\n"
        f"👑 شهردار: {'دارد' if city.mayor_telegram_id else 'ندارد'}\n"
        f"📊 مالیات: <b>{city.tax_rate * 100:.1f}%</b>\n\n"
        f"یه گزینه رو انتخاب کن 👇",
        reply_markup=city_admin_kb().as_markup()
    )


@router.callback_query(F.data == "city_admin:back")
async def city_admin_back(callback: CallbackQuery, session):
    member = await callback.bot.get_chat_member(callback.message.chat.id, callback.from_user.id)
    if member.status not in ("administrator", "creator"):
        await callback.answer("⛔", show_alert=True)
        return
    result = await session.execute(select(City).where(City.chat_id == callback.message.chat.id))
    city = result.scalar_one_or_none()
    text = (
        f"{header('⚙️ پنل مدیریت شهر')}\n\n"
        f"🏙️ نام: <b>{city.title}</b>\n"
        f"🌆 سطح: <b>{city.status}</b>\n"
        f"💰 خزانه: <code>{fmt_money(city.treasury)}</code>\n"
        f"👑 شهردار: {'دارد' if city.mayor_telegram_id else 'ندارد'}\n"
        f"📊 مالیات: <b>{city.tax_rate * 100:.1f}%</b>\n\n"
        f"یه گزینه رو انتخاب کن 👇"
    )
    await callback.message.edit_text(text, reply_markup=city_admin_kb().as_markup())
    await callback.answer()


@router.callback_query(F.data == "city_admin:close")
async def city_admin_close(callback: CallbackQuery):
    member = await callback.bot.get_chat_member(callback.message.chat.id, callback.from_user.id)
    if member.status not in ("administrator", "creator"):
        await callback.answer("⛔", show_alert=True)
        return
    await callback.message.delete()
    await callback.answer("پنل بسته شد.", show_alert=True)


@router.callback_query(F.data == "city_admin:stats")
async def city_admin_stats(callback: CallbackQuery, session):
    member = await callback.bot.get_chat_member(callback.message.chat.id, callback.from_user.id)
    if member.status not in ("administrator", "creator"):
        await callback.answer("⛔", show_alert=True)
        return
    result = await session.execute(select(City).where(City.chat_id == callback.message.chat.id))
    city = result.scalar_one_or_none()
    if not city:
        await callback.answer("شهر پیدا نشد.", show_alert=True)
        return
    total_members = (await session.execute(
        select(func.count(User.id))
        .join(CityContribution, CityContribution.telegram_id == User.telegram_id)
        .where(CityContribution.city_id == city.id)
    )).scalar() or 0
    text = (
        f"{header('📊 آمار شهر')}\n\n"
        f"🏙️ نام: <b>{city.title}</b>\n"
        f"🆔 چت: <code>{city.chat_id}</code>\n"
        f"🌆 سطح: <b>{city.status}</b>\n"
        f"💰 خزانه: <code>{fmt_money(city.treasury)}</code>\n"
        f"👥 تعداد کمک‌کنندگان: <b>{total_members}</b>\n"
        f"📊 مالیات فعلی: <b>{city.tax_rate * 100:.1f}%</b>"
    )
    b = InlineKeyboardBuilder()
    b.button(text="🔙 بازگشت", callback_data="city_admin:back", style="primary")
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "city_admin:contributors")
async def city_admin_contributors(callback: CallbackQuery, session):
    member = await callback.bot.get_chat_member(callback.message.chat.id, callback.from_user.id)
    if member.status not in ("administrator", "creator"):
        await callback.answer("⛔", show_alert=True)
        return
    result = await session.execute(select(City).where(City.chat_id == callback.message.chat.id))
    city = result.scalar_one_or_none()
    if not city:
        await callback.answer("شهر پیدا نشد.", show_alert=True)
        return
    sum_result = await session.execute(
        select(CityContribution.telegram_id, func.sum(CityContribution.amount).label("total"))
        .where(CityContribution.city_id == city.id)
        .group_by(CityContribution.telegram_id)
        .order_by(desc("total"))
    )
    lines = [f"{header('🏆 برترین کمک‌کنندگان خزانه')}\n"]
    rows = sum_result.all()
    if not rows:
        lines.append("هنوز کسی کمک نکرده.")
    else:
        for i, (tg_id, total) in enumerate(rows[:10], 1):
            user_r = await session.execute(select(User).where(User.telegram_id == tg_id))
            u = user_r.scalar_one_or_none()
            name = u.first_name if u else str(tg_id)
            lines.append(f"{i}. {name} — <code>{fmt_money(total)}</code>")
    b = InlineKeyboardBuilder()
    b.button(text="🔙 بازگشت", callback_data="city_admin:back", style="primary")
    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "city_admin:tax")
async def city_admin_tax_start(callback: CallbackQuery, state: FSMContext):
    member = await callback.bot.get_chat_member(callback.message.chat.id, callback.from_user.id)
    if member.status not in ("administrator", "creator"):
        await callback.answer("⛔", show_alert=True)
        return
    await state.set_state(CityAdminStates.set_tax)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="city_admin:back", style="danger")
    await callback.message.edit_text(
        "💰 <b>تنظیم مالیات شهر</b>\n\n"
        "درصد مالیات رو بفرست (عدد بین ۰ تا ۵۰):",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(CityAdminStates.set_tax, F.text)
async def city_admin_tax_set(message: Message, state: FSMContext, session):
    try:
        val = float(message.text.replace("%", "").strip())
        if not (0 <= val <= 50):
            raise ValueError
    except ValueError:
        await message.answer("❌ عدد نامعتبر. یه عدد بین ۰ تا ۵۰ بفرست:")
        return
    result = await session.execute(select(City).where(City.chat_id == message.chat.id))
    city = result.scalar_one_or_none()
    if not city:
        await message.answer("❌ شهر پیدا نشد.")
        await state.clear()
        return
    city.tax_rate = val / 100
    await session.commit()
    await state.clear()
    b = InlineKeyboardBuilder()
    b.button(text="🔙 بازگشت", callback_data="city_admin:back", style="primary")
    await message.answer(
        f"✅ مالیات شهر به <b>{val}%</b> تنظیم شد.",
        reply_markup=b.as_markup()
    )
