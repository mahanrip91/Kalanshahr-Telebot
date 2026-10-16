"""
بازار دلار، یورو و طلا - خرید/فروش با تایید
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from database.models import User, ForexAsset, ForexHolding
from core.keyboards import back_kb, market_kb, confirm_kb
from core.texts import header, NOT_ENOUGH_MONEY, INVALID_AMOUNT_TEXT
from core.economy import log_transaction
from core.reply_guard import set_prompt, check_reply
from utils.formatting import fmt_money, fmt_percent, parse_amount

router = Router(name="forex")


class ForexStates(StatesGroup):
    waiting_buy = State()
    confirm_buy = State()
    waiting_sell = State()
    confirm_sell = State()


def _change(a: ForexAsset) -> float:
    if not a.previous_price:
        return 0.0
    return (a.price - a.previous_price) / a.previous_price


@router.callback_query(F.data == "market_forex")
async def forex_list(callback: CallbackQuery, session):
    result = await session.execute(select(ForexAsset))
    assets = result.scalars().all()

    lines = [header("💵 بازار ارز و طلا"), ""]
    b = InlineKeyboardBuilder()
    for a in assets:
        pct = _change(a)
        arrow = "🟢▲" if pct >= 0 else "🔴▼"
        lines.append(f"<b>{a.name}</b> — <code>{fmt_money(a.price)}</code> تومان / {a.unit} {arrow} {fmt_percent(pct)}")
        b.button(text=f"{a.symbol}", callback_data=f"forex_view:{a.id}")
    b.adjust(4)
    b.row(InlineKeyboardButton(text="🔙 بازگشت به بازار مالی", callback_data="market_back"))

    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("forex_view:"))
async def forex_view(callback: CallbackQuery, session, db_user: User):
    asset_id = int(callback.data.split(":")[1])
    a = await session.get(ForexAsset, asset_id)
    if not a:
        await callback.answer("پیدا نشد!", show_alert=True)
        return

    holding = (await session.execute(
        select(ForexHolding).where(ForexHolding.user_id == db_user.id, ForexHolding.asset_id == a.id)
    )).scalar_one_or_none()

    pct = _change(a)
    arrow = "🟢▲" if pct >= 0 else "🔴▼"
    text = (
        f"{header(f'💵 {a.name}')}\n\n"
        f"قیمت هر {a.unit}: <code>{fmt_money(a.price)}</code> تومان\n"
        f"تغییر اخیر: {arrow} {fmt_percent(pct)}\n\n"
    )
    if holding and holding.amount > 0:
        value = holding.amount * a.price
        profit = value - (holding.amount * holding.avg_buy_price)
        text += (
            f"🎒 دارایی تو: <b>{holding.amount:.4f}</b> {a.unit}\n"
            f"میانگین خرید: <code>{fmt_money(holding.avg_buy_price)}</code>\n"
            f"ارزش فعلی: <code>{fmt_money(value)}</code>\n"
            f"سود/زیان: <code>{fmt_money(profit)}</code>\n"
        )
    else:
        text += "هنوز از این دارایی نداری."

    b = InlineKeyboardBuilder()
    b.button(text="خرید", callback_data=f"forex_buy:{a.id}", style="success")
    b.button(text="فروش", callback_data=f"forex_sell:{a.id}", style="danger")
    b.button(text="🔙 بازگشت", callback_data="market_forex")
    b.adjust(2, 1)
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("forex_buy:"))
async def forex_buy_start(callback: CallbackQuery, state: FSMContext):
    asset_id = int(callback.data.split(":")[1])
    await state.set_state(ForexStates.waiting_buy)
    await callback.message.edit_text(
        f"{header('خرید')}\n\n↩️ رو همین پیام ریپلای کن و بگو چند تومان",
        reply_markup=back_kb("market_forex")
    )
    await set_prompt(state, callback.message.message_id, asset_id=asset_id)
    await callback.answer()


@router.message(ForexStates.waiting_buy)
async def forex_buy_amount_ask(message: Message, state: FSMContext, session, db_user: User):
    if not await check_reply(message, state):
        return
    toman = parse_amount(message.text)
    if toman is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    data = await state.get_data()
    a = await session.get(ForexAsset, data["asset_id"])

    if toman > db_user.cash:
        await message.answer(NOT_ENOUGH_MONEY.format(cash=fmt_money(db_user.cash)))
        return

    units = toman / a.price
    await state.update_data(toman=toman, units=units)
    await state.set_state(ForexStates.confirm_buy)
    await message.answer(
        f"{header('✅ تایید خرید')}\n\n"
        f"💵 <b>{a.name}</b>: <b>{units:.4f}</b> {a.unit}\n"
        f"💰 مبلغ: <code>{fmt_money(toman)}</code> تومان\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb("forex_buy_confirm", "market_forex")
    )


@router.callback_query(F.data == "forex_buy_confirm", ForexStates.confirm_buy)
async def forex_buy_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    toman = data.get("toman")
    asset_id = data.get("asset_id")
    if toman is None or asset_id is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return
    if toman > db_user.cash:
        await callback.answer("❌ پولت کافی نیست!", show_alert=True)
        await state.clear()
        return

    a = await session.get(ForexAsset, asset_id)
    units = toman / a.price
    holding = (await session.execute(
        select(ForexHolding).where(ForexHolding.user_id == db_user.id, ForexHolding.asset_id == a.id)
    )).scalar_one_or_none()
    if not holding:
        holding = ForexHolding(user_id=db_user.id, asset_id=a.id, amount=0, avg_buy_price=0)
        session.add(holding)
        await session.flush()

    total_cost_before = holding.amount * holding.avg_buy_price
    new_amount = holding.amount + units
    holding.avg_buy_price = (total_cost_before + toman) / new_amount
    holding.amount = new_amount

    db_user.cash -= toman
    await log_transaction(session, db_user.id, "forex_buy", -toman, f"خرید {a.symbol}")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>{units:.4f} {a.unit}</b> از <b>{a.name}</b> خریداری شد!\n"
        f"💵 موجودی نقد: <code>{fmt_money(db_user.cash)}</code> تومان",
        reply_markup=back_kb("market_forex")
    )
    await callback.answer("✅ خریداری شد!")


@router.callback_query(F.data.startswith("forex_sell:"))
async def forex_sell_start(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    asset_id = int(callback.data.split(":")[1])
    holding = (await session.execute(
        select(ForexHolding).where(ForexHolding.user_id == db_user.id, ForexHolding.asset_id == asset_id)
    )).scalar_one_or_none()
    if not holding or holding.amount <= 0:
        await callback.answer("❌ از این دارایی نداری!", show_alert=True)
        return

    await state.set_state(ForexStates.waiting_sell)
    await callback.message.edit_text(
        f"{header('فروش')}\n\nموجودی: <b>{holding.amount:.4f}</b>\n\n↩️ رو همین پیام ریپلای کن و بگو چه مقدار",
        reply_markup=back_kb("market_forex")
    )
    await set_prompt(state, callback.message.message_id, asset_id=asset_id)
    await callback.answer()


@router.message(ForexStates.waiting_sell)
async def forex_sell_amount_ask(message: Message, state: FSMContext, session, db_user: User):
    if not await check_reply(message, state):
        return
    try:
        amount = float(message.text.strip().replace(",", ""))
    except ValueError:
        await message.answer("❌ فقط عدد بفرست.")
        return

    data = await state.get_data()
    a = await session.get(ForexAsset, data["asset_id"])
    holding = (await session.execute(
        select(ForexHolding).where(ForexHolding.user_id == db_user.id, ForexHolding.asset_id == a.id)
    )).scalar_one_or_none()

    if amount <= 0 or not holding or amount > holding.amount:
        await message.answer("❌ مقدار نامعتبره.")
        return

    revenue = amount * a.price
    await state.update_data(sell_amount=amount, revenue=revenue)
    await state.set_state(ForexStates.confirm_sell)
    await message.answer(
        f"{header('✅ تایید فروش')}\n\n"
        f"💵 <b>{amount:.4f}</b> {a.unit}\n"
        f"💰 درآمد: <code>{fmt_money(revenue)}</code> تومان\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb("forex_sell_confirm", "market_forex")
    )


@router.callback_query(F.data == "forex_sell_confirm", ForexStates.confirm_sell)
async def forex_sell_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    amount = data.get("sell_amount")
    asset_id = data.get("asset_id")
    if amount is None or asset_id is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return

    a = await session.get(ForexAsset, asset_id)
    holding = (await session.execute(
        select(ForexHolding).where(ForexHolding.user_id == db_user.id, ForexHolding.asset_id == a.id)
    )).scalar_one_or_none()
    if not holding or amount > holding.amount:
        await callback.answer("❌ دیگه این مقدار رو نداری!", show_alert=True)
        await state.clear()
        return

    revenue = amount * a.price
    holding.amount -= amount
    db_user.cash += revenue
    await log_transaction(session, db_user.id, "forex_sell", revenue, f"فروش {a.symbol}")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>{amount:.4f} {a.unit}</b> فروخته شد!\n"
        f"💰 درآمد: <code>{fmt_money(revenue)}</code> تومان",
        reply_markup=back_kb("market_forex")
    )
    await callback.answer("✅ فروخته شد!")


@router.message(F.text.in_({"📈 بازار مالی", "بازار مالی", "بازار"}))
async def market_menu(message: Message):
    await message.answer(f"{header('📈 مرکز بازار مالی کلان‌شهر')}\n\nیکی از بازارها رو انتخاب کن:", reply_markup=market_kb())


@router.callback_query(F.data == "market_back")
async def market_back(callback: CallbackQuery):
    await callback.message.edit_text(f"{header('📈 مرکز بازار مالی کلان‌شهر')}\n\nیکی از بازارها رو انتخاب کن:", reply_markup=market_kb())
    await callback.answer()


@router.callback_query(F.data == "market_portfolio")
async def market_portfolio(callback: CallbackQuery, session, db_user: User):
    from database.models import StockHolding, CryptoHolding, Stock

    stocks = (await session.execute(
        select(StockHolding).where(StockHolding.user_id == db_user.id, StockHolding.amount > 0)
    )).scalars().all()
    cryptos = (await session.execute(
        select(CryptoHolding).where(CryptoHolding.user_id == db_user.id, CryptoHolding.amount > 0)
    )).scalars().all()
    forex = (await session.execute(
        select(ForexHolding).where(ForexHolding.user_id == db_user.id, ForexHolding.amount > 0)
    )).scalars().all()

    total_value = 0.0
    lines = [header("💼 پرتفوی سرمایه‌گذاری من")]

    if stocks:
        lines.append("\n📈 <b>سهام:</b>")
        for h in stocks:
            s = await session.get(Stock, h.stock_id)
            value = h.amount * s.price
            total_value += value
            lines.append(f"  • {s.symbol}: {h.amount:.3f} = <code>{fmt_money(value)}</code>")

    if cryptos:
        lines.append("\n₿ <b>ارز دیجیتال:</b>")
        for h in cryptos:
            from database.models import Crypto
            c = await session.get(Crypto, h.crypto_id)
            value = h.amount * c.price
            total_value += value
            lines.append(f"  • {c.symbol}: {h.amount:.5f} = <code>{fmt_money(value)}</code>")

    if forex:
        lines.append("\n💵 <b>ارز و طلا:</b>")
        for h in forex:
            a = await session.get(ForexAsset, h.asset_id)
            value = h.amount * a.price
            total_value += value
            lines.append(f"  • {a.name}: {h.amount:.4f} = <code>{fmt_money(value)}</code>")

    if not (stocks or cryptos or forex):
        lines.append("\nهنوز هیچ سرمایه‌گذاری نداری!")
    else:
        lines.append(f"\n💎 ارزش کل پرتفوی: <code>{fmt_money(total_value)}</code> تومان")

    await callback.message.edit_text("\n".join(lines), reply_markup=back_kb("market_back"))
    await callback.answer()
