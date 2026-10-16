"""
بازار ارز دیجیتال کلان‌شهر (نوسان بیشتر و ریسک بالاتر از بورس) - خرید/فروش با تایید
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from database.models import User, Crypto, CryptoHolding
from core.keyboards import back_kb, confirm_kb
from core.texts import header, NOT_ENOUGH_MONEY, INVALID_AMOUNT_TEXT
from core.economy import log_transaction
from core.reply_guard import set_prompt, check_reply
from utils.formatting import fmt_money, fmt_percent, parse_amount

router = Router(name="crypto")


class CryptoStates(StatesGroup):
    waiting_buy = State()
    confirm_buy = State()
    waiting_sell = State()
    confirm_sell = State()


def _change(c: Crypto) -> float:
    if not c.previous_price:
        return 0.0
    return (c.price - c.previous_price) / c.previous_price


@router.callback_query(F.data == "market_crypto")
async def crypto_list(callback: CallbackQuery, session):
    result = await session.execute(select(Crypto))
    cryptos = result.scalars().all()

    lines = [header("₿ بازار ارز دیجیتال"), "⚠️ نوسان بالا = ریسک و سود بیشتر", ""]
    b = InlineKeyboardBuilder()
    for c in cryptos:
        pct = _change(c)
        arrow = "🟢▲" if pct >= 0 else "🔴▼"
        lines.append(f"<b>{c.name}</b> ({c.symbol}) — <code>{fmt_money(c.price)}</code> {arrow} {fmt_percent(pct)}")
        b.button(text=f"{c.symbol}", callback_data=f"crypto_view:{c.id}")
    b.adjust(4)
    b.row(InlineKeyboardButton(text="🔙 بازگشت به بازار مالی", callback_data="market_back"))

    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("crypto_view:"))
async def crypto_view(callback: CallbackQuery, session, db_user: User):
    crypto_id = int(callback.data.split(":")[1])
    c = await session.get(Crypto, crypto_id)
    if not c:
        await callback.answer("پیدا نشد!", show_alert=True)
        return

    holding = (await session.execute(
        select(CryptoHolding).where(CryptoHolding.user_id == db_user.id, CryptoHolding.crypto_id == c.id)
    )).scalar_one_or_none()

    pct = _change(c)
    arrow = "🟢▲" if pct >= 0 else "🔴▼"
    text = (
        f"{header(f'₿ {c.name} ({c.symbol})')}\n\n"
        f"قیمت فعلی: <code>{fmt_money(c.price)}</code> تومان\n"
        f"تغییر اخیر: {arrow} {fmt_percent(pct)}\n\n"
    )
    if holding and holding.amount > 0:
        value = holding.amount * c.price
        profit = value - (holding.amount * holding.avg_buy_price)
        text += (
            f"🎒 دارایی تو: <b>{holding.amount:.5f}</b> {c.symbol}\n"
            f"میانگین خرید: <code>{fmt_money(holding.avg_buy_price)}</code>\n"
            f"ارزش فعلی: <code>{fmt_money(value)}</code>\n"
            f"سود/زیان: <code>{fmt_money(profit)}</code>\n"
        )
    else:
        text += "هنوز از این کوین نداری."

    b = InlineKeyboardBuilder()
    b.button(text="خرید", callback_data=f"crypto_buy:{c.id}", style="success")
    b.button(text="فروش", callback_data=f"crypto_sell:{c.id}", style="danger")
    b.button(text="🔙 بازگشت", callback_data="market_crypto")
    b.adjust(2, 1)
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("crypto_buy:"))
async def crypto_buy_start(callback: CallbackQuery, state: FSMContext):
    crypto_id = int(callback.data.split(":")[1])
    await state.set_state(CryptoStates.waiting_buy)
    await callback.message.edit_text(
        f"{header('خرید کوین')}\n\n↩️ رو همین پیام ریپلای کن و بگو چند تومان",
        reply_markup=back_kb("market_crypto")
    )
    await set_prompt(state, callback.message.message_id, crypto_id=crypto_id)
    await callback.answer()


@router.message(CryptoStates.waiting_buy)
async def crypto_buy_amount_ask(message: Message, state: FSMContext, session, db_user: User):
    if not await check_reply(message, state):
        return
    toman = parse_amount(message.text)
    if toman is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    data = await state.get_data()
    c = await session.get(Crypto, data["crypto_id"])

    if toman > db_user.cash:
        await message.answer(NOT_ENOUGH_MONEY.format(cash=fmt_money(db_user.cash)))
        return

    units = toman / c.price
    await state.update_data(toman=toman, units=units)
    await state.set_state(CryptoStates.confirm_buy)
    await message.answer(
        f"{header('✅ تایید خرید')}\n\n"
        f"₿ <b>{c.name}</b>: <b>{units:.5f}</b> {c.symbol}\n"
        f"💰 مبلغ: <code>{fmt_money(toman)}</code> تومان\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb("crypto_buy_confirm", "market_crypto")
    )


@router.callback_query(F.data == "crypto_buy_confirm", CryptoStates.confirm_buy)
async def crypto_buy_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    toman = data.get("toman")
    crypto_id = data.get("crypto_id")
    if toman is None or crypto_id is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return
    if toman > db_user.cash:
        await callback.answer("❌ پولت کافی نیست!", show_alert=True)
        await state.clear()
        return

    c = await session.get(Crypto, crypto_id)
    units = toman / c.price
    holding = (await session.execute(
        select(CryptoHolding).where(CryptoHolding.user_id == db_user.id, CryptoHolding.crypto_id == c.id)
    )).scalar_one_or_none()
    if not holding:
        holding = CryptoHolding(user_id=db_user.id, crypto_id=c.id, amount=0, avg_buy_price=0)
        session.add(holding)
        await session.flush()

    total_cost_before = holding.amount * holding.avg_buy_price
    new_amount = holding.amount + units
    holding.avg_buy_price = (total_cost_before + toman) / new_amount
    holding.amount = new_amount

    db_user.cash -= toman
    await log_transaction(session, db_user.id, "crypto_buy", -toman, f"خرید {c.symbol}")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>{units:.5f} {c.symbol}</b> خریداری شد!\n"
        f"💵 موجودی نقد: <code>{fmt_money(db_user.cash)}</code> تومان",
        reply_markup=back_kb("market_crypto")
    )
    await callback.answer("✅ خریداری شد!")


@router.callback_query(F.data.startswith("crypto_sell:"))
async def crypto_sell_start(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    crypto_id = int(callback.data.split(":")[1])
    holding = (await session.execute(
        select(CryptoHolding).where(CryptoHolding.user_id == db_user.id, CryptoHolding.crypto_id == crypto_id)
    )).scalar_one_or_none()
    if not holding or holding.amount <= 0:
        await callback.answer("❌ از این کوین نداری!", show_alert=True)
        return

    await state.set_state(CryptoStates.waiting_sell)
    await callback.message.edit_text(
        f"{header('فروش کوین')}\n\nموجودی: <b>{holding.amount:.5f}</b>\n\n↩️ رو همین پیام ریپلای کن و بگو چه مقدار",
        reply_markup=back_kb("market_crypto")
    )
    await set_prompt(state, callback.message.message_id, crypto_id=crypto_id)
    await callback.answer()


@router.message(CryptoStates.waiting_sell)
async def crypto_sell_amount_ask(message: Message, state: FSMContext, session, db_user: User):
    if not await check_reply(message, state):
        return
    try:
        amount = float(message.text.strip().replace(",", ""))
    except ValueError:
        await message.answer("❌ فقط عدد بفرست.")
        return

    data = await state.get_data()
    c = await session.get(Crypto, data["crypto_id"])
    holding = (await session.execute(
        select(CryptoHolding).where(CryptoHolding.user_id == db_user.id, CryptoHolding.crypto_id == c.id)
    )).scalar_one_or_none()

    if amount <= 0 or not holding or amount > holding.amount:
        await message.answer("❌ مقدار نامعتبره.")
        return

    revenue = amount * c.price
    await state.update_data(sell_amount=amount, revenue=revenue)
    await state.set_state(CryptoStates.confirm_sell)
    await message.answer(
        f"{header('✅ تایید فروش')}\n\n"
        f"₿ <b>{amount:.5f}</b> {c.symbol}\n"
        f"💰 درآمد: <code>{fmt_money(revenue)}</code> تومان\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb("crypto_sell_confirm", "market_crypto")
    )


@router.callback_query(F.data == "crypto_sell_confirm", CryptoStates.confirm_sell)
async def crypto_sell_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    amount = data.get("sell_amount")
    crypto_id = data.get("crypto_id")
    if amount is None or crypto_id is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return

    c = await session.get(Crypto, crypto_id)
    holding = (await session.execute(
        select(CryptoHolding).where(CryptoHolding.user_id == db_user.id, CryptoHolding.crypto_id == c.id)
    )).scalar_one_or_none()
    if not holding or amount > holding.amount:
        await callback.answer("❌ دیگه این مقدار رو نداری!", show_alert=True)
        await state.clear()
        return

    revenue = amount * c.price
    holding.amount -= amount
    db_user.cash += revenue
    await log_transaction(session, db_user.id, "crypto_sell", revenue, f"فروش {c.symbol}")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>{amount:.5f} {c.symbol}</b> فروخته شد!\n"
        f"💰 درآمد: <code>{fmt_money(revenue)}</code> تومان",
        reply_markup=back_kb("market_crypto")
    )
    await callback.answer("✅ فروخته شد!")
