"""
صفحه حساب من - پروفایل کاربر با نوار پیشرفت XP
"""
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select, desc

from database.models import User, Transaction, StockHolding, CryptoHolding, ForexHolding, Property
from core.keyboards import profile_kb, back_kb
from core.texts import header
from config import xp_needed_for_level
from utils.formatting import fmt_money, progress_bar

router = Router(name="profile")


def build_profile_text(user: User) -> str:
    xp_need = xp_needed_for_level(user.level)
    bar = progress_bar(user.xp, xp_need)
    job = user.job or "بیکار 😅"

    return (
        f"{header('👤 حساب من')}\n\n"
        f"🆔 آیدی: <code>{user.telegram_id}</code>\n"
        f"📛 نام: <b>{user.first_name}</b>\n\n"
        f"🏅 سطح: <b>{user.level}</b>\n"
        f"{bar}\n"
        f"<code>{user.xp}/{xp_need} XP</code>\n\n"
        f"💼 شغل: <b>{job}</b> (لول {user.job_level})\n\n"
        f"💵 نقد: <code>{fmt_money(user.cash)}</code> تومان\n"
        f"🏦 بانک: <code>{fmt_money(user.bank_balance)}</code> تومان\n"
        f"💎 ثروت کل: <code>{fmt_money(user.total_wealth())}</code> تومان\n"
        f"🔴 بدهی وام: <code>{fmt_money(user.loan_amount)}</code> تومان\n"
    )


@router.message(F.text.in_({"👤 حساب من", "حساب من"}))
async def profile_menu(message: Message, db_user: User):
    await message.answer(build_profile_text(db_user), reply_markup=profile_kb())


@router.callback_query(F.data == "profile_history")
async def profile_history(callback: CallbackQuery, session, db_user: User):
    result = await session.execute(
        select(Transaction).where(Transaction.user_id == db_user.id)
        .order_by(desc(Transaction.created_at)).limit(10)
    )
    txs = result.scalars().all()
    if not txs:
        text = f"{header('📜 تراکنش‌های اخیر')}\n\nهنوز تراکنشی ثبت نشده."
    else:
        lines = [header("📜 ۱۰ تراکنش اخیر"), ""]
        for tx in txs:
            sign = "🟢" if tx.amount >= 0 else "🔴"
            lines.append(f"{sign} <code>{fmt_money(abs(tx.amount))}</code> — {tx.description}")
        text = "\n".join(lines)
    await callback.message.edit_text(text, reply_markup=back_kb("profile_back"))
    await callback.answer()


@router.callback_query(F.data == "profile_assets")
async def profile_assets(callback: CallbackQuery, session, db_user: User):
    stocks = (await session.execute(
        select(StockHolding).where(StockHolding.user_id == db_user.id, StockHolding.amount > 0)
    )).scalars().all()
    cryptos = (await session.execute(
        select(CryptoHolding).where(CryptoHolding.user_id == db_user.id, CryptoHolding.amount > 0)
    )).scalars().all()
    forex = (await session.execute(
        select(ForexHolding).where(ForexHolding.user_id == db_user.id, ForexHolding.amount > 0)
    )).scalars().all()
    props = (await session.execute(
        select(Property).where(Property.user_id == db_user.id)
    )).scalars().all()

    lines = [header("🎒 دارایی‌های من")]
    lines.append(f"\n📈 سهام: <b>{len(stocks)}</b> نوع")
    lines.append(f"₿ ارز دیجیتال: <b>{len(cryptos)}</b> نوع")
    lines.append(f"💵 دلار/طلا: <b>{len(forex)}</b> نوع")
    lines.append(f"🏠 املاک: <b>{len(props)}</b> مورد")
    lines.append("\nجزئیات کامل رو از بخش «📈 بازار مالی» و «🏗️ ساخت‌وساز» ببین.")

    await callback.message.edit_text("\n".join(lines), reply_markup=back_kb("profile_back"))
    await callback.answer()


@router.callback_query(F.data == "profile_back")
async def profile_back(callback: CallbackQuery, db_user: User):
    await callback.message.edit_text(build_profile_text(db_user), reply_markup=profile_kb())
    await callback.answer()
