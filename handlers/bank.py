"""
سیستم بانک: واریز، برداشت، سود روزانه، وام، تاریخچه، شماره حساب و انتقال به حساب
همه‌ی عملیات پولی قبل از اجرا یه مرحله «تایید یا برگشت» دارن.
"""
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, desc
import random

from database.models import User, Transaction
from core.keyboards import bank_kb, back_kb, confirm_kb
from core.texts import header, NOT_ENOUGH_MONEY, INVALID_AMOUNT_TEXT
from core.economy import log_transaction, ensure_account_number
from core.reply_guard import set_prompt, check_reply
from core.auto_revert import schedule_revert
from config import BANK_MIN_INTEREST, BANK_MAX_INTEREST, BANK_DAILY_DEPOSIT_LIMIT, BANK_TRANSFER_FEE_RATE
from utils.formatting import fmt_money, parse_amount

router = Router(name="bank")


class BankStates(StatesGroup):
    waiting_deposit = State()
    confirm_deposit = State()
    waiting_withdraw = State()
    confirm_withdraw = State()
    waiting_transfer_amount = State()
    waiting_transfer_account = State()


def _reset_daily_limit_if_needed(user: User):
    today = datetime.utcnow().date()
    if not user.bank_deposit_reset or user.bank_deposit_reset.date() != today:
        user.bank_deposit_today = 0
        user.bank_deposit_reset = datetime.utcnow()


def build_bank_text(user: User) -> str:
    return (
        f"{header('🏦 بانک کلان‌شهر')}\n\n"
        f"🆔 حساب: <code>{user.account_number or '—'}</code>\n"
        f"💵 نقد: <code>{fmt_money(user.cash)}</code>\n"
        f"🏦 بانک: <code>{fmt_money(user.bank_balance)}</code>\n"
        f"🔴 بدهی: <code>{fmt_money(user.loan_amount)}</code>\n\n"
        f"سود روزانه: {int(BANK_MIN_INTEREST*100*10)/10}٪ تا {int(BANK_MAX_INTEREST*100*10)/10}٪"
    )


@router.message(F.text.in_({"🏦 بانک", "بانک"}))
async def bank_menu(message: Message, session, db_user: User):
    await ensure_account_number(session, db_user)
    await message.answer(build_bank_text(db_user), reply_markup=bank_kb())


# ---------------- واریز ----------------

@router.callback_query(F.data == "bank_deposit")
async def bank_deposit_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BankStates.waiting_deposit)
    await callback.message.edit_text(
        f"{header('واریز')}\n\n↩️ رو همین پیام ریپلای کن و بگو چقدر (مثلاً <code>5k</code>)",
        reply_markup=back_kb("bank_back")
    )
    await set_prompt(state, callback.message.message_id)
    await callback.answer()


@router.message(BankStates.waiting_deposit)
async def bank_deposit_amount(message: Message, state: FSMContext, db_user: User):
    if not await check_reply(message, state):
        return
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    _reset_daily_limit_if_needed(db_user)

    if db_user.cash < amount:
        await message.answer(NOT_ENOUGH_MONEY.format(cash=fmt_money(db_user.cash)))
        return
    if db_user.bank_deposit_today + amount > BANK_DAILY_DEPOSIT_LIMIT:
        remain = BANK_DAILY_DEPOSIT_LIMIT - db_user.bank_deposit_today
        await message.answer(f"❌ سقف واریز روزانه پر شده. باقی‌مانده امروز: <code>{fmt_money(remain)}</code>")
        return

    await state.update_data(amount=amount)
    await state.set_state(BankStates.confirm_deposit)
    await message.answer(
        f"{header('✅ تایید واریز')}\n\nمبلغ: <code>{fmt_money(amount)}</code> تومان\n\nمطمئنی؟",
        reply_markup=confirm_kb("bank_deposit_confirm", "bank_deposit_cancel")
    )


@router.callback_query(F.data == "bank_deposit_confirm", BankStates.confirm_deposit)
async def bank_deposit_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    amount = data.get("amount")
    if amount is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return

    _reset_daily_limit_if_needed(db_user)
    if db_user.cash < amount:
        await callback.answer(NOT_ENOUGH_MONEY.format(cash=fmt_money(db_user.cash)), show_alert=True)
        await state.clear()
        return
    if db_user.bank_deposit_today + amount > BANK_DAILY_DEPOSIT_LIMIT:
        await callback.answer("❌ سقف واریز روزانه پر شده.", show_alert=True)
        await state.clear()
        return

    db_user.cash -= amount
    db_user.bank_balance += amount
    db_user.bank_deposit_today += amount
    await log_transaction(session, db_user.id, "bank_deposit", amount, "واریز به بانک")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>{fmt_money(amount)}</b> تومان با موفقیت واریز شد!\n\n{build_bank_text(db_user)}",
        reply_markup=bank_kb()
    )
    await callback.answer("✅ واریز شد!")


@router.callback_query(F.data == "bank_deposit_cancel")
async def bank_deposit_cancel(callback: CallbackQuery, state: FSMContext, db_user: User):
    await state.clear()
    await callback.message.edit_text(build_bank_text(db_user), reply_markup=bank_kb())
    await callback.answer("❌ واریز لغو شد.")


# ---------------- برداشت ----------------

@router.callback_query(F.data == "bank_withdraw")
async def bank_withdraw_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BankStates.waiting_withdraw)
    await callback.message.edit_text(
        f"{header('برداشت')}\n\n↩️ رو همین پیام ریپلای کن و بگو چقدر",
        reply_markup=back_kb("bank_back")
    )
    await set_prompt(state, callback.message.message_id)
    await callback.answer()


@router.message(BankStates.waiting_withdraw)
async def bank_withdraw_amount(message: Message, state: FSMContext, db_user: User):
    if not await check_reply(message, state):
        return
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    if db_user.bank_balance < amount:
        await message.answer(f"❌ موجودی بانکت کافی نیست! (<code>{fmt_money(db_user.bank_balance)}</code>)")
        return

    await state.update_data(amount=amount)
    await state.set_state(BankStates.confirm_withdraw)
    await message.answer(
        f"{header('✅ تایید برداشت')}\n\nمبلغ: <code>{fmt_money(amount)}</code> تومان\n\nمطمئنی؟",
        reply_markup=confirm_kb("bank_withdraw_confirm", "bank_withdraw_cancel")
    )


@router.callback_query(F.data == "bank_withdraw_confirm", BankStates.confirm_withdraw)
async def bank_withdraw_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    amount = data.get("amount")
    if amount is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return
    if db_user.bank_balance < amount:
        await callback.answer("❌ موجودی بانکت کافی نیست!", show_alert=True)
        await state.clear()
        return

    db_user.bank_balance -= amount
    db_user.cash += amount
    await log_transaction(session, db_user.id, "bank_withdraw", amount, "برداشت از بانک")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>{fmt_money(amount)}</b> تومان با موفقیت برداشت شد!\n\n{build_bank_text(db_user)}",
        reply_markup=bank_kb()
    )
    await callback.answer("✅ برداشت شد!")


@router.callback_query(F.data == "bank_withdraw_cancel")
async def bank_withdraw_cancel(callback: CallbackQuery, state: FSMContext, db_user: User):
    await state.clear()
    await callback.message.edit_text(build_bank_text(db_user), reply_markup=bank_kb())
    await callback.answer("❌ برداشت لغو شد.")


# ---------------- سود روزانه ----------------

@router.callback_query(F.data == "bank_interest")
async def bank_interest(callback: CallbackQuery, session, db_user: User):
    now = datetime.utcnow()
    result = await session.execute(
        select(Transaction).where(
            Transaction.user_id == db_user.id, Transaction.type == "bank_interest"
        ).order_by(desc(Transaction.created_at)).limit(1)
    )
    last_tx = result.scalar_one_or_none()
    if last_tx and last_tx.created_at.date() == now.date():
        await callback.answer("❌ سود امروز رو قبلاً دریافت کردی!", show_alert=True)
        return

    if db_user.bank_balance <= 0:
        await callback.answer("❌ موجودی بانکت صفره!", show_alert=True)
        return

    rate = random.uniform(BANK_MIN_INTEREST, BANK_MAX_INTEREST)
    profit = round(db_user.bank_balance * rate)
    db_user.bank_balance += profit
    await log_transaction(session, db_user.id, "bank_interest", profit, f"سود بانکی روزانه ({rate*100:.2f}٪)")
    await session.commit()

    await callback.message.edit_text(
        f"{header('سود بانکی')}\n\n"
        f"📈 نرخ امروز: <b>{rate*100:.2f}٪</b>\n"
        f"💰 سود دریافتی: <code>{fmt_money(profit)}</code> تومان\n"
        f"🏦 موجودی جدید: <code>{fmt_money(db_user.bank_balance)}</code> تومان",
        reply_markup=back_kb("bank_back")
    )
    await callback.answer("💰 سود واریز شد!")
    schedule_revert(callback.message, build_bank_text(db_user), bank_kb())


# ---------------- انتقال به حساب (قبلاً هم تایید داشت) ----------------

@router.callback_query(F.data == "bank_transfer_start")
async def bank_transfer_start(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    await ensure_account_number(session, db_user)
    await state.set_state(BankStates.waiting_transfer_amount)
    await callback.message.edit_text(
        f"{header('انتقال به حساب')}\n\n"
        f"🏦 موجودی: <code>{fmt_money(db_user.bank_balance)}</code> | کارمزد: {BANK_TRANSFER_FEE_RATE*100:.0f}٪\n\n"
        f"↩️ رو همین پیام ریپلای کن و بگو چقدر",
        reply_markup=back_kb("bank_back")
    )
    await set_prompt(state, callback.message.message_id)
    await callback.answer()


@router.message(BankStates.waiting_transfer_amount)
async def bank_transfer_amount(message: Message, state: FSMContext, db_user: User):
    if not await check_reply(message, state):
        return
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    if amount > db_user.bank_balance:
        await message.answer(f"❌ موجودی بانکت کافی نیست! (<code>{fmt_money(db_user.bank_balance)}</code>)")
        return

    prompt = await message.answer(
        f"{header('شماره حساب مقصد')}\n\n"
        f"↩️ رو همین پیام ریپلای کن، مثلاً: <code>KLS-1234-5678</code>",
        reply_markup=back_kb("bank_back")
    )
    await state.update_data(transfer_amount=amount)
    await set_prompt(state, prompt.message_id)
    await state.set_state(BankStates.waiting_transfer_account)


@router.message(BankStates.waiting_transfer_account)
async def bank_transfer_account(message: Message, state: FSMContext, session, db_user: User):
    if not await check_reply(message, state):
        return
    acc = message.text.strip().upper()
    result = await session.execute(select(User).where(User.account_number == acc))
    target = result.scalar_one_or_none()

    if not target:
        await message.answer("❌ حسابی با این شماره پیدا نشد! دوباره بفرست یا /لغو بزن.")
        return
    if target.id == db_user.id:
        await message.answer("❌ نمیتونی به حساب خودت پول بفرستی!")
        return

    data = await state.get_data()
    amount = data["transfer_amount"]
    fee = round(amount * BANK_TRANSFER_FEE_RATE)
    net = amount - fee

    await state.update_data(target_id=target.id, target_name=target.first_name, net=net, fee=fee)

    text = (
        f"{header('تایید انتقال')}\n\n"
        f"👤 مقصد: <b>{target.first_name}</b> (<code>{target.account_number}</code>)\n"
        f"💰 مبلغ: <code>{fmt_money(amount)}</code> تومان\n"
        f"💸 کارمزد ({BANK_TRANSFER_FEE_RATE*100:.0f}٪): <code>{fmt_money(fee)}</code> تومان\n"
        f"📥 مبلغ دریافتی مقصد: <code>{fmt_money(net)}</code> تومان\n\n"
        f"مطمئنی میخوای این انتقال رو انجام بدی؟"
    )
    await message.answer(text, reply_markup=confirm_kb("bank_transfer_confirm", "bank_transfer_cancel"))


@router.callback_query(F.data == "bank_transfer_confirm")
async def bank_transfer_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    amount = data.get("transfer_amount")
    target_id = data.get("target_id")
    net = data.get("net")
    fee = data.get("fee")

    if not amount or not target_id:
        await callback.answer("❌ اطلاعات انتقال منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return
    if amount > db_user.bank_balance:
        await callback.answer("❌ موجودی بانکت کافی نیست!", show_alert=True)
        await state.clear()
        return

    target = await session.get(User, target_id)
    if not target:
        await callback.answer("❌ حساب مقصد دیگه معتبر نیست.", show_alert=True)
        await state.clear()
        return

    db_user.bank_balance -= amount
    target.bank_balance += net
    await log_transaction(session, db_user.id, "bank_transfer_out", -amount, f"انتقال به حساب {target.account_number}")
    await log_transaction(session, target.id, "bank_transfer_in", net, f"دریافت از حساب {db_user.account_number}")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <code>{fmt_money(amount)}</code> تومان از حساب بانکیت منتقل شد!\n"
        f"💸 کارمزد: <code>{fmt_money(fee)}</code> تومان\n"
        f"📥 مبلغ دریافتی طرف مقابل: <code>{fmt_money(net)}</code> تومان\n\n"
        f"{build_bank_text(db_user)}",
        reply_markup=bank_kb()
    )
    await callback.answer("✅ انتقال انجام شد!")
    try:
        await callback.bot.send_message(
            target.telegram_id,
            f"💳 <b>{db_user.first_name}</b> مبلغ <code>{fmt_money(net)}</code> تومان به حساب بانکیت واریز کرد!",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data == "bank_transfer_cancel")
async def bank_transfer_cancel(callback: CallbackQuery, state: FSMContext, db_user: User):
    await state.clear()
    await callback.message.edit_text(build_bank_text(db_user), reply_markup=bank_kb())
    await callback.answer("❌ انتقال لغو شد.")


@router.callback_query(F.data == "bank_history")
async def bank_history(callback: CallbackQuery, session, db_user: User):
    result = await session.execute(
        select(Transaction).where(
            Transaction.user_id == db_user.id,
            Transaction.type.in_(["bank_deposit", "bank_withdraw", "bank_interest", "bank_transfer_out", "bank_transfer_in"])
        ).order_by(desc(Transaction.created_at)).limit(10)
    )
    txs = result.scalars().all()
    lines = [header("⚫️ تاریخچه بانکی")]
    if not txs:
        lines.append("\nتراکنشی ثبت نشده.")
    else:
        for tx in txs:
            sign = "🟢" if tx.amount >= 0 else "🔴"
            lines.append(f"{sign} <code>{fmt_money(abs(tx.amount))}</code> — {tx.description}")
    await callback.message.edit_text("\n".join(lines), reply_markup=back_kb("bank_back"))
    await callback.answer()


@router.callback_query(F.data == "bank_back")
async def bank_back(callback: CallbackQuery, state: FSMContext, db_user: User):
    await state.clear()
    await callback.message.edit_text(build_bank_text(db_user), reply_markup=bank_kb())
    await callback.answer()
