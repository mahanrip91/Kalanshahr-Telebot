"""
جوایز: پاداش روزانه + استریک، کد هدیه، سیستم دعوت دوستان
"""
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from database.models import User, GiftCode
from core.texts import header
from core.economy import add_cash, log_transaction
from core.auto_revert import schedule_revert
from core.reply_guard import set_prompt, check_reply
from config import DAILY_BASE_REWARD, DAILY_STREAK_BONUS, DAILY_STREAK_CAP
from utils.formatting import fmt_money

router = Router(name="rewards")


class GiftStates(StatesGroup):
    waiting_code = State()


def rewards_kb() -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.button(text="🎁 جایزه روزانه", callback_data="daily_reward", style="success")
    b.button(text="🎫 کد هدیه", callback_data="redeem_code", style="primary")
    b.button(text="👥 دعوت دوستان", callback_data="referral_info", style="primary")
    b.adjust(1)
    return b


def _rewards_menu_text(db_user: User) -> str:
    return (
        f"{header('🎁 مرکز جوایز')}\n\n"
        f"🔥 استریک روزانه فعلی: <b>{db_user.daily_streak}</b> روز\n\n"
        f"یکی از گزینه‌ها رو انتخاب کن:"
    )


@router.message(F.text.in_({"🎁 جوایز", "جوایز"}))
async def rewards_menu(message: Message, db_user: User):
    await message.answer(_rewards_menu_text(db_user), reply_markup=rewards_kb().as_markup())


@router.callback_query(F.data == "daily_reward")
async def daily_reward(callback: CallbackQuery, session, db_user: User):
    now = datetime.utcnow()
    if db_user.last_daily:
        elapsed = now - db_user.last_daily
        if elapsed < timedelta(hours=24):
            remain = timedelta(hours=24) - elapsed
            hours = int(remain.total_seconds() // 3600)
            minutes = int((remain.total_seconds() % 3600) // 60)
            await callback.answer(f"⏳ {hours} ساعت و {minutes} دقیقه تا جایزه بعدی مونده!", show_alert=True)
            return
        if elapsed > timedelta(hours=48):
            db_user.daily_streak = 0

    db_user.daily_streak = min(db_user.daily_streak + 1, DAILY_STREAK_CAP)
    bonus = DAILY_STREAK_BONUS * (db_user.daily_streak - 1)
    reward = DAILY_BASE_REWARD + bonus

    db_user.last_daily = now
    await add_cash(session, db_user, reward, f"جایزه روزانه (استریک {db_user.daily_streak})")

    await callback.message.edit_text(
        f"{header('🎁 جایزه روزانه دریافت شد!')}\n\n"
        f"🔥 استریک: <b>{db_user.daily_streak}</b> روز\n"
        f"💰 پاداش پایه: <code>{fmt_money(DAILY_BASE_REWARD)}</code>\n"
        f"➕ بونوس استریک: <code>{fmt_money(bonus)}</code>\n"
        f"💵 مجموع دریافتی: <code>{fmt_money(reward)}</code> تومان\n\n"
        f"موجودی جدید: <code>{fmt_money(db_user.cash)}</code> تومان"
    )
    await callback.answer("🎉 جایزه گرفتی!")
    schedule_revert(callback.message, _rewards_menu_text(db_user), rewards_kb().as_markup())


@router.callback_query(F.data == "redeem_code")
async def redeem_code_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GiftStates.waiting_code)
    await callback.message.edit_text(f"{header('🎫 کد هدیه')}\n\n↩️ رو همین پیام ریپلای کن و کدت رو بفرست")
    await set_prompt(state, callback.message.message_id)
    await callback.answer()


@router.message(GiftStates.waiting_code)
async def redeem_code_check(message: Message, state: FSMContext, session, db_user: User):
    if not await check_reply(message, state):
        return
    code_text = message.text.strip().upper()
    result = await session.execute(select(GiftCode).where(GiftCode.code == code_text))
    code = result.scalar_one_or_none()

    if not code:
        await message.answer("❌ کد نامعتبره!")
        return
    if code.expires_at and datetime.utcnow() > code.expires_at:
        await message.answer("❌ این کد منقضی شده!")
        return
    if code.used_count >= code.max_uses:
        await message.answer("❌ ظرفیت این کد پر شده!")
        return

    used_ids = code.used_by_ids.split(",") if code.used_by_ids else []
    if str(db_user.telegram_id) in used_ids:
        await message.answer("❌ تو قبلاً این کد رو استفاده کردی!")
        return

    code.used_count += 1
    used_ids.append(str(db_user.telegram_id))
    code.used_by_ids = ",".join(used_ids)
    await add_cash(session, db_user, code.amount, f"کد هدیه {code.code}")
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ کد با موفقیت فعال شد!\n💰 دریافتی: <code>{fmt_money(code.amount)}</code> تومان"
    )


@router.callback_query(F.data == "referral_info")
async def referral_info(callback: CallbackQuery, db_user: User):
    bot_info = await callback.bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={db_user.telegram_id}"
    await callback.message.edit_text(
        f"{header('👥 دعوت دوستان')}\n\n"
        f"به ازای هر دوست که با لینک تو عضو بشه:\n"
        f"🎁 تو ۳,۰۰۰ تومان میگیری\n"
        f"🎁 دوستت هم ۲,۰۰۰ تومان هدیه میگیره\n\n"
        f"لینک دعوت تو:\n<code>{link}</code>"
    )
    await callback.answer()
