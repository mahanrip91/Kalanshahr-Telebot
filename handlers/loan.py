"""
سیستم وام: درخواست، بازپرداخت، جریمه دیرکرد - با تایید/برگشت قبل از هر عملیات
"""
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database.models import User
from core.keyboards import back_kb, bank_kb, confirm_kb
from core.texts import header, INVALID_AMOUNT_TEXT
from core.economy import log_transaction
from core.reply_guard import set_prompt, check_reply
from config import LOAN_INTEREST_RATE, LOAN_MAX_DAYS, LOAN_LATE_PENALTY_PER_DAY
from utils.formatting import fmt_money, parse_amount, fmt_datetime

router = Router(name="loan")


class LoanStates(StatesGroup):
    waiting_amount = State()
    confirm_amount = State()
    waiting_repay = State()
    confirm_repay = State()


def max_loan_for(user: User) -> int:
    return 5000 * user.level + 10000


@router.callback_query(F.data == "loan_request")
async def loan_request_start(callback: CallbackQuery, state: FSMContext, db_user: User):
    if db_user.loan_amount > 0:
        due_text = fmt_datetime(db_user.loan_due) if db_user.loan_due else "-"
        await callback.answer(
            f"❌ الان یه وام باز داری ({fmt_money(db_user.loan_amount)} تومان، سررسید {due_text}).",
            show_alert=True
        )
        return

    limit = max_loan_for(db_user)
    await state.set_state(LoanStates.waiting_amount)
    await callback.message.edit_text(
        f"{header('درخواست وام')}\n\n"
        f"سقف: <code>{fmt_money(limit)}</code> | بهره: {LOAN_INTEREST_RATE*100:.0f}٪ | مهلت: {LOAN_MAX_DAYS} روز\n\n"
        f"↩️ رو همین پیام ریپلای کن و بگو چقدر",
        reply_markup=back_kb("bank_back")
    )
    await set_prompt(state, callback.message.message_id)
    await callback.answer()


@router.message(LoanStates.waiting_amount)
async def loan_request_amount(message: Message, state: FSMContext, db_user: User):
    if not await check_reply(message, state):
        return
    amount = parse_amount(message.text)
    limit = max_loan_for(db_user)
    if amount is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    if amount > limit:
        await message.answer(f"❌ مبلغ باید بین ۱ تا <code>{fmt_money(limit)}</code> تومان باشه.")
        return

    total_owed = round(amount * (1 + LOAN_INTEREST_RATE))
    await state.update_data(amount=amount, total_owed=total_owed)
    await state.set_state(LoanStates.confirm_amount)
    await message.answer(
        f"{header('✅ تایید درخواست وام')}\n\n"
        f"💰 مبلغ دریافتی: <code>{fmt_money(amount)}</code>\n"
        f"💳 مبلغ قابل بازپرداخت: <code>{fmt_money(total_owed)}</code>\n"
        f"📅 مهلت: {LOAN_MAX_DAYS} روز | جریمه دیرکرد روزی {LOAN_LATE_PENALTY_PER_DAY*100:.0f}٪\n\n"
        f"مطمئنی می‌خوای این وام رو بگیری؟",
        reply_markup=confirm_kb("loan_request_confirm", "loan_request_cancel")
    )


@router.callback_query(F.data == "loan_request_confirm", LoanStates.confirm_amount)
async def loan_request_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    if db_user.loan_amount > 0:
        await callback.answer("❌ همین الان یه وام باز داری!", show_alert=True)
        await state.clear()
        return
    data = await state.get_data()
    amount = data.get("amount")
    total_owed = data.get("total_owed")
    if amount is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return

    db_user.loan_amount = total_owed
    db_user.loan_due = datetime.utcnow() + timedelta(days=LOAN_MAX_DAYS)
    db_user.cash += amount
    await log_transaction(session, db_user.id, "loan_take", amount, "دریافت وام")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>{fmt_money(amount)}</b> تومان وام گرفتی!\n\n"
        f"💰 مبلغ قابل بازپرداخت: <code>{fmt_money(total_owed)}</code> تومان\n"
        f"📅 سررسید: <b>{fmt_datetime(db_user.loan_due)}</b>\n\n"
        f"⚠️ اگه دیر کنی، روزی {LOAN_LATE_PENALTY_PER_DAY*100:.0f}٪ جریمه اضافه میشه!",
        reply_markup=bank_kb()
    )
    await callback.answer("✅ وام گرفته شد!")


@router.callback_query(F.data == "loan_request_cancel")
async def loan_request_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(f"{header('🏦 بانک')}\n\n❌ درخواست وام لغو شد.", reply_markup=bank_kb())
    await callback.answer()


@router.callback_query(F.data == "loan_repay")
async def loan_repay_start(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    if db_user.loan_amount <= 0:
        await callback.answer("✅ هیچ وام بازی نداری!", show_alert=True)
        return

    if db_user.loan_due and datetime.utcnow() > db_user.loan_due:
        days_late = (datetime.utcnow() - db_user.loan_due).days + 1
        penalty = db_user.loan_amount * LOAN_LATE_PENALTY_PER_DAY * days_late
        db_user.loan_amount += penalty
        await session.commit()

    await state.set_state(LoanStates.waiting_repay)
    await callback.message.edit_text(
        f"{header('بازپرداخت وام')}\n\n"
        f"بدهی فعلی: <code>{fmt_money(db_user.loan_amount)}</code>\n\n"
        f"↩️ رو همین پیام ریپلای کن (جزئی یا کامل)",
        reply_markup=back_kb("bank_back")
    )
    await set_prompt(state, callback.message.message_id)
    await callback.answer()


@router.message(LoanStates.waiting_repay)
async def loan_repay_amount(message: Message, state: FSMContext, db_user: User):
    if not await check_reply(message, state):
        return
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    if amount > db_user.cash:
        await message.answer(f"❌ پول نقدت کافی نیست! (<code>{fmt_money(db_user.cash)}</code>)")
        return

    pay = min(amount, db_user.loan_amount)
    await state.update_data(pay=pay)
    await state.set_state(LoanStates.confirm_repay)
    remain_after = db_user.loan_amount - pay
    await message.answer(
        f"{header('✅ تایید بازپرداخت')}\n\n"
        f"💰 مبلغ پرداختی: <code>{fmt_money(pay)}</code>\n"
        f"باقی‌مانده بعد از این پرداخت: <code>{fmt_money(max(remain_after, 0))}</code>\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb("loan_repay_confirm", "loan_repay_cancel")
    )


@router.callback_query(F.data == "loan_repay_confirm", LoanStates.confirm_repay)
async def loan_repay_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    pay = data.get("pay")
    if pay is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return
    if pay > db_user.cash:
        await callback.answer("❌ پول نقدت کافی نیست!", show_alert=True)
        await state.clear()
        return

    pay = min(pay, db_user.loan_amount)
    db_user.cash -= pay
    db_user.loan_amount -= pay
    if db_user.loan_amount <= 0:
        db_user.loan_amount = 0
        db_user.loan_due = None

    await log_transaction(session, db_user.id, "loan_repay", -pay, "بازپرداخت وام")
    await session.commit()
    await state.clear()

    status = "✅ وامت کاملاً تسویه شد! 🎉" if db_user.loan_amount == 0 else f"باقی‌مانده بدهی: <code>{fmt_money(db_user.loan_amount)}</code>"
    await callback.message.edit_text(
        f"✅ <b>{fmt_money(pay)}</b> تومان پرداخت شد.\n\n{status}",
        reply_markup=bank_kb()
    )
    await callback.answer("✅ پرداخت شد!")


@router.callback_query(F.data == "loan_repay_cancel")
async def loan_repay_cancel(callback: CallbackQuery, state: FSMContext, db_user: User):
    await state.clear()
    from handlers.bank import build_bank_text
    await callback.message.edit_text(build_bank_text(db_user), reply_markup=bank_kb())
    await callback.answer("❌ بازپرداخت لغو شد.")
