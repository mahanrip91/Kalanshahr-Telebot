"""
پنل مالک کل ربات — ۱۰۰٪ شیشه‌ای (Inline Keyboard) + FSM
فقط OWNER_ID بهش دسترسی داره. هیچ دستور متنی /شارژ و... لازم نیست.
"""
import asyncio
import os
import sys
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from database.models import User, GiftCode
from database.engine import wipe_db, async_session
from core.texts import header
from core.economy import add_cash, log_transaction
from config import settings
from utils.formatting import fmt_money, parse_amount

router = Router(name="admin")


class OwnerStates(StatesGroup):
    charge_cash_target = State()
    charge_cash_amount = State()
    charge_bank_target = State()
    charge_bank_amount = State()
    ban_target = State()
    unban_target = State()
    gift_code = State()
    gift_amount = State()
    gift_uses = State()
    reset_target = State()
    broadcast_text = State()
    restart_confirm = State()


def _is_owner(tg_id: int) -> bool:
    return tg_id == settings.OWNER_ID


async def _find_user(session, id_or_username: str):
    id_or_username = id_or_username.lstrip("@")
    if id_or_username.isdigit():
        result = await session.execute(select(User).where(User.telegram_id == int(id_or_username)))
    else:
        result = await session.execute(select(User).where(User.username == id_or_username))
    return result.scalar_one_or_none()


def owner_panel_kb() -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.button(text="💵 شارژ نقدی", callback_data="owner:charge_cash", style="success")
    b.button(text="🏦 شارژ بانکی", callback_data="owner:charge_bank", style="success")
    b.button(text="🚫 اخراج کاربر", callback_data="owner:ban", style="danger")
    b.button(text="✅ رفع اخراج", callback_data="owner:unban", style="primary")
    b.button(text="🎁 کد هدیه", callback_data="owner:gift", style="success")
    b.button(text="📊 آمار ربات", callback_data="owner:stats", style="primary")
    b.button(text="♻️ ریست کاربر", callback_data="owner:reset", style="danger")
    b.button(text="📢 پیام همگانی", callback_data="owner:broadcast", style="primary")
    b.button(text="⚠️ ری‌استارت کامل", callback_data="owner:restart", style="danger")
    b.button(text="❌ بستن پنل", callback_data="owner:close", style="danger")
    b.adjust(2, 2, 2, 2, 2)
    return b


def confirm_kb(yes_cb: str, no_cb: str = "owner:back") -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.button(text="✅ تایید و انجام", callback_data=yes_cb, style="success")
    b.button(text="❌ انصراف", callback_data=no_cb, style="danger")
    b.adjust(2)
    return b


@router.message(Command("پنل_مالک"))
@router.message(F.text.in_({"👑 پنل مالک", "پنل مالک"}))
async def owner_panel_entry(message: Message, state: FSMContext):
    await state.clear()
    if not _is_owner(message.from_user.id):
        return
    await message.answer(
        f"{header('👑 پنل مالک کلان‌شهر')}\n\n"
        "یه گزینه رو انتخاب کن. همه‌چی اینجاست 👇",
        reply_markup=owner_panel_kb().as_markup()
    )


@router.callback_query(F.data == "owner:back")
async def owner_panel_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not _is_owner(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    await callback.message.edit_text(
        f"{header('👑 پنل مالک کلان‌شهر')}\n\n"
        "یه گزینه رو انتخاب کن. همه‌چی اینجاست 👇",
        reply_markup=owner_panel_kb().as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "owner:close")
async def owner_panel_close(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not _is_owner(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    await callback.message.delete()
    await callback.answer("پنل بسته شد.", show_alert=True)


# ---------- شارژ نقدی ----------
@router.callback_query(F.data == "owner:charge_cash")
async def charge_cash_start(callback: CallbackQuery, state: FSMContext):
    if not _is_owner(callback.from_user.id):
        return
    await state.set_state(OwnerStates.charge_cash_target)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await callback.message.edit_text(
        "💵 <b>شارژ نقدی</b>\n\nآیدی عددی یا یوزرنیم کاربر رو بفرست:",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(OwnerStates.charge_cash_target, F.text)
async def charge_cash_target_msg(message: Message, state: FSMContext, session):
    target = await _find_user(session, message.text)
    if not target:
        b = InlineKeyboardBuilder()
        b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
        await message.answer("❌ کاربر پیدا نشد. دوباره بفرست:", reply_markup=b.as_markup())
        return
    await state.update_data(target_id=target.telegram_id, target_name=target.first_name)
    await state.set_state(OwnerStates.charge_cash_amount)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await message.answer(
        f"کاربر: <b>{target.first_name}</b> (<code>{target.telegram_id}</code>)\n"
        f"مبلغ رو بفرست (مثلاً ۵۰k یا ۱۰۰۰۰):",
        reply_markup=b.as_markup()
    )


@router.message(OwnerStates.charge_cash_amount, F.text)
async def charge_cash_amount_msg(message: Message, state: FSMContext, session):
    amount = parse_amount(message.text)
    if amount is None or amount <= 0:
        b = InlineKeyboardBuilder()
        b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
        await message.answer("❌ مبلغ نامعتبر. دوباره بفرست:", reply_markup=b.as_markup())
        return
    data = await state.get_data()
    await state.update_data(amount=amount)
    b = confirm_kb("owner:charge_cash_confirm")
    await message.answer(
        f"💵 <b>تایید شارژ نقدی</b>\n\n"
        f"کاربر: <b>{data['target_name']}</b>\n"
        f"مبلغ: <code>{fmt_money(amount)}</code> تومان\n\nانجام بدم؟",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data == "owner:charge_cash_confirm")
async def charge_cash_confirm_cb(callback: CallbackQuery, state: FSMContext, session):
    if not _is_owner(callback.from_user.id):
        return
    data = await state.get_data()
    target_id = data.get("target_id")
    amount = data.get("amount")
    target = await _find_user(session, str(target_id))
    if not target:
        await callback.answer("❌ کاربر پیدا نشد.", show_alert=True)
        return
    await add_cash(session, target, amount, "شارژ نقدی توسط مالک")
    await state.clear()
    await callback.message.edit_text(
        f"✅ <code>{fmt_money(amount)}</code> تومان نقد به <b>{target.first_name}</b> اضافه شد.",
        reply_markup=owner_panel_kb().as_markup()
    )
    try:
        await callback.bot.send_message(target_id, f"💵 مالک ربات <code>{fmt_money(amount)}</code> تومان نقد به حسابت اضافه کرد!")
    except Exception:
        pass
    await callback.answer()


# ---------- شارژ بانکی ----------
@router.callback_query(F.data == "owner:charge_bank")
async def charge_bank_start(callback: CallbackQuery, state: FSMContext):
    if not _is_owner(callback.from_user.id):
        return
    await state.set_state(OwnerStates.charge_bank_target)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await callback.message.edit_text(
        "🏦 <b>شارژ بانکی</b>\n\nآیدی عددی یا یوزرنیم کاربر رو بفرست:",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(OwnerStates.charge_bank_target, F.text)
async def charge_bank_target_msg(message: Message, state: FSMContext, session):
    target = await _find_user(session, message.text)
    if not target:
        b = InlineKeyboardBuilder()
        b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
        await message.answer("❌ کاربر پیدا نشد. دوباره بفرست:", reply_markup=b.as_markup())
        return
    await state.update_data(target_id=target.telegram_id, target_name=target.first_name)
    await state.set_state(OwnerStates.charge_bank_amount)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await message.answer(
        f"کاربر: <b>{target.first_name}</b>\nمبلغ رو بفرست:",
        reply_markup=b.as_markup()
    )


@router.message(OwnerStates.charge_bank_amount, F.text)
async def charge_bank_amount_msg(message: Message, state: FSMContext, session):
    amount = parse_amount(message.text)
    if amount is None or amount <= 0:
        b = InlineKeyboardBuilder()
        b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
        await message.answer("❌ مبلغ نامعتبر. دوباره بفرست:", reply_markup=b.as_markup())
        return
    data = await state.get_data()
    await state.update_data(amount=amount)
    b = confirm_kb("owner:charge_bank_confirm")
    await message.answer(
        f"🏦 <b>تایید شارژ بانکی</b>\n\n"
        f"کاربر: <b>{data['target_name']}</b>\n"
        f"مبلغ: <code>{fmt_money(amount)}</code> تومان\n\nانجام بدم؟",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data == "owner:charge_bank_confirm")
async def charge_bank_confirm_cb(callback: CallbackQuery, state: FSMContext, session):
    if not _is_owner(callback.from_user.id):
        return
    data = await state.get_data()
    target_id = data.get("target_id")
    amount = data.get("amount")
    target = await _find_user(session, str(target_id))
    if not target:
        await callback.answer("❌ کاربر پیدا نشد.", show_alert=True)
        return
    target.bank_balance += amount
    await log_transaction(session, target.id, "owner_bank_charge", amount, "شارژ بانکی توسط مالک")
    await session.commit()
    await state.clear()
    await callback.message.edit_text(
        f"✅ <code>{fmt_money(amount)}</code> تومان بانکی به <b>{target.first_name}</b> اضافه شد.",
        reply_markup=owner_panel_kb().as_markup()
    )
    try:
        await callback.bot.send_message(target_id, f"🏦 مالک ربات <code>{fmt_money(amount)}</code> تومان به بانکت اضافه کرد!")
    except Exception:
        pass
    await callback.answer()


# ---------- اخراج ----------
@router.callback_query(F.data == "owner:ban")
async def ban_start(callback: CallbackQuery, state: FSMContext):
    if not _is_owner(callback.from_user.id):
        return
    await state.set_state(OwnerStates.ban_target)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await callback.message.edit_text(
        "🚫 <b>اخراج کاربر</b>\n\nآیدی عددی یا یوزرنیم کاربر رو بفرست:",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(OwnerStates.ban_target, F.text)
async def ban_target_msg(message: Message, state: FSMContext, session):
    target = await _find_user(session, message.text)
    if not target:
        b = InlineKeyboardBuilder()
        b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
        await message.answer("❌ کاربر پیدا نشد. دوباره بفرست:", reply_markup=b.as_markup())
        return
    if target.telegram_id == settings.OWNER_ID:
        await message.answer("❌ نمی‌تونی خودتو اخراج کنی!")
        return
    await state.update_data(target_id=target.telegram_id, target_name=target.first_name)
    b = confirm_kb("owner:ban_confirm")
    await message.answer(
        f"🚫 <b>تایید اخراج</b>\n\n"
        f"کاربر: <b>{target.first_name}</b> (<code>{target.telegram_id}</code>)\n\n"
        f"مطمئنی می‌خوای اخراجش کنی؟",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data == "owner:ban_confirm")
async def ban_confirm_cb(callback: CallbackQuery, state: FSMContext, session):
    if not _is_owner(callback.from_user.id):
        return
    data = await state.get_data()
    target = await _find_user(session, str(data.get("target_id")))
    if not target:
        await callback.answer("❌ کاربر پیدا نشد.", show_alert=True)
        return
    target.is_banned = True
    await session.commit()
    await state.clear()
    await callback.message.edit_text(
        f"🚫 کاربر <b>{target.first_name}</b> (<code>{target.telegram_id}</code>) اخراج شد.\n"
        f"پیشرفتش حفظ می‌شه؛ فقط دیگه نمی‌تونه از ربات استفاده کنه.",
        reply_markup=owner_panel_kb().as_markup()
    )
    try:
        await callback.bot.send_message(target.telegram_id, "🚫 شما توسط مالک ربات اخراج شدید!")
    except Exception:
        pass
    await callback.answer()


# ---------- رفع اخراج ----------
@router.callback_query(F.data == "owner:unban")
async def unban_start(callback: CallbackQuery, state: FSMContext):
    if not _is_owner(callback.from_user.id):
        return
    await state.set_state(OwnerStates.unban_target)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await callback.message.edit_text(
        "✅ <b>رفع اخراج</b>\n\nآیدی عددی یا یوزرنیم کاربر رو بفرست:",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(OwnerStates.unban_target, F.text)
async def unban_target_msg(message: Message, state: FSMContext, session):
    target = await _find_user(session, message.text)
    if not target:
        b = InlineKeyboardBuilder()
        b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
        await message.answer("❌ کاربر پیدا نشد. دوباره بفرست:", reply_markup=b.as_markup())
        return
    await state.update_data(target_id=target.telegram_id, target_name=target.first_name)
    b = confirm_kb("owner:unban_confirm")
    await message.answer(
        f"✅ <b>تایید رفع اخراج</b>\n\n"
        f"کاربر: <b>{target.first_name}</b> (<code>{target.telegram_id}</code>)\n\nمطمئنی؟",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data == "owner:unban_confirm")
async def unban_confirm_cb(callback: CallbackQuery, state: FSMContext, session):
    if not _is_owner(callback.from_user.id):
        return
    data = await state.get_data()
    target = await _find_user(session, str(data.get("target_id")))
    if not target:
        await callback.answer("❌ کاربر پیدا نشد.", show_alert=True)
        return
    target.is_banned = False
    await session.commit()
    await state.clear()
    await callback.message.edit_text(
        f"✅ کاربر <b>{target.first_name}</b> رفع اخراج شد.",
        reply_markup=owner_panel_kb().as_markup()
    )
    try:
        await callback.bot.send_message(target.telegram_id, "✅ اخراج شما لغو شد! خوش برگشتی 🎉")
    except Exception:
        pass
    await callback.answer()


# ---------- کد هدیه ----------
@router.callback_query(F.data == "owner:gift")
async def gift_start(callback: CallbackQuery, state: FSMContext):
    if not _is_owner(callback.from_user.id):
        return
    await state.set_state(OwnerStates.gift_code)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await callback.message.edit_text(
        "🎁 <b>ساخت کد هدیه</b>\n\nمتن کد رو بفرست (مثلاً NEWYEAR1404):",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(OwnerStates.gift_code, F.text)
async def gift_code_msg(message: Message, state: FSMContext):
    code = message.text.strip().upper().replace(" ", "_")
    if len(code) < 3:
        await message.answer("❌ کد باید حداقل ۳ کاراکتر باشه. دوباره بفرست:")
        return
    await state.update_data(code=code)
    await state.set_state(OwnerStates.gift_amount)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await message.answer(
        f"کد: <code>{code}</code>\n\nمبلغ کد رو بفرست:",
        reply_markup=b.as_markup()
    )


@router.message(OwnerStates.gift_amount, F.text)
async def gift_amount_msg(message: Message, state: FSMContext):
    amount = parse_amount(message.text)
    if amount is None or amount <= 0:
        await message.answer("❌ مبلغ نامعتبر. دوباره بفرست:")
        return
    await state.update_data(amount=amount)
    await state.set_state(OwnerStates.gift_uses)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await message.answer(
        f"مبلغ: <code>{fmt_money(amount)}</code>\n\nتعداد دفعات استفاده رو بفرست (عدد):",
        reply_markup=b.as_markup()
    )


@router.message(OwnerStates.gift_uses, F.text)
async def gift_uses_msg(message: Message, state: FSMContext, session):
    if not message.text.isdigit() or int(message.text) <= 0:
        await message.answer("❌ عدد نامعتبر. دوباره بفرست:")
        return
    uses = int(message.text)
    data = await state.get_data()
    code_text = data["code"]
    amount = data["amount"]
    existing = await session.execute(select(GiftCode).where(GiftCode.code == code_text))
    if existing.scalar_one_or_none():
        await message.answer("❌ این کد قبلاً ساخته شده. از اول شروع کن.")
        await state.clear()
        return
    await state.update_data(uses=uses)
    b = confirm_kb("owner:gift_confirm")
    await message.answer(
        f"🎁 <b>تایید ساخت کد هدیه</b>\n\n"
        f"کد: <code>{code_text}</code>\n"
        f"مبلغ: <code>{fmt_money(amount)}</code>\n"
        f"ظرفیت: <b>{uses}</b> نفر\n\nمی‌سازم؟",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data == "owner:gift_confirm")
async def gift_confirm_cb(callback: CallbackQuery, state: FSMContext, session):
    if not _is_owner(callback.from_user.id):
        return
    data = await state.get_data()
    code = GiftCode(code=data["code"], amount=data["amount"], max_uses=data.get("uses", 1))
    session.add(code)
    await session.commit()
    await state.clear()
    await callback.message.edit_text(
        f"✅ کد هدیه ساخته شد!\n\n"
        f"کد: <code>{data['code']}</code>\n"
        f"مبلغ: {fmt_money(data['amount'])}\n"
        f"ظرفیت: {data.get('uses', 1)} نفر",
        reply_markup=owner_panel_kb().as_markup()
    )
    await callback.answer()


# ---------- آمار ----------
@router.callback_query(F.data == "owner:stats")
async def owner_stats(callback: CallbackQuery, session):
    if not _is_owner(callback.from_user.id):
        return
    total_users = (await session.execute(select(func.count(User.id)))).scalar()
    total_cash = (await session.execute(select(func.sum(User.cash)))).scalar() or 0
    total_bank = (await session.execute(select(func.sum(User.bank_balance)))).scalar() or 0
    banned = (await session.execute(select(func.count(User.id)).where(User.is_banned == True))).scalar()
    text = (
        f"{header('📊 آمار کلی ربات')}\n\n"
        f"👥 کل کاربران: <b>{total_users}</b>\n"
        f"🚫 اخراج‌شده: <b>{banned}</b>\n"
        f"💵 مجموع نقدینگی: <code>{fmt_money(total_cash)}</code>\n"
        f"🏦 مجموع بانکی: <code>{fmt_money(total_bank)}</code>\n"
        f"💎 ثروت کل: <code>{fmt_money(total_cash + total_bank)}</code>"
    )
    b = InlineKeyboardBuilder()
    b.button(text="🔙 بازگشت", callback_data="owner:back", style="primary")
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


# ---------- ریست کاربر ----------
@router.callback_query(F.data == "owner:reset")
async def reset_start(callback: CallbackQuery, state: FSMContext):
    if not _is_owner(callback.from_user.id):
        return
    await state.set_state(OwnerStates.reset_target)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await callback.message.edit_text(
        "♻️ <b>ریست کاربر</b>\n\n"
        "آیدی عددی یا یوزرنیم کاربر رو بفرست:\n"
        "⚠️ این کار تمام پیشرفت کاربر رو صفر می‌کنه!",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(OwnerStates.reset_target, F.text)
async def reset_target_msg(message: Message, state: FSMContext, session):
    target = await _find_user(session, message.text)
    if not target:
        b = InlineKeyboardBuilder()
        b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
        await message.answer("❌ کاربر پیدا نشد. دوباره بفرست:", reply_markup=b.as_markup())
        return
    await state.update_data(target_id=target.telegram_id, target_name=target.first_name)
    b = confirm_kb("owner:reset_confirm")
    await message.answer(
        f"♻️ <b>تایید ریست</b>\n\n"
        f"کاربر: <b>{target.first_name}</b> (<code>{target.telegram_id}</code>)\n"
        f"سطح فعلی: <b>{target.level}</b> | ثروت: <code>{fmt_money(target.total_wealth())}</code>\n\n"
        f"⚠️ مطمئنی؟ این کار برگشت‌ناپذیره!",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data == "owner:reset_confirm")
async def reset_confirm_cb(callback: CallbackQuery, state: FSMContext, session):
    if not _is_owner(callback.from_user.id):
        return
    data = await state.get_data()
    target = await _find_user(session, str(data.get("target_id")))
    if not target:
        await callback.answer("❌ کاربر پیدا نشد.", show_alert=True)
        return
    target.level = 1
    target.xp = 0
    target.cash = 5000
    target.bank_balance = 0
    target.loan_amount = 0
    target.loan_due = None
    target.job = None
    target.job_level = 1
    await session.commit()
    await state.clear()
    await callback.message.edit_text(
        f"♻️ کاربر <b>{target.first_name}</b> کاملاً ریست شد.",
        reply_markup=owner_panel_kb().as_markup()
    )
    try:
        await callback.bot.send_message(target.telegram_id, "♻️ حساب کاربریت توسط مالک ربات ریست شد.")
    except Exception:
        pass
    await callback.answer()


# ---------- پیام همگانی ----------
@router.callback_query(F.data == "owner:broadcast")
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    if not _is_owner(callback.from_user.id):
        return
    await state.set_state(OwnerStates.broadcast_text)
    b = InlineKeyboardBuilder()
    b.button(text="🔙 انصراف", callback_data="owner:back", style="danger")
    await callback.message.edit_text(
        "📢 <b>پیام همگانی</b>\n\nمتن پیام رو بفرست (می‌تونه HTML باشه):",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.message(OwnerStates.broadcast_text, F.text)
async def broadcast_text_msg(message: Message, state: FSMContext):
    text = message.text
    await state.update_data(broadcast_text=text)
    b = confirm_kb("owner:broadcast_confirm")
    await message.answer(
        f"📢 <b>پیش‌نمایش پیام همگانی</b>\n\n{text}\n\nبرای همه کاربران ارسال بشه؟",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data == "owner:broadcast_confirm")
async def broadcast_confirm_cb(callback: CallbackQuery, state: FSMContext, session):
    if not _is_owner(callback.from_user.id):
        return
    data = await state.get_data()
    text = data.get("broadcast_text")
    if not text:
        await callback.answer("❌ متنی نیست.", show_alert=True)
        return
    result = await session.execute(select(User.telegram_id))
    ids = [row[0] for row in result.all()]
    await callback.message.edit_text(f"⏳ در حال ارسال به {len(ids)} کاربر...")
    sent, failed = 0, 0
    for tg_id in ids:
        try:
            await callback.bot.send_message(tg_id, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)
    await state.clear()
    await callback.message.answer(
        f"✅ ارسال شد به {sent} نفر. ({failed} ناموفق)",
        reply_markup=owner_panel_kb().as_markup()
    )
    await callback.answer()


# ---------- ری‌استارت کامل ----------
@router.callback_query(F.data == "owner:restart")
async def restart_start(callback: CallbackQuery, state: FSMContext):
    if not _is_owner(callback.from_user.id):
        return
    await state.set_state(OwnerStates.restart_confirm)
    b = InlineKeyboardBuilder()
    b.button(text="✅ بله، همه‌چی پاک شه", callback_data="owner:restart_yes", style="danger")
    b.button(text="❌ نه، بیخیال", callback_data="owner:back", style="success")
    b.adjust(1)
    await callback.message.edit_text(
        "⚠️ <b>هشدار جدی!</b>\n\n"
        "این کار کل دیتابیس رو کاملاً پاک می‌کنه و ربات از صفر ریستارت می‌شه.\n"
        "این کار <b>غیرقابل بازگشت</b> است!\n\nمطمئنی؟",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "owner:restart_yes")
async def restart_yes(callback: CallbackQuery, state: FSMContext):
    if not _is_owner(callback.from_user.id):
        return
    await state.clear()
    await callback.message.edit_text("⏳ در حال پاکسازی کامل دیتابیس و ریستارت...")
    await callback.answer()
    await wipe_db()
    from services.market_engine import seed_market
    async with async_session() as session:
        await seed_market(session)
    await callback.message.answer("✅ همه‌چی پاک شد. ربات داره ریستارت می‌شه...")
    await asyncio.sleep(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)
