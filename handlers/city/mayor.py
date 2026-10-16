"""
سیستم شهرداری: هر دوره ۷ روزه. ۳ روز پایانی دوره به‌طور کاملاً خودکار وارد فاز
انتخابات میشه (نیازی به دکمه دستی نیست) و بعد از پایان اون ۳ روز، پرآرا شهردار
بعدی میشه. تا وقتی انتخابات تموم نشده، شهردار فعلی همچنان سرکاره.
"""
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import select

from database.models import City, Candidate, Vote, User
from core.texts import header
from config import MAYOR_TERM_DAYS, MAYOR_ELECTION_WINDOW_DAYS
from utils.formatting import fmt_datetime

router = Router(name="city_mayor")


async def _get_city(session, chat_id: int) -> City:
    result = await session.execute(select(City).where(City.chat_id == chat_id))
    return result.scalar_one_or_none()


async def _safe_edit(callback: CallbackQuery, text: str, reply_markup=None):
    """جلوگیری از کرش خوردن دکمه وقتی متن/کیبورد نسبت به قبل فرقی نکرده"""
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        pass


async def ensure_election_state(session, city: City):
    """
    اگه وقتش رسیده باشه (۳ روز پایانی دوره‌ی شهردار فعلی، یا شهر اصلاً شهردار نداره)،
    خودکار وارد فاز انتخابات میشه. هرجا که وضعیت شهرداری/شهر نمایش داده میشه صدا زده میشه
    تا حتی بدون صبر کردن برای زمان‌بند پس‌زمینه، بلافاصله به‌روز باشه.
    """
    if city.election_active:
        return
    now = datetime.utcnow()

    if not city.mayor_telegram_id:
        city.election_active = True
        city.current_round += 1
        city.election_ends_at = now + timedelta(days=MAYOR_ELECTION_WINDOW_DAYS)
        await session.commit()
        return

    if city.mayor_elected_at:
        election_start = city.mayor_elected_at + timedelta(days=MAYOR_TERM_DAYS - MAYOR_ELECTION_WINDOW_DAYS)
        if now >= election_start:
            city.election_active = True
            city.current_round += 1
            city.election_ends_at = city.mayor_elected_at + timedelta(days=MAYOR_TERM_DAYS)
            await session.commit()


def _mayor_text(city: City) -> str:
    text = header("🏛️ شهرداری کلان‌شهر")
    now = datetime.utcnow()

    if city.mayor_telegram_id:
        elected = fmt_datetime(city.mayor_elected_at, "%Y-%m-%d") if city.mayor_elected_at else "-"
        text += (
            f"\n\n👑 شهردار فعلی: <a href='tg://user?id={city.mayor_telegram_id}'>مشاهده پروفایل</a>\n"
            f"📅 تاریخ انتخاب: {elected}\n"
            f"💰 نرخ مالیات تعیین‌شده: {city.tax_rate*100:.1f}٪"
        )
        if not city.election_active and city.mayor_elected_at:
            election_start = city.mayor_elected_at + timedelta(days=MAYOR_TERM_DAYS - MAYOR_ELECTION_WINDOW_DAYS)
            remain = election_start - now
            days = max(remain.days, 0)
            text += f"\n⏳ تا شروع انتخابات بعدی: <b>{days} روز</b>"
    else:
        text += "\n\n😐 این شهر فعلاً شهردار نداره!"

    if city.election_active:
        remain = (city.election_ends_at - now) if city.election_ends_at else None
        days = max(remain.days, 0) if remain else 0
        text += f"\n\n🗳️ <b>انتخاباتی!</b> (تا پایان: {days} روز)"
        if city.mayor_telegram_id:
            text += "\n<i>شهردار فعلی تا پایان انتخابات همچنان سرکاره.</i>"
        text += "\nمی‌تونی کاندید بشی یا رای بدی 👇"

    return text


def _mayor_kb(city: City) -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    if city.election_active:
        b.button(text="🙋 کاندید شو", callback_data="mayor_candidate", style="success")
        b.button(text="🗳️ رای بده", callback_data="mayor_vote_list", style="primary")
        b.button(text="🔙 بازگشت", callback_data="city_back")
        b.adjust(2, 1)
    else:
        b.button(text="🔙 بازگشت", callback_data="city_back")
        b.adjust(1)
    return b


@router.callback_query(F.data == "city_hall")
async def city_hall(callback: CallbackQuery, session):
    city = await _get_city(session, callback.message.chat.id)
    if not city or not city.is_active:
        await callback.answer("❌ این گروه هنوز کلان‌شهر نشده!", show_alert=True)
        return

    await ensure_election_state(session, city)
    await _safe_edit(callback, _mayor_text(city), _mayor_kb(city).as_markup())
    await callback.answer()


@router.callback_query(F.data == "mayor_candidate")
async def become_candidate(callback: CallbackQuery, session, db_user: User):
    city = await _get_city(session, callback.message.chat.id)
    if not city or not city.election_active:
        await callback.answer("❌ الان انتخاباتی در جریان نیست!", show_alert=True)
        return

    existing = (await session.execute(
        select(Candidate).where(
            Candidate.city_id == city.id,
            Candidate.telegram_id == db_user.telegram_id,
            Candidate.election_round == city.current_round,
        )
    )).scalar_one_or_none()
    if existing:
        await callback.answer("✅ تو همین الان کاندیدی!", show_alert=True)
        return

    cand = Candidate(
        city_id=city.id,
        telegram_id=db_user.telegram_id,
        name=db_user.first_name or f"کاربر {db_user.telegram_id}",
        election_round=city.current_round,
    )
    session.add(cand)
    await session.commit()

    await callback.answer("🙋 با موفقیت کاندید شدی!", show_alert=True)


@router.callback_query(F.data == "mayor_vote_list")
async def vote_list(callback: CallbackQuery, session):
    city = await _get_city(session, callback.message.chat.id)
    if not city or not city.election_active:
        await callback.answer("❌ الان انتخاباتی در جریان نیست!", show_alert=True)
        return

    candidates = (await session.execute(
        select(Candidate).where(Candidate.city_id == city.id, Candidate.election_round == city.current_round)
    )).scalars().all()

    if not candidates:
        await callback.answer("😐 هنوز هیچ کاندیدایی ثبت‌نام نکرده!", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    lines = [header("🗳️ لیست کاندیداها")]
    for c in candidates:
        lines.append(f"👤 <b>{c.name}</b> — {c.votes} رای")
        b.button(text=f"🗳️ رای به {c.name}", callback_data=f"mayor_vote:{c.id}")
    b.button(text="🔙 بازگشت", callback_data="city_hall")
    b.adjust(1)

    await _safe_edit(callback, "\n".join(lines), b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("mayor_vote:"))
async def cast_vote(callback: CallbackQuery, session, db_user: User):
    candidate_id = int(callback.data.split(":")[1])
    candidate = await session.get(Candidate, candidate_id)
    if not candidate:
        await callback.answer("❌ کاندیدا پیدا نشد!", show_alert=True)
        return

    city = await session.get(City, candidate.city_id)
    if not city.election_active:
        await callback.answer("❌ انتخابات تموم شده!", show_alert=True)
        return

    existing_vote = (await session.execute(
        select(Vote).where(
            Vote.city_id == city.id,
            Vote.voter_telegram_id == db_user.telegram_id,
            Vote.election_round == city.current_round,
        )
    )).scalar_one_or_none()
    if existing_vote:
        await callback.answer("❌ تو قبلاً رای دادی!", show_alert=True)
        return

    vote = Vote(
        city_id=city.id,
        voter_telegram_id=db_user.telegram_id,
        candidate_id=candidate.id,
        election_round=city.current_round,
    )
    session.add(vote)
    candidate.votes += 1
    await session.commit()

    await callback.answer(f"✅ رای تو به {candidate.name} ثبت شد!", show_alert=True)


@router.callback_query(F.data == "city_back")
async def city_back(callback: CallbackQuery, session):
    from handlers.city.status import build_city_status_text
    from core.keyboards import city_kb

    city = await _get_city(session, callback.message.chat.id)
    text = await build_city_status_text(session, city, bot=callback.bot)
    await _safe_edit(callback, text, city_kb(city.is_active if city else False))
    await callback.answer()
