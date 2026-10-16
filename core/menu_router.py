"""
روتر مخصوص دکمه‌های اصلی منو با بالاترین اولویت.
"""
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from core.economy import is_in_prison
from config import settings

router = Router(name="menu_priority")

PRISON_ALLOWED_SECTIONS = {"go_profile", "go_settings", "go_help", "go_main", "go_owner"}


async def _blocked_by_prison(message: Message, db_user, section: str) -> bool:
    if not db_user or not is_in_prison(db_user):
        return False
    from handlers.city.prison import build_prison_block
    text, b = build_prison_block(db_user, section)
    await message.answer(text, reply_markup=b.as_markup())
    return True


@router.message(F.text.in_({"💼 کار", "کار"}))
async def go_work(message: Message, state: FSMContext, db_user):
    await state.clear()
    if await _blocked_by_prison(message, db_user, "کار"):
        return
    from handlers.work import work_menu
    await work_menu(message, db_user)


@router.message(F.text.in_({"🏦 بانک", "بانک"}))
async def go_bank(message: Message, state: FSMContext, session, db_user):
    await state.clear()
    if await _blocked_by_prison(message, db_user, "بانک"):
        return
    from handlers.bank import bank_menu
    await bank_menu(message, session, db_user)


@router.message(F.text.in_({"🎰 کازینو", "کازینو", "شرط بندی", "شرط‌بندی"}))
async def go_casino(message: Message, state: FSMContext, db_user):
    await state.clear()
    if await _blocked_by_prison(message, db_user, "کازینو"):
        return
    from handlers.betting import casino_menu
    await casino_menu(message, db_user)


@router.message(F.text.in_({"🕵️ خلاف", "خلاف"}))
async def go_crime(message: Message, state: FSMContext, db_user):
    await state.clear()
    if await _blocked_by_prison(message, db_user, "خلاف"):
        return
    from handlers.crime import crime_menu
    await crime_menu(message, db_user)


@router.message(F.text.in_({"🏗️ ساخت‌وساز", "ساخت‌وساز", "ساخت وساز", "املاک"}))
async def go_property(message: Message, state: FSMContext, session, db_user):
    await state.clear()
    if await _blocked_by_prison(message, db_user, "ساخت‌وساز"):
        return
    from handlers.property import property_menu
    await property_menu(message, session, db_user)


@router.message(F.text.in_({"🛒 مغازه‌داری", "مغازه‌داری", "مغازه داری", "مغازه"}))
async def go_shop(message: Message, state: FSMContext, session, db_user):
    if await _blocked_by_prison(message, db_user, "مغازه‌داری"):
        await state.clear()
        return
    from handlers.shop import shop_menu
    await shop_menu(message, state, session, db_user)


@router.message(F.text.in_({"📈 بازار مالی", "بازار مالی", "بازار"}))
async def go_market(message: Message, state: FSMContext, db_user):
    await state.clear()
    if await _blocked_by_prison(message, db_user, "بازار مالی"):
        return
    from handlers.market.forex import market_menu
    await market_menu(message)


@router.message(F.text.in_({"🎁 جوایز", "جوایز"}))
async def go_rewards(message: Message, state: FSMContext, db_user):
    await state.clear()
    if await _blocked_by_prison(message, db_user, "جوایز"):
        return
    from handlers.rewards import rewards_menu
    await rewards_menu(message, db_user)


@router.message(F.text.in_({"📊 رتبه‌بندی", "رتبه‌بندی", "رتبه بندی"}))
async def go_leaderboard(message: Message, state: FSMContext, db_user):
    await state.clear()
    if await _blocked_by_prison(message, db_user, "رتبه‌بندی"):
        return
    from handlers.leaderboard import leaderboard_menu
    await leaderboard_menu(message)


@router.message(F.text.in_({"🏙️ کلان‌شهر", "کلان‌شهر", "کلانشهر"}))
async def go_city(message: Message, state: FSMContext, session, db_user):
    await state.clear()
    if await _blocked_by_prison(message, db_user, "کلان‌شهر"):
        return
    if message.chat.type in ("group", "supergroup"):
        from handlers.city.status import city_menu_group
        await city_menu_group(message, session)
    else:
        from handlers.city.status import city_menu_private
        await city_menu_private(message)


@router.message(F.text.in_({"📖 راهنما", "راهنما", "کمک"}))
async def go_help(message: Message, state: FSMContext):
    await state.clear()
    from handlers.help import show_help
    await show_help(message)


@router.message(F.text.in_({"⚙️ تنظیمات", "تنظیمات"}))
async def go_settings(message: Message, state: FSMContext, session, db_user):
    await state.clear()
    from handlers.settings import settings_menu
    await settings_menu(message, session, db_user)


@router.message(F.text.in_({"👤 حساب من", "حساب من"}))
async def go_profile(message: Message, state: FSMContext, db_user):
    await state.clear()
    from handlers.profile import profile_menu
    await profile_menu(message, db_user)


@router.message(F.text.in_({"🏠 پنل اصلی", "پنل اصلی", "پنل"}))
async def go_main(message: Message, state: FSMContext, db_user):
    await state.clear()
    from handlers.start import main_panel
    await main_panel(message, db_user)


@router.message(F.text.in_({"👑 پنل مالک", "پنل مالک"}))
async def go_owner(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id != settings.OWNER_ID:
        return
    from handlers.admin import owner_panel_entry
    await owner_panel_entry(message, state)
