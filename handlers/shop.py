"""
سیستم مغازه‌داری: باز کردن مغازه، خرید عمده، فروش، استخدام کارگر
افتتاح/خرید عمده/استخدام هرکدوم قبل از اجرا یه تایید دارن.
"""
import random
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from database.models import User, Shop
from core.texts import header, NOT_ENOUGH_MONEY, INVALID_AMOUNT_TEXT
from core.economy import log_transaction
from core.auto_revert import schedule_revert
from core.keyboards import confirm_kb
from core.reply_guard import set_prompt, check_reply
from utils.formatting import fmt_money, parse_amount

router = Router(name="shop")

SHOP_OPEN_COST = 60_000
WHOLESALE_UNIT_PRICE = 800
SELL_UNIT_PRICE_BASE = 1400
EMPLOYEE_COST = 50_000
EMPLOYEE_CAPACITY_BOOST = 0.4
BASE_DAILY_SELL_CAPACITY = 40


class ShopStates(StatesGroup):
    waiting_shop_name = State()
    confirm_open = State()
    waiting_buy_amount = State()
    confirm_buy = State()


async def _get_shop(session, user_id: int):
    result = await session.execute(select(Shop).where(Shop.user_id == user_id))
    return result.scalar_one_or_none()


def _shop_text(shop: Shop) -> str:
    return (
        f"{header(f'🛒 {shop.name}')}\n\n"
        f"💰 موجودی نقدی مغازه: <code>{fmt_money(shop.capital)}</code> تومان\n"
        f"📦 موجودی کالا: <b>{shop.inventory_count}</b> عدد\n"
        f"👷 تعداد کارگر: <b>{shop.employees}</b>\n"
        f"📈 سود کل تا الان: <code>{fmt_money(shop.total_profit)}</code> تومان\n"
    )


def _shop_kb() -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.button(text="📦 خرید عمده کالا", callback_data="shop_buy", style="success")
    b.button(text="💰 فروش امروز", callback_data="shop_sell_today")
    b.button(text="👷 استخدام کارگر", callback_data="shop_hire_ask", style="primary")
    b.button(text="🏦 انتقال سود به کیف پول", callback_data="shop_withdraw", style="primary")
    b.adjust(1)
    return b


@router.message(F.text.in_({"🛒 مغازه‌داری", "مغازه‌داری", "مغازه داری", "مغازه"}))
async def shop_menu(message: Message, state: FSMContext, session, db_user: User):
    shop = await _get_shop(session, db_user.id)
    if not shop:
        prompt = await message.answer(
            f"{header('🛒 مغازه‌داری')}\n\n"
            f"هزینه باز کردن: <code>{fmt_money(SHOP_OPEN_COST)}</code>\n\n"
            f"↩️ رو همین پیام ریپلای کن و اسم مغازه‌ت رو بفرست"
        )
        await state.set_state(ShopStates.waiting_shop_name)
        await set_prompt(state, prompt.message_id)
        return

    await message.answer(_shop_text(shop), reply_markup=_shop_kb().as_markup())


@router.message(ShopStates.waiting_shop_name)
async def create_shop_ask(message: Message, state: FSMContext, db_user: User):
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("لغو شد.")
        return
    if not await check_reply(message, state):
        return

    name = message.text.strip()
    if not (2 <= len(name) <= 30):
        await message.answer("❌ اسم باید بین ۲ تا ۳۰ کاراکتر باشه.")
        return
    if db_user.cash < SHOP_OPEN_COST:
        await message.answer(NOT_ENOUGH_MONEY.format(cash=fmt_money(db_user.cash)))
        return

    await state.update_data(shop_name=name)
    await state.set_state(ShopStates.confirm_open)
    await message.answer(
        f"{header('✅ تایید افتتاح مغازه')}\n\n"
        f"🏪 اسم: <b>{name}</b>\n"
        f"💰 هزینه: <code>{fmt_money(SHOP_OPEN_COST)}</code> تومان\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb("shop_open_confirm", "shop_open_cancel")
    )


@router.callback_query(F.data == "shop_open_confirm", ShopStates.confirm_open)
async def create_shop_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    name = data.get("shop_name")
    if not name:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return
    if db_user.cash < SHOP_OPEN_COST:
        await callback.answer("❌ پولت کافی نیست!", show_alert=True)
        await state.clear()
        return

    db_user.cash -= SHOP_OPEN_COST
    shop = Shop(user_id=db_user.id, name=name, capital=0)
    session.add(shop)
    await log_transaction(session, db_user.id, "shop_open", -SHOP_OPEN_COST, "افتتاح مغازه")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ مغازه <b>{name}</b> با موفقیت افتتاح شد! 🎉\n\nحالا از منوی مغازه، کالا بخر و شروع کن.",
        reply_markup=_shop_kb().as_markup()
    )
    await callback.answer("✅ افتتاح شد!")


@router.callback_query(F.data == "shop_open_cancel")
async def create_shop_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ افتتاح مغازه لغو شد.")
    await callback.answer()


@router.callback_query(F.data == "shop_buy")
async def shop_buy_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(ShopStates.waiting_buy_amount)
    await callback.message.edit_text(
        f"{header('📦 خرید عمده')}\n\n"
        f"هر واحد: <code>{fmt_money(WHOLESALE_UNIT_PRICE)}</code>\n\n"
        f"↩️ رو همین پیام ریپلای کن و بگو چند واحد"
    )
    await set_prompt(state, callback.message.message_id)
    await callback.answer()


@router.message(ShopStates.waiting_buy_amount)
async def shop_buy_amount_ask(message: Message, state: FSMContext, db_user: User):
    if not await check_reply(message, state):
        return
    units = parse_amount(message.text)
    if units is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    cost = units * WHOLESALE_UNIT_PRICE
    if db_user.cash < cost:
        await message.answer(NOT_ENOUGH_MONEY.format(cash=fmt_money(db_user.cash)))
        return

    await state.update_data(units=units, cost=cost)
    await state.set_state(ShopStates.confirm_buy)
    await message.answer(
        f"{header('✅ تایید خرید عمده')}\n\n"
        f"📦 تعداد: <b>{units}</b> واحد\n"
        f"💰 هزینه کل: <code>{fmt_money(cost)}</code> تومان\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb("shop_buy_confirm", "shop_buy_cancel")
    )


@router.callback_query(F.data == "shop_buy_confirm", ShopStates.confirm_buy)
async def shop_buy_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    units = data.get("units")
    cost = data.get("cost")
    if units is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return
    if db_user.cash < cost:
        await callback.answer("❌ پولت کافی نیست!", show_alert=True)
        await state.clear()
        return

    shop = await _get_shop(session, db_user.id)
    db_user.cash -= cost
    shop.inventory_count += units
    shop.inventory_value += cost
    await log_transaction(session, db_user.id, "shop_stock", -cost, f"خرید {units} واحد کالا")
    await session.commit()
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>{units}</b> واحد کالا خریداری شد!\n"
        f"💵 موجودی نقد: <code>{fmt_money(db_user.cash)}</code> تومان",
        reply_markup=_shop_kb().as_markup()
    )
    await callback.answer("✅ خریداری شد!")


@router.callback_query(F.data == "shop_buy_cancel")
async def shop_buy_cancel(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    await state.clear()
    shop = await _get_shop(session, db_user.id)
    await callback.message.edit_text(_shop_text(shop), reply_markup=_shop_kb().as_markup())
    await callback.answer("❌ خرید لغو شد.")


@router.callback_query(F.data == "shop_sell_today")
async def shop_sell(callback: CallbackQuery, session, db_user: User):
    shop = await _get_shop(session, db_user.id)
    if not shop or shop.inventory_count <= 0:
        await callback.answer("❌ موجودی کالا نداری! اول خرید کن.", show_alert=True)
        return

    capacity = round(BASE_DAILY_SELL_CAPACITY * (1 + shop.employees * EMPLOYEE_CAPACITY_BOOST))
    sold = min(shop.inventory_count, random.randint(max(1, int(capacity * 0.6)), max(1, capacity)))

    avg_cost_per_unit = shop.inventory_value / shop.inventory_count if shop.inventory_count else WHOLESALE_UNIT_PRICE
    sell_price = SELL_UNIT_PRICE_BASE * random.uniform(0.85, 1.2)
    revenue = round(sold * sell_price)
    cost_of_goods = round(sold * avg_cost_per_unit)
    profit = revenue - cost_of_goods

    salary_cost = shop.employees * 8000
    profit -= salary_cost

    shop.inventory_count -= sold
    shop.inventory_value -= cost_of_goods
    shop.capital += profit
    shop.total_profit += profit

    await log_transaction(session, db_user.id, "shop_sell", profit, f"فروش {sold} واحد کالا")
    await session.commit()

    result_icon = "📈" if profit >= 0 else "📉"
    await callback.message.edit_text(
        f"{header('💰 گزارش فروش امروز')}\n\n"
        f"📦 تعداد فروخته‌شده: <b>{sold}</b> واحد\n"
        f"💵 درآمد: <code>{fmt_money(revenue)}</code> تومان\n"
        f"👷 هزینه کارگر: <code>{fmt_money(salary_cost)}</code> تومان\n"
        f"{result_icon} سود خالص: <code>{fmt_money(profit)}</code> تومان\n\n"
        f"💰 سرمایه مغازه: <code>{fmt_money(shop.capital)}</code> تومان",
        reply_markup=_shop_kb().as_markup()
    )
    await callback.answer()
    schedule_revert(callback.message, _shop_text(shop), _shop_kb().as_markup())


@router.callback_query(F.data == "shop_hire_ask")
async def shop_hire_ask(callback: CallbackQuery, db_user: User):
    if db_user.cash < EMPLOYEE_COST:
        await callback.answer(f"❌ برای استخدام {fmt_money(EMPLOYEE_COST)} تومان لازمه!", show_alert=True)
        return
    await callback.message.edit_text(
        f"{header('✅ تایید استخدام')}\n\n"
        f"👷 هزینه استخدام یه کارگر جدید: <code>{fmt_money(EMPLOYEE_COST)}</code> تومان\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb("shop_hire_confirm", "shop_hire_cancel")
    )
    await callback.answer()


@router.callback_query(F.data == "shop_hire_confirm")
async def shop_hire_confirm(callback: CallbackQuery, session, db_user: User):
    shop = await _get_shop(session, db_user.id)
    if db_user.cash < EMPLOYEE_COST:
        await callback.answer(f"❌ برای استخدام {fmt_money(EMPLOYEE_COST)} تومان لازمه!", show_alert=True)
        return

    db_user.cash -= EMPLOYEE_COST
    shop.employees += 1
    await log_transaction(session, db_user.id, "shop_hire", -EMPLOYEE_COST, "استخدام کارگر مغازه")
    await session.commit()

    await callback.answer("✅ یه کارگر جدید استخدام شد!", show_alert=True)
    await callback.message.edit_text(_shop_text(shop), reply_markup=_shop_kb().as_markup())


@router.callback_query(F.data == "shop_hire_cancel")
async def shop_hire_cancel(callback: CallbackQuery, session, db_user: User):
    shop = await _get_shop(session, db_user.id)
    await callback.message.edit_text(_shop_text(shop), reply_markup=_shop_kb().as_markup())
    await callback.answer("❌ استخدام لغو شد.")


@router.callback_query(F.data == "shop_withdraw")
async def shop_withdraw(callback: CallbackQuery, session, db_user: User):
    shop = await _get_shop(session, db_user.id)
    if shop.capital <= 0:
        await callback.answer("❌ سرمایه‌ای برای انتقال نیست!", show_alert=True)
        return

    amount = shop.capital
    shop.capital = 0
    db_user.cash += amount
    await log_transaction(session, db_user.id, "shop_withdraw", amount, "برداشت سود مغازه")
    await session.commit()

    await callback.answer(f"✅ {fmt_money(amount)} تومان به کیف پولت منتقل شد!", show_alert=True)
    await callback.message.edit_text(_shop_text(shop), reply_markup=_shop_kb().as_markup())
