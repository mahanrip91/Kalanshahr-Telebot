"""
هندلر /start ، ثبت‌نام خودکار، رفرال و پنل اصلی
"""
from aiogram import Router, F
from aiogram.filters import CommandStart, CommandObject
from aiogram.types import Message
from sqlalchemy import select

from database.models import User
from core.keyboards import main_menu_kb
from core.texts import WELCOME_TEXT, header
from core.economy import add_cash
from utils.formatting import fmt_money

router = Router(name="start")


@router.message(CommandStart(deep_link=True))
async def start_with_referral(message: Message, command: CommandObject, session, db_user: User, is_new_user: bool):
    if is_new_user and command.args and command.args.isdigit():
        ref_id = int(command.args)
        if ref_id != db_user.telegram_id:
            result = await session.execute(select(User).where(User.telegram_id == ref_id))
            ref_user = result.scalar_one_or_none()
            if ref_user:
                db_user.referred_by = ref_id
                await session.commit()
                await add_cash(session, ref_user, 3000, "پاداش دعوت دوست")
                await add_cash(session, db_user, 2000, "هدیه خوش‌آمدگویی رفرال")
    await send_welcome(message, db_user, is_new_user)


@router.message(CommandStart())
async def start_plain(message: Message, db_user: User, is_new_user: bool):
    await send_welcome(message, db_user, is_new_user)


async def send_welcome(message: Message, db_user: User, is_new_user: bool):
    text = WELCOME_TEXT.format(name=db_user.first_name or "دوست عزیز")
    if not is_new_user:
        text += f"\n\n💰 موجودی فعلی: <code>{fmt_money(db_user.cash)}</code> تومان"
    await message.answer(text, reply_markup=main_menu_kb(db_user.telegram_id))


@router.message(F.text.in_({"🏠 پنل اصلی", "پنل اصلی", "پنل"}))
async def main_panel(message: Message, db_user: User):
    text = (
        f"{header('🏠 پنل اصلی کلان‌شهر')}\n\n"
        f"👋 سلام <b>{db_user.first_name}</b>!\n"
        f"🏅 سطح: <code>{db_user.level}</code>\n"
        f"💵 نقد: <code>{fmt_money(db_user.cash)}</code> تومان\n"
        f"🏦 بانک: <code>{fmt_money(db_user.bank_balance)}</code> تومان\n"
        f"💎 ثروت کل: <code>{fmt_money(db_user.total_wealth())}</code> تومان\n\n"
        f"از منوی پایین یکی از بخش‌ها رو انتخاب کن، یا هرجا هستی فقط اسمش رو تایپ کن 👇"
    )
    await message.answer(text, reply_markup=main_menu_kb(db_user.telegram_id))
