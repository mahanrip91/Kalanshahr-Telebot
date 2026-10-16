"""
زندان: مشاهده وضعیت زندانی و پرداخت وثیقه (با تایید/لغو).
build_prison_block از menu_router.py هم صدا زده میشه تا هرجا کاربر زندانیه،
یه پیام شیک و دکمه‌ی وثیقه نشونش بده - نه فقط داخل منوی «زندان شهر».
"""
from datetime import datetime
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from database.models import User, City
from core.texts import header
from core.economy import is_in_prison, log_transaction
from utils.formatting import fmt_money, fmt_seconds

router = Router(name="city_prison")

BAIL_PER_MINUTE = 150

SECTION_MESSAGES = {
    "کار": "💼 نمیتونی بری سرکار، از پشت میله‌ها که نمیشه کار کرد!",
    "بانک": "🏦 بانک‌ها به زندانی‌ها اعتماد ندارن، از اینجا نمیتونی بری تو!",
    "کازینو": "🎰 کازینو برای آدمای آزاده، تو الان مهمون ناخونده‌ی زندانی!",
    "خلاف": "🕵️ یکی از قبل خلاف کردی و گیر افتادی، بازم میخوای خلاف کنی؟! اول آزاد شو.",
    "ساخت‌وساز": "🏗️ کارگرا منتظر یه مالک آزادن، از پشت میله که نمیشه نقشه کشید!",
    "مغازه‌داری": "🛒 مغازه‌ت داره غبار می‌گیره، ولی تا آزاد نشی دستت بهش نمی‌رسه!",
    "بازار مالی": "📈 بازار منتظر تو نمی‌مونه، ولی تو الان جای دیگه‌ای سرگرمی!",
    "جوایز": "🎁 جایزه‌ها برای آدمای آزاد، نه مهمونای زندان!",
    "رتبه‌بندی": "📊 فعلاً رتبه‌ت داره از دور خارج میشه، زودتر آزاد شو!",
    "کلان‌شهر": "🏙️ شهر بدون تو هم می‌چرخه، ولی تو باید اول از زندان بیای بیرون!",
}

DEFAULT_MESSAGE = "🚔 از پشت میله‌های زندان که نمیشه کاری کرد!"


def build_prison_block(db_user: User, section: str = None):
    """پیام و builder کیبورد بلاک‌شدن به‌خاطر زندانی بودن - برای استفاده از هر جای ربات.
    خروجی: (text, InlineKeyboardBuilder) - caller میتونه دکمه‌ی بیشتر اضافه کنه و بعد as_markup() بزنه."""
    remain_sec = (db_user.prison_until - datetime.utcnow()).total_seconds()
    flavor = SECTION_MESSAGES.get(section, DEFAULT_MESSAGE)

    text = (
        f"{header('🚔 زندانی هستی!')}\n\n"
        f"{flavor}\n\n"
        f"⛓️ دلیل: {db_user.prison_reason or 'نامشخص'}\n"
        f"⏳ زمان باقی‌مانده: <code>{fmt_seconds(remain_sec)}</code>"
    )
    b = InlineKeyboardBuilder()
    b.button(text="💰 پرداخت وثیقه و آزادی فوری", callback_data="prison_bail_info", style="success")
    b.adjust(1)
    return text, b


@router.callback_query(F.data == "city_prison")
async def prison_menu(callback: CallbackQuery, session, db_user: User):
    result = await session.execute(select(City).where(City.chat_id == callback.message.chat.id))
    city = result.scalar_one_or_none()
    if not city or not city.is_active:
        await callback.answer("❌ این گروه هنوز کلان‌شهر نیست!", show_alert=True)
        return

    if is_in_prison(db_user):
        text, b = build_prison_block(db_user, "کلان‌شهر")
        b.button(text="🔙 بازگشت", callback_data="city_back")
        b.adjust(1)
        await callback.message.edit_text(text, reply_markup=b.as_markup())
    else:
        text = f"{header('🚔 زندان کلان‌شهر')}\n\n✅ تو الان آزادی! کاری نکن که سر از زندان دربیاری 😄"
        b = InlineKeyboardBuilder()
        b.button(text="🔙 بازگشت", callback_data="city_back")
        await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "prison_bail_info")
async def prison_bail_info(callback: CallbackQuery, db_user: User):
    if not is_in_prison(db_user):
        await callback.answer("✅ تو الان زندانی نیستی!", show_alert=True)
        return

    remain_sec = (db_user.prison_until - datetime.utcnow()).total_seconds()
    bail = round(remain_sec / 60 * BAIL_PER_MINUTE)

    text = (
        f"{header('💰 پرداخت وثیقه')}\n\n"
        f"💵 موجودی نقد تو: <code>{fmt_money(db_user.cash)}</code>\n"
        f"💰 مبلغ وثیقه: <code>{fmt_money(bail)}</code>\n"
        f"⏳ زمان باقی‌مانده اگه پرداخت نکنی: <code>{fmt_seconds(remain_sec)}</code>\n\n"
        f"مطمئنی میخوای پرداخت کنی و آزاد شی؟"
    )
    b = InlineKeyboardBuilder()
    b.button(text="✅ تایید و پرداخت", callback_data="prison_bail_confirm", style="success")
    b.button(text="🔙 برگشت", callback_data="prison_bail_cancel", style="danger")
    b.adjust(2)
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "prison_bail_confirm")
async def prison_bail_confirm(callback: CallbackQuery, session, db_user: User):
    if not is_in_prison(db_user):
        await callback.answer("✅ تو الان زندانی نیستی!", show_alert=True)
        return

    remain_sec = (db_user.prison_until - datetime.utcnow()).total_seconds()
    bail = round(remain_sec / 60 * BAIL_PER_MINUTE)

    if db_user.cash < bail:
        await callback.answer(f"❌ پولت کافی نیست! وثیقه: {fmt_money(bail)} تومان", show_alert=True)
        return

    db_user.cash -= bail
    db_user.prison_until = None
    db_user.prison_reason = None
    await log_transaction(session, db_user.id, "bail_payment", -bail, "پرداخت وثیقه آزادی")
    await session.commit()

    await callback.message.edit_text(
        f"{header('🎉 آزاد شدی!')}\n\nبا پرداخت <code>{fmt_money(bail)}</code> تومان از زندان آزاد شدی!\n"
        f"حالا می‌تونی دوباره از همه‌ی بخش‌های ربات استفاده کنی."
    )
    await callback.answer("🔓 آزاد شدی!")


@router.callback_query(F.data == "prison_bail_cancel")
async def prison_bail_cancel(callback: CallbackQuery, db_user: User):
    if not is_in_prison(db_user):
        await callback.message.edit_text("✅ تو الان زندانی نیستی!")
        await callback.answer()
        return
    text, b = build_prison_block(db_user)
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer("لغو شد.")
