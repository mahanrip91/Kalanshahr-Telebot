"""
سیستم رتبه‌بندی (لیدربورد) + انتقال نقدی سریع بین کاربران (با آیدی/یوزرنیم)
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, desc

from database.models import User, Property
from core.texts import header, NOT_ENOUGH_MONEY, INVALID_AMOUNT_TEXT
from core.economy import log_transaction
from core.reply_guard import set_prompt, check_reply
from utils.formatting import fmt_money, parse_amount

router = Router(name="leaderboard")


class TransferStates(StatesGroup):
    waiting_target = State()
    waiting_amount = State()


def leaderboard_kb() -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.button(text="💎 ثروت", callback_data="lb_wealth")
    b.button(text="🏅 سطح", callback_data="lb_level", style="primary")
    b.button(text="🏠 املاک", callback_data="lb_property", style="primary")
    b.adjust(3)
    return b


@router.message(F.text.in_({"📊 رتبه‌بندی", "رتبه‌بندی", "رتبه بندی"}))
async def leaderboard_menu(message: Message):
    await message.answer(f"{header('📊 رتبه‌بندی کلان‌شهر')}\n\nیک لیدربورد انتخاب کن:", reply_markup=leaderboard_kb().as_markup())


@router.callback_query(F.data == "lb_wealth")
async def lb_wealth(callback: CallbackQuery, session):
    result = await session.execute(select(User).order_by(desc(User.cash + User.bank_balance)).limit(10))
    users = result.scalars().all()
    lines = [header("💎 برترین‌های ثروت")]
    medals = ["🥇", "🥈", "🥉"]
    for i, u in enumerate(users):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {u.first_name or 'کاربر'} — <code>{fmt_money(u.total_wealth())}</code>")
    await callback.message.edit_text("\n".join(lines), reply_markup=leaderboard_kb().as_markup())
    await callback.answer()


@router.callback_query(F.data == "lb_level")
async def lb_level(callback: CallbackQuery, session):
    result = await session.execute(select(User).order_by(desc(User.level), desc(User.xp)).limit(10))
    users = result.scalars().all()
    lines = [header("🏅 برترین‌های سطح")]
    medals = ["🥇", "🥈", "🥉"]
    for i, u in enumerate(users):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {u.first_name or 'کاربر'} — سطح <b>{u.level}</b>")
    await callback.message.edit_text("\n".join(lines), reply_markup=leaderboard_kb().as_markup())
    await callback.answer()


@router.callback_query(F.data == "lb_property")
async def lb_property(callback: CallbackQuery, session):
    result = await session.execute(
        select(Property.user_id, User.first_name)
        .join(User, User.id == Property.user_id)
    )
    rows = result.all()
    counts = {}
    names = {}
    for user_id, name in rows:
        counts[user_id] = counts.get(user_id, 0) + 1
        names[user_id] = name

    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
    lines = [header("🏠 برترین‌های املاک")]
    medals = ["🥇", "🥈", "🥉"]
    if not top:
        lines.append("هنوز کسی ملکی نداره.")
    for i, (user_id, count) in enumerate(top):
        medal = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{medal} {names[user_id] or 'کاربر'} — <b>{count}</b> ملک")

    await callback.message.edit_text("\n".join(lines), reply_markup=leaderboard_kb().as_markup())
    await callback.answer()


# ---------------- انتقال پول سریع (نقدی، با آیدی/یوزرنیم) ----------------

@router.message(F.text.startswith("/انتقال") | F.text.startswith("انتقال پول"))
async def transfer_start(message: Message, state: FSMContext):
    prompt = await message.answer(
        f"{header('💸 انتقال پول')}\n\n"
        f"↩️ رو همین پیام ریپلای کن و آیدی عددی یا یوزرنیم مقصد رو بفرست"
    )
    await state.set_state(TransferStates.waiting_target)
    await set_prompt(state, prompt.message_id)


@router.message(TransferStates.waiting_target)
async def transfer_target(message: Message, state: FSMContext, session):
    if not await check_reply(message, state):
        return
    target_text = message.text.strip().lstrip("@")
    target_user = None

    if target_text.isdigit():
        result = await session.execute(select(User).where(User.telegram_id == int(target_text)))
        target_user = result.scalar_one_or_none()
    else:
        result = await session.execute(select(User).where(User.username == target_text))
        target_user = result.scalar_one_or_none()

    if not target_user:
        await message.answer("❌ کاربر پیدا نشد! دوباره امتحان کن یا /لغو بزن.")
        return

    prompt = await message.answer(f"✅ <b>{target_user.first_name}</b>\n↩️ رو همین پیام ریپلای کن و بگو چقدر")
    await state.update_data(target_id=target_user.id, target_name=target_user.first_name)
    await state.set_state(TransferStates.waiting_amount)
    await set_prompt(state, prompt.message_id)


@router.message(TransferStates.waiting_amount)
async def transfer_amount(message: Message, state: FSMContext, session, db_user: User):
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
    target = await session.get(User, data["target_id"])
    if not target:
        await message.answer("❌ کاربر مقصد دیگه معتبر نیست.")
        await state.clear()
        return
    if target.id == db_user.id:
        await message.answer("❌ نمیتونی به خودت پول بفرستی!")
        return

    fee = round(amount * 0.02)
    net = amount - fee

    db_user.cash -= amount
    target.cash += net
    await log_transaction(session, db_user.id, "transfer_out", -amount, f"انتقال به {target.first_name}")
    await log_transaction(session, target.id, "transfer_in", net, f"دریافت از {db_user.first_name}")
    await session.commit()
    await state.clear()

    await message.answer(
        f"✅ <code>{fmt_money(amount)}</code> تومان ارسال شد!\n"
        f"💸 کارمزد: <code>{fmt_money(fee)}</code> تومان (۲٪)\n"
        f"📥 مبلغ دریافتی طرف مقابل: <code>{fmt_money(net)}</code> تومان"
    )
    try:
        await message.bot.send_message(
            target.telegram_id,
            f"💸 <b>{db_user.first_name}</b> مبلغ <code>{fmt_money(net)}</code> تومان برات فرستاد!",
            parse_mode="HTML"
        )
    except Exception:
        pass
