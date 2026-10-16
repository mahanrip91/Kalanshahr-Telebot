"""
بورس سهام کلان‌شهر - خرید/فروش قبل از اجرا تایید داره
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy import select

from database.models import User, Stock, StockHolding
from core.keyboards import market_kb, back_kb, confirm_kb
from core.texts import header, NOT_ENOUGH_MONEY, INVALID_AMOUNT_TEXT
from core.economy import log_transaction
from core.reply_guard import set_prompt, check_reply
from utils.formatting import fmt_money, fmt_percent, parse_amount

router = Router(name="stocks")


class StockStates(StatesGroup):
    waiting_buy = State()
    confirm_buy = State()
    waiting_sell = State()
    confirm_sell = State()


def _change(stock: Stock) -> float:
    if not stock.previous_price:
        return 0.0
    return (stock.price - stock.previous_price) / stock.previous_price


@router.callback_query(F.data == "market_stocks")
async def stocks_list(callback: CallbackQuery, session):
    result = await session.execute(select(Stock))
    stocks = result.scalars().all()

    lines = [header("📈 بورس سهام کلان‌شهر"), ""]
    b = InlineKeyboardBuilder()
    for s in stocks:
        pct = _change(s)
        arrow = "🟢▲" if pct >= 0 else "🔴▼"
        lines.append(f"<b>{s.name}</b> ({s.symbol}) — <code>{fmt_money(s.price)}</code> {arrow} {fmt_percent(pct)}")
        b.button(text=f"{s.symbol}", callback_data=f"stock_view:{s.id}")
    b.adjust(4)
    b.row(InlineKeyboardButton(text="🔙 بازگشت به بازار مالی", callback_data="market_back"))

    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("stock_view:"))
async def stock_view(callback: CallbackQuery, session, db_user: User):
    stock_id = int(callback.data.split(":")[1])
    stock = await session.get(Stock, stock_id)
    if not stock:
        await callback.answer("سهم پیدا نشد!", show_alert=True)
        return

    holding = (await session.execute(
        select(StockHolding).where(StockHolding.user_id == db_user.id, StockHolding.stock_id == stock.id)
    )).scalar_one_or_none()

    pct = _change(stock)
    arrow = "🟢▲" if pct >= 0 else "🔴▼"
    text = (
        f"{header(f'📈 {stock.name} ({stock.symbol})')}\n\n"
        f"قیمت فعلی: <code>{fmt_money(stock.price)}</code> تومان\n"
        f"تغییر اخیر: {arrow} {fmt_percent(pct)}\n\n"
    )
    if holding and holding.amount > 0:
        value = holding.amount * stock.price
        profit = value - (holding.amount * holding.avg_buy_price)
        text += (
            f"🎒 دارایی تو: <b>{holding.amount:.2f}</b> سهم\n"
            f"میانگین خرید: <code>{fmt_money(holding.avg_buy_price)}</code>\n"
            f"ارزش فعلی: <code>{fmt_money(value)}</code>\n"
            f"سود/زیان: <code>{fmt_money(profit)}</code>\n"
        )
    else:
        text += "هنوز از این سهم نداری."

    b = InlineKeyboardBuilder()
    b.button(text="خرید", callback_data=f"stock_buy:{stock.id}", style="success")
    b.button(text="فروش", callback_data=f"stock_sell:{stock.id}", style="danger")
    b.button(text="🔙 بازگشت", callback_data="market_stocks")
    b.adjust(2, 1)
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("stock_buy:"))
async def stock_buy_start(callback: CallbackQuery, state: FSMContext):
    stock_id = int(callback.data.split(":")[1])
    await state.set_state(StockStates.waiting_buy)
    await callback.message.edit_text(
        f"{header('خرید سهم')}\n\n↩️ رو همین پیام ریپلای کن و بگو چند تومان",
        reply_markup=back_kb("market_stocks")
    )
    await set_prompt(state, callback.message.message_id, stock_id=stock_id)
    await callback.answer()


@router.message(StockStates.waiting_buy)
async def stock_buy_amount_ask(message: Message, state: FSMContext, session, db_user: User):
    if not await check_reply(message, state):
        return
    toman = parse_amount(message.text)
    if toman is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    data = await state.get_data()
    stock = await session.get(Stock, data["stock_id"])

    if toman > db_user.cash:
        await message.answer(NOT_ENOUGH_MONEY.format(cash=fmt_money(db_user.cash)))
        return

    shares = toman / stock.price
    await state.update_data(toman=toman, shares=shares)
    await state.set_state(StockStates.confirm_buy)
    await message.answer(
        f"{header('✅ تایید خرید')}\n\n"
        f"📈 <b>{stock.name}</b>: <b>{shares:.3f}</b> سهم\n"
        f"💰 مبلغ: <code>{fmt_money(toman)}</code> تومان\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb("stock_buy_confirm", "market_stocks")
    )


@router.callback_query(F.data == "stock_buy_confirm", StockStates.confirm_buy)
async def stock_buy_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    toman = data.get("toman")
    stock_id = data.get("stock_id")
    if toman is None or stock_id is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return
    if toman > db_user.cash:
        await callback.answer("❌ پولت کافی نیست!", show_alert=True)
        await state.clear()
        return

    stock = await session.get(Stock, stock_id)
    shares = toman / stock.price
    holding = (await session.execute(
        select(StockHolding).where(StockHolding.user_id == db_user.id, StockHolding.stock_id == stock.id)
    )).scalar_one_or_none()
    if not holding:
        holding = StockHolding(user_id=db_user.id, stock_id=stock.id, amount=0, avg_buy_price=0)
        session.add(holding)
        await session.flush()

    total_cost_before = holding.amount * holding.avg_buy_price
    new_amount = holding.amount + shares
    holding.avg_buy_price = (total_cost_before + toman) / new_amount
    holding.amount = new_amount

    db_user.cash -= toman
    await log_transaction(session, db_user.id, "stock_buy", -toman, f"خرید سهام {stock.symbol}")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>{shares:.3f}</b> سهم از <b>{stock.name}</b> خریداری شد!\n"
        f"💵 موجودی: <code>{fmt_money(db_user.cash)}</code>",
        reply_markup=back_kb("market_stocks")
    )
    await callback.answer("✅ خریداری شد!")


@router.callback_query(F.data.startswith("stock_sell:"))
async def stock_sell_start(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    stock_id = int(callback.data.split(":")[1])
    holding = (await session.execute(
        select(StockHolding).where(StockHolding.user_id == db_user.id, StockHolding.stock_id == stock_id)
    )).scalar_one_or_none()
    if not holding or holding.amount <= 0:
        await callback.answer("❌ از این سهم نداری!", show_alert=True)
        return

    await state.set_state(StockStates.waiting_sell)
    await callback.message.edit_text(
        f"{header('فروش سهم')}\n\nموجودی: <b>{holding.amount:.3f}</b>\n\n"
        f"↩️ رو همین پیام ریپلای کن و بگو چند سهم",
        reply_markup=back_kb("market_stocks")
    )
    await set_prompt(state, callback.message.message_id, stock_id=stock_id)
    await callback.answer()


@router.message(StockStates.waiting_sell)
async def stock_sell_amount_ask(message: Message, state: FSMContext, session, db_user: User):
    if not await check_reply(message, state):
        return
    try:
        amount = float(message.text.strip().replace(",", ""))
    except ValueError:
        await message.answer("❌ فقط عدد بفرست.")
        return

    data = await state.get_data()
    stock = await session.get(Stock, data["stock_id"])
    holding = (await session.execute(
        select(StockHolding).where(StockHolding.user_id == db_user.id, StockHolding.stock_id == stock.id)
    )).scalar_one_or_none()

    if amount <= 0 or not holding or amount > holding.amount:
        await message.answer("❌ مقدار نامعتبره یا بیشتر از دارایی توئه.")
        return

    revenue = amount * stock.price
    await state.update_data(sell_amount=amount, revenue=revenue)
    await state.set_state(StockStates.confirm_sell)
    await message.answer(
        f"{header('✅ تایید فروش')}\n\n"
        f"📈 <b>{amount:.3f}</b> سهم از <b>{stock.name}</b>\n"
        f"💰 درآمد: <code>{fmt_money(revenue)}</code> تومان\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb("stock_sell_confirm", "market_stocks")
    )


@router.callback_query(F.data == "stock_sell_confirm", StockStates.confirm_sell)
async def stock_sell_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    amount = data.get("sell_amount")
    stock_id = data.get("stock_id")
    if amount is None or stock_id is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return

    stock = await session.get(Stock, stock_id)
    holding = (await session.execute(
        select(StockHolding).where(StockHolding.user_id == db_user.id, StockHolding.stock_id == stock.id)
    )).scalar_one_or_none()
    if not holding or amount > holding.amount:
        await callback.answer("❌ دیگه این مقدار رو نداری!", show_alert=True)
        await state.clear()
        return

    revenue = amount * stock.price
    holding.amount -= amount
    db_user.cash += revenue
    await log_transaction(session, db_user.id, "stock_sell", revenue, f"فروش سهام {stock.symbol}")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>{amount:.3f}</b> سهم فروخته شد!\n"
        f"💰 درآمد: <code>{fmt_money(revenue)}</code> تومان\n"
        f"💵 موجودی نقد: <code>{fmt_money(db_user.cash)}</code> تومان",
        reply_markup=back_kb("market_stocks")
    )
    await callback.answer("✅ فروخته شد!")
