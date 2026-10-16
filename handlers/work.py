"""
سیستم کار: انتخاب شغل، کار کردن، ارتقای شغل
عوض کردن شغلی که از قبل داری تایید داره (چون کول‌داون رو ریست می‌کنه).
"""
import random
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database.models import User
from config import JOBS
from core.texts import header, IN_PRISON_TEXT, COOLDOWN_TEXT
from core.economy import add_cash, add_xp, is_in_prison
from core.auto_revert import schedule_revert
from core.keyboards import confirm_kb
from utils.formatting import fmt_money, fmt_seconds

router = Router(name="work")

WORK_SUCCESS_MESSAGES = [
    "💪 عالی کار کردی و پول خوبی گرفتی!",
    "🔥 امروز روز خوبی برای کار بود!",
    "✅ کارت رو با موفقیت تموم کردی!",
    "🎉 رئیس ازت راضی بود و پاداش هم گرفتی!",
    "⚡ سریع و حرفه‌ای! دستمزدت رو بگیر.",
]


def jobs_kb() -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    for name, info in JOBS.items():
        b.button(text=f"{name} (لول {info['level']}+)", callback_data=f"job_select:{name}", style="success")
    b.adjust(1)
    return b.as_markup()


def _work_menu_text_kb(db_user: User):
    """متن و کیبورد منوی کار - جدا شده تا هم توسط work_menu هم برای بازگشت خودکار بعد از کار استفاده بشه"""
    info = JOBS[db_user.job]
    now = datetime.utcnow()
    can_work = True
    remain_text = ""
    if db_user.last_work:
        elapsed = (now - db_user.last_work).total_seconds()
        if elapsed < info["cooldown"]:
            can_work = False
            remain_text = fmt_seconds(info["cooldown"] - elapsed)

    text = (
        f"{header('💼 محل کار')}\n\n"
        f"شغل فعلی: <b>{db_user.job}</b> (لول {db_user.job_level})\n"
        f"حقوق پایه: <code>{fmt_money(info['salary'])}</code> تومان\n\n"
    )
    b = InlineKeyboardBuilder()
    if can_work:
        text += "✅ آماده کاری! دکمه زیر رو بزن."
        b.button(text="🔨 شروع کار", callback_data="work_do", style="success")
        b.button(text="🔄 تغییر شغل", callback_data="work_change")
        b.adjust(1)
    else:
        text += COOLDOWN_TEXT.format(time=remain_text)
        b.button(text="🔄 تغییر شغل", callback_data="work_change")
    return text, b.as_markup()


@router.message(F.text.in_({"💼 کار", "کار"}))
async def work_menu(message: Message, db_user: User):
    if is_in_prison(db_user):
        remain = (db_user.prison_until - datetime.utcnow()).total_seconds()
        await message.answer(IN_PRISON_TEXT.format(time=fmt_seconds(remain), reason=db_user.prison_reason or "نامشخص"))
        return

    if not db_user.job:
        text = (
            f"{header('💼 انتخاب شغل')}\n\n"
            "هنوز شغلی انتخاب نکردی! یکی از مشاغل زیر رو انتخاب کن:\n"
            "(هرچی سطحت بالاتر باشه به مشاغل بهتر دسترسی داری)"
        )
        await message.answer(text, reply_markup=jobs_kb())
        return

    text, markup = _work_menu_text_kb(db_user)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("job_select:"))
async def job_select(callback: CallbackQuery, session, db_user: User):
    job_name = callback.data.split(":", 1)[1]
    info = JOBS.get(job_name)
    if not info:
        await callback.answer("شغل نامعتبره!", show_alert=True)
        return
    if db_user.level < info["level"]:
        await callback.answer(f"❌ برای این شغل حداقل باید سطح {info['level']} باشی!", show_alert=True)
        return

    if db_user.job == job_name:
        await callback.answer("✅ همین الان همین شغل رو داری! کول‌داونت هم دست‌نخورده باقی می‌مونه.", show_alert=True)
        return

    # اگه از قبل شغل داشته باشه، عوض کردنش کول‌داون رو ریست می‌کنه - پس تایید بگیر
    if db_user.job:
        await callback.message.edit_text(
            f"{header('⚠️ تایید تغییر شغل')}\n\n"
            f"شغل فعلی: <b>{db_user.job}</b>\n"
            f"شغل جدید: <b>{job_name}</b>\n\n"
            f"⚠️ با این کار کول‌داون فعلیت پاک میشه و سابقه‌ی لول شغلیت از صفر شروع میشه.\n"
            f"مطمئنی؟",
            reply_markup=confirm_kb(f"job_switch_confirm:{job_name}", "work_change")
        )
        await callback.answer()
        return

    db_user.job = job_name
    db_user.job_level = 1
    db_user.last_work = None
    await session.commit()

    await callback.message.edit_text(
        f"{header('✅ استخدام شدی!')}\n\nشغل جدید: <b>{job_name}</b>\nحالا از منوی «💼 کار» شروع کن!"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("job_switch_confirm:"))
async def job_switch_confirm(callback: CallbackQuery, session, db_user: User):
    job_name = callback.data.split(":", 1)[1]
    info = JOBS.get(job_name)
    if not info or db_user.level < info["level"]:
        await callback.answer("❌ این شغل دیگه در دسترس نیست!", show_alert=True)
        return

    db_user.job = job_name
    db_user.job_level = 1
    db_user.last_work = None
    await session.commit()

    await callback.message.edit_text(
        f"{header('✅ شغل عوض شد!')}\n\nشغل جدید: <b>{job_name}</b>\nحالا از منوی «💼 کار» شروع کن!"
    )
    await callback.answer("✅ شغلت عوض شد!")


@router.callback_query(F.data == "work_change")
async def work_change(callback: CallbackQuery):
    await callback.message.edit_text(
        f"{header('💼 انتخاب شغل جدید')}\n\n"
        f"⚠️ توجه: اگه شغل جدید انتخاب کنی، سابقه‌ی کول‌داون قبلی پاک میشه و از صفر شروع میشه.\n"
        f"ولی انتخاب دوباره‌ی همون شغل فعلی، کول‌داونت رو ریست نمی‌کنه.",
        reply_markup=jobs_kb()
    )
    await callback.answer()


@router.callback_query(F.data == "work_do")
async def work_do(callback: CallbackQuery, session, db_user: User):
    if is_in_prison(db_user):
        await callback.answer("🚔 تو زندانی نمیتونی کار کنی!", show_alert=True)
        return

    info = JOBS.get(db_user.job)
    if not info:
        await callback.answer("اول باید شغل انتخاب کنی!", show_alert=True)
        return

    now = datetime.utcnow()
    if db_user.last_work:
        elapsed = (now - db_user.last_work).total_seconds()
        if elapsed < info["cooldown"]:
            remain = fmt_seconds(info["cooldown"] - elapsed)
            await callback.answer(f"⏳ هنوز {remain} مونده!", show_alert=True)
            return

    base = info["salary"] * (1 + (db_user.job_level - 1) * 0.15)
    earned = round(base * random.uniform(0.9, 1.25))

    db_user.last_work = now
    await add_cash(session, db_user, earned, f"دستمزد شغل {db_user.job}")
    level_result = await add_xp(session, db_user, random.randint(15, 35))

    msg = (
        f"{header('💼 نتیجه کار')}\n\n"
        f"{random.choice(WORK_SUCCESS_MESSAGES)}\n\n"
        f"💰 دستمزد: <code>{fmt_money(earned)}</code> تومان\n"
        f"💵 موجودی جدید: <code>{fmt_money(db_user.cash)}</code> تومان"
    )
    if level_result["leveled_up"]:
        msg += f"\n\n🎉 <b>تبریک! سطحت رفت بالا! سطح جدید: {level_result['new_level']}</b>"

    await callback.message.edit_text(msg)
    await callback.answer("✅ کار انجام شد!")

    revert_text, revert_kb = _work_menu_text_kb(db_user)
    schedule_revert(callback.message, revert_text, revert_kb)
