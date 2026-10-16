"""
خزانه شهر: کمک مالی اعضا و ارتقای سطح شهر - با تایید/برگشت قبل از کمک
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from database.models import City, CityContribution, User
from core.texts import header, NOT_ENOUGH_MONEY, INVALID_AMOUNT_TEXT
from core.keyboards import back_kb, confirm_kb
from core.reply_guard import set_prompt, check_reply
from utils.formatting import fmt_money, parse_amount
from handlers.city.status import current_city_level, _city_metrics

router = Router(name="city_treasury")


class TreasuryStates(StatesGroup):
    waiting_amount = State()
    confirm_amount = State()


@router.callback_query(F.data == "city_treasury")
async def treasury_menu(callback: CallbackQuery, state: FSMContext, session):
    result = await session.execute(select(City).where(City.chat_id == callback.message.chat.id))
    city = result.scalar_one_or_none()
    if not city or not city.is_active:
        await callback.answer("❌ این گروه هنوز کلان‌شهر نیست!", show_alert=True)
        return

    await state.update_data(city_id=city.id)
    await state.set_state(TreasuryStates.waiting_amount)
    await callback.message.edit_text(
        f"{header('💰 خزانه کلان‌شهر')}\n\n"
        f"موجودی: <code>{fmt_money(city.treasury)}</code>\n\n"
        f"↩️ رو همین پیام ریپلای کن و بگو چقدر کمک می‌کنی",
        reply_markup=back_kb("city_back")
    )
    await set_prompt(state, callback.message.message_id, city_id=city.id)
    await callback.answer()


@router.message(TreasuryStates.waiting_amount)
async def treasury_contribute(message: Message, state: FSMContext, db_user: User):
    if not await check_reply(message, state):
        return
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    if amount > db_user.cash:
        await message.answer(NOT_ENOUGH_MONEY.format(cash=fmt_money(db_user.cash)))
        return

    data = await state.get_data()
    await state.update_data(amount=amount)
    await state.set_state(TreasuryStates.confirm_amount)
    await message.answer(
        f"{header('✅ تایید کمک به خزانه')}\n\n"
        f"💰 مبلغ: <code>{fmt_money(amount)}</code> تومان\n\n"
        f"مطمئنی می‌خوای این مبلغ رو به خزانه شهر بدی؟ (برگشت‌ناپذیره)",
        reply_markup=confirm_kb("treasury_confirm", "treasury_cancel")
    )


@router.callback_query(F.data == "treasury_confirm", TreasuryStates.confirm_amount)
async def treasury_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    amount = data.get("amount")
    city_id = data.get("city_id")
    if amount is None or city_id is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return
    if amount > db_user.cash:
        await callback.answer("❌ پولت کافی نیست!", show_alert=True)
        await state.clear()
        return

    city = await session.get(City, city_id)
    if not city:
        await callback.answer("❌ شهر پیدا نشد.", show_alert=True)
        await state.clear()
        return

    try:
        member_count = await callback.bot.get_chat_member_count(city.chat_id)
    except Exception:
        member_count = 0
    old_metrics = await _city_metrics(session, city, member_count)
    old_level = current_city_level(old_metrics)

    db_user.cash -= amount
    city.treasury += amount
    session.add(CityContribution(city_id=city.id, telegram_id=db_user.telegram_id, amount=amount))
    await session.commit()

    new_metrics = await _city_metrics(session, city, member_count)
    new_level = current_city_level(new_metrics)
    await state.clear()

    text = (
        f"✅ <code>{fmt_money(amount)}</code> به خزانه اضافه شد!\n"
        f"💰 خزانه جدید: <code>{fmt_money(city.treasury)}</code>"
    )
    if new_level["name"] != old_level["name"]:
        city.status = new_level["name"]
        await session.commit()
        text = f"🎉 <b>شهر ارتقا پیدا کرد!</b> «{old_level['name']}» → «<b>{new_level['name']}</b>»\n\n" + text

    await callback.message.edit_text(text, reply_markup=back_kb("city_back"))
    await callback.answer("✅ کمک ثبت شد، ممنون!")


@router.callback_query(F.data == "treasury_cancel")
async def treasury_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(f"{header('💰 خزانه کلان‌شهر')}\n\n❌ کمک لغو شد.", reply_markup=back_kb("city_back"))
    await callback.answer()
