"""
بخش خلاف کلان‌شهر: جایگزین بخش قدیمی قاچاق.
دو زیربخش داره:
  - خلاف تکی: چند نوع کار خلاف با ریسک/سود متفاوت - قبل از اجرا تایید داره،
    و به‌جای نتیجه‌ی آنی، چند مرحله‌ی تعلیق (روایت زنده) داره تا نتیجه لو بره.
  - خلاف گروهی: سرقت بزرگ بانک که نیاز به تیم داره (فقط داخل گروه)
"""
import asyncio
import random
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from database.models import User
from database.engine import async_session
from core.texts import header, NOT_ENOUGH_MONEY, IN_PRISON_TEXT, INVALID_AMOUNT_TEXT
from core.keyboards import back_kb, crime_kb, confirm_kb
from core.economy import log_transaction, is_in_prison
from core.reply_guard import set_prompt, check_reply
from config import PRISON_BASE_SECONDS, HEIST_JOIN_SECONDS, HEIST_MIN_PARTICIPANTS
from utils.formatting import fmt_money, fmt_seconds, parse_amount

router = Router(name="crime")


class CrimeStates(StatesGroup):
    waiting_amount = State()
    confirm_amount = State()


SOLO_CRIMES = {
    "crime_pickpocket": {
        "name": "🟢 🖐️ جیب‌بری", "catch_chance": 0.20, "multiplier": 1.6,
        "min": 1000, "prison_range": (0.5, 1.0),
        "desc": "کم‌ریسک‌ترین کار خلاف. سود کم ولی امن‌تره.",
        "steps": [
            "🚶 داری تو شلوغی بازار قدم می‌زنی و دنبال طعمه می‌گردی...",
            "👀 یه هدف خوب پیدا کردی، آروم آروم نزدیک میشی...",
            "🖐️ دستت رو بردی سمت جیبش...",
        ],
    },
    "crime_smuggle": {
        "name": "🟠 🚚 قاچاق کالا", "catch_chance": 0.35, "multiplier": 2.4,
        "min": 3000, "prison_range": (1.0, 2.5),
        "desc": "ریسک متوسط، سود خوب. کلاسیک‌ترین خلاف کلان‌شهر!",
        "steps": [
            "🚚 بار رو تو وانت جاساز کردی و راه افتادی...",
            "🛣️ داری از جاده‌ی فرعی رد میشی که کمتر گشت می‌زنن...",
            "🚧 یه ایست بازرسی جلوته! باید تصمیم بگیری چیکار کنی...",
        ],
    },
    "crime_burglary": {
        "name": "🟠 🏚️ دزدی از خونه", "catch_chance": 0.45, "multiplier": 3.0,
        "min": 5000, "prison_range": (1.5, 3.0),
        "desc": "ریسک بالا، ولی غنیمت بهتر.",
        "steps": [
            "🌙 نصفه‌شبه، رفتی جلوی یه خونه‌ی خالی از سکنه...",
            "🔓 قفل در رو باز کردی و آروم رفتی تو...",
            "💍 داری تو کمد دنبال چیزای باارزش می‌گردی...",
        ],
    },
    "crime_hack": {
        "name": "🔴 💻 هک حساب بانکی", "catch_chance": 0.55, "multiplier": 4.5,
        "min": 8000, "prison_range": (2.0, 4.0),
        "desc": "خطرناک‌ترین کار خلاف؛ اگه جواب بده، رئیس خلافکارای شهری!",
        "steps": [
            "💻 نشستی پشت لپ‌تاپ و داری وارد سیستم بانک میشی...",
            "🔐 فایروال اولش رو دور زدی، یه لایه‌ی امنیتی دیگه مونده...",
            "⏱️ داری کد نهایی رو اجرا می‌کنی، هر لحظه ممکنه ردت بزنن...",
        ],
    },
}

REVEAL_DELAY = 1.6  # ثانیه بین هر مرحله از روایت

HEIST_REWARD_PER_PERSON = (10_000, 25_000)
HEIST_PRISON_SECONDS = (2000, 4500)
HEIST_SUCCESS_BASE = 0.45

# state درون‌حافظه‌ای برای سرقت‌های گروهی فعال هر گروه
active_heists: dict[int, dict] = {}


@router.message(F.text.in_({"🕵️ خلاف", "خلاف"}))
async def crime_menu(message: Message, db_user: User):
    if is_in_prison(db_user):
        remain = (db_user.prison_until - datetime.utcnow()).total_seconds()
        await message.answer(IN_PRISON_TEXT.format(time=fmt_seconds(remain), reason=db_user.prison_reason or "نامشخص"))
        return

    text = f"{header('🕵️ خلاف')}\n\n⚠️ همه‌ی این کارها ریسک زندان دارن. تنها یا با تیم؟"
    await message.answer(text, reply_markup=crime_kb())


# ---------------- خلاف تکی ----------------

@router.callback_query(F.data == "crime_solo_menu")
async def crime_solo_menu(callback: CallbackQuery):
    b = InlineKeyboardBuilder()
    lines = [header("🕵️‍♂️ خلاف تکی"), ""]
    for key, c in SOLO_CRIMES.items():
        lines.append(f"{c['name']} — گیر افتادن {int(c['catch_chance']*100)}٪ | x{c['multiplier']}")
        b.button(text=c["name"], callback_data=key)
    b.button(text="🔙 بازگشت", callback_data="crime_back")
    b.adjust(1)
    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.in_(SOLO_CRIMES.keys()))
async def solo_crime_start(callback: CallbackQuery, state: FSMContext, db_user: User):
    if is_in_prison(db_user):
        remain = (db_user.prison_until - datetime.utcnow()).total_seconds()
        await callback.answer(f"🚔 تو زندانی! {fmt_seconds(remain)} مونده.", show_alert=True)
        return

    crime = SOLO_CRIMES[callback.data]
    await state.set_state(CrimeStates.waiting_amount)
    await callback.message.edit_text(
        f"{header(crime['name'])}\n\n"
        f"{crime['desc']}\n\n"
        f"⚠️ گیر افتادن: {int(crime['catch_chance']*100)}٪ | سود: x{crime['multiplier']} | حداقل: {fmt_money(crime['min'])}\n\n"
        f"↩️ رو همین پیام ریپلای کن و بگو چقدر سرمایه میذاری",
        reply_markup=back_kb("crime_back")
    )
    await set_prompt(state, callback.message.message_id, crime=callback.data)
    await callback.answer()


@router.message(CrimeStates.waiting_amount)
async def solo_crime_amount_ask(message: Message, state: FSMContext, db_user: User):
    if not await check_reply(message, state):
        return
    data = await state.get_data()
    crime_key = data.get("crime")
    crime = SOLO_CRIMES.get(crime_key)
    if not crime:
        await state.clear()
        return

    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(INVALID_AMOUNT_TEXT)
        return
    if amount < crime["min"]:
        await message.answer(f"❌ حداقل سرمایه لازم: <code>{fmt_money(crime['min'])}</code> تومان")
        return
    if amount > db_user.cash:
        await message.answer(NOT_ENOUGH_MONEY.format(cash=fmt_money(db_user.cash)))
        return

    await state.update_data(amount=amount)
    await state.set_state(CrimeStates.confirm_amount)
    potential_profit = round(amount * crime["multiplier"]) - amount
    await message.answer(
        f"{header('⚠️ تایید نهایی')}\n\n"
        f"{crime['name']}\n"
        f"💰 سرمایه: <code>{fmt_money(amount)}</code>\n"
        f"🎯 سود احتمالی اگه موفق شی: <code>+{fmt_money(potential_profit)}</code>\n"
        f"🚔 احتمال گیر افتادن: <b>{int(crime['catch_chance']*100)}٪</b>\n\n"
        f"مطمئنی می‌خوای این ریسک رو بکنی؟",
        reply_markup=confirm_kb("crime_confirm", "crime_cancel")
    )


@router.callback_query(F.data == "crime_confirm", CrimeStates.confirm_amount)
async def solo_crime_confirm(callback: CallbackQuery, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    crime_key = data.get("crime")
    amount = data.get("amount")
    crime = SOLO_CRIMES.get(crime_key)
    if not crime or amount is None:
        await callback.answer("❌ منقضی شده، دوباره امتحان کن.", show_alert=True)
        await state.clear()
        return
    if amount > db_user.cash:
        await callback.answer("❌ پولت کافی نیست!", show_alert=True)
        await state.clear()
        return

    await state.clear()
    await callback.answer("🎬 شروع شد...")

    # ---- روایت زنده: چند مرحله تعلیق قبل از فاش شدن نتیجه ----
    msg = callback.message
    await msg.edit_text(f"{header(crime['name'])}\n\n{crime['steps'][0]}")
    for step in crime["steps"][1:]:
        await asyncio.sleep(REVEAL_DELAY)
        try:
            await msg.edit_text(f"{header(crime['name'])}\n\n{step}")
        except Exception:
            pass
    await asyncio.sleep(REVEAL_DELAY)

    caught = random.random() < crime["catch_chance"]

    if caught:
        db_user.cash -= amount
        prison_seconds = PRISON_BASE_SECONDS * random.uniform(*crime["prison_range"])
        db_user.prison_until = datetime.utcnow() + timedelta(seconds=prison_seconds)
        db_user.prison_reason = crime["name"]
        await log_transaction(session, db_user.id, "crime_caught", -amount, f"مصادره اموال - {crime['name']}")
        await session.commit()

        caught_lines = [
            "🚨 یهو یه دست از پشت گرفتت! پلیس بود.",
            "🚔 صدای آژیر پیچید تو کوچه، فرصت فرار نداشتی...",
            "👮 یه گشت گمرکی درست همون لحظه رسید.",
        ]
        await msg.edit_text(
            f"{header('🚔 گیر افتادی!')}\n\n"
            f"{random.choice(caught_lines)}\n\n"
            f"💸 <code>-{fmt_money(amount)}</code> | ⏳ زندان: <code>{fmt_seconds(prison_seconds)}</code>\n"
            f"وثیقه از «🏙️ کلان‌شهر → زندان»"
        )
    else:
        profit = round(amount * crime["multiplier"]) - amount
        db_user.cash += profit
        await log_transaction(session, db_user.id, "crime_success", profit, f"سود خلاف موفق - {crime['name']}")
        await session.commit()

        success_lines = [
            "😎 بی‌سروصدا زدی به چاک و کسی نفهمید.",
            "🔥 عملیات تمیز و بی‌نقص پیش رفت!",
            "💨 غیب شدی قبل از اینکه کسی بفهمه چی شد.",
        ]
        await msg.edit_text(
            f"{header('✅ موفق شدی!')}\n\n"
            f"{random.choice(success_lines)}\n\n"
            f"💰 <code>+{fmt_money(profit)}</code> | 💵 موجودی: <code>{fmt_money(db_user.cash)}</code>"
        )


@router.callback_query(F.data == "crime_cancel")
async def solo_crime_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    text = f"{header('🕵️ خلاف')}\n\n❌ منصرف شدی. عاقلانه بود شاید!"
    await callback.message.edit_text(text, reply_markup=crime_kb())
    await callback.answer()


# ---------------- خلاف گروهی ----------------

@router.callback_query(F.data == "crime_group_menu")
async def crime_group_menu(callback: CallbackQuery):
    if callback.message.chat.type not in ("group", "supergroup"):
        await callback.answer("❌ خلاف گروهی فقط داخل گروه‌ها فعاله!", show_alert=True)
        return

    chat_id = callback.message.chat.id
    b = InlineKeyboardBuilder()
    if chat_id in active_heists:
        n = len(active_heists[chat_id]["participants"])
        text = f"{header('👥 سرقت بزرگ بانک')}\n\n⏳ یه سرقت در جریانه ({n} نفر). از پیام سرقت وارد تیم شو."
    else:
        text = (
            f"{header('👥 سرقت بزرگ بانک')}\n\n"
            f"حداقل {HEIST_MIN_PARTICIPANTS} نفر، {HEIST_JOIN_SECONDS} ثانیه فرصت.\n"
            f"✅ موفق = غنیمت برای همه | 🚔 گیر افتادن = زندان برای همه"
        )
        b.button(text="🏦 شروع سرقت", callback_data="crime_group_start", style="success")
    b.button(text="🔙 بازگشت", callback_data="crime_back")
    b.adjust(1)
    await callback.message.edit_text(text, reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data == "crime_group_start")
async def crime_group_start(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id in active_heists:
        await callback.answer("❌ همین الان یه سرقت گروهی در جریانه!", show_alert=True)
        return

    active_heists[chat_id] = {
        "participants": {callback.from_user.id: callback.from_user.first_name or "کاربر"},
    }

    b = InlineKeyboardBuilder()
    b.button(text="ورود به تیم", callback_data="crime_group_join", style="success")
    text = (
        f"{header('🏦 سرقت بزرگ بانک')}\n\n"
        f"👤 <b>{callback.from_user.first_name}</b> شروع کرد | حداقل {HEIST_MIN_PARTICIPANTS} نفر | {HEIST_JOIN_SECONDS} ثانیه"
    )
    msg = await callback.message.answer(text, reply_markup=b.as_markup())
    active_heists[chat_id]["message_id"] = msg.message_id
    asyncio.create_task(_resolve_heist_later(callback.bot, chat_id))
    await callback.answer("🟢 تیم سرقت راه‌اندازی شد!")


@router.callback_query(F.data == "crime_group_join")
async def crime_group_join(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    heist = active_heists.get(chat_id)
    if not heist:
        await callback.answer("❌ سرقتی در جریان نیست یا زمانش تموم شده!", show_alert=True)
        return
    if callback.from_user.id in heist["participants"]:
        await callback.answer("✅ تو همین الان تو تیمی!", show_alert=True)
        return

    heist["participants"][callback.from_user.id] = callback.from_user.first_name or "کاربر"
    await callback.answer(f"🟢 وارد تیم شدی! نفرات فعلی: {len(heist['participants'])}", show_alert=True)


async def _resolve_heist_later(bot, chat_id: int):
    await asyncio.sleep(HEIST_JOIN_SECONDS)
    heist = active_heists.pop(chat_id, None)
    if not heist:
        return

    participants = heist["participants"]
    async with async_session() as session:
        if len(participants) < HEIST_MIN_PARTICIPANTS:
            await bot.send_message(
                chat_id,
                f"😐 <b>سرقت گروهی لغو شد!</b>\nحداقل {HEIST_MIN_PARTICIPANTS} نفر لازم بود ولی فقط "
                f"{len(participants)} نفر ملحق شدن.",
                parse_mode="HTML"
            )
            return

        success_chance = min(0.85, HEIST_SUCCESS_BASE + 0.05 * len(participants))
        success = random.random() < success_chance
        lines = [header("🏦 نتیجه سرقت بزرگ بانک"), ""]

        if success:
            lines.append(f"✅ تیم {len(participants)} نفره موفق شد ضربه بزنه! 💰\n")
            for tg_id, name in participants.items():
                reward = random.randint(*HEIST_REWARD_PER_PERSON)
                result = await session.execute(select(User).where(User.telegram_id == tg_id))
                user = result.scalar_one_or_none()
                if user:
                    user.cash += reward
                    await log_transaction(session, user.id, "heist_success", reward, "سهم از سرقت بزرگ بانک")
                lines.append(f"💵 {name}: +<code>{fmt_money(reward)}</code> تومان")
            await session.commit()
        else:
            lines.append("🚔 <b>پلیس همه رو گرفت! کل تیم رفت زندان.</b>\n")
            for tg_id, name in participants.items():
                prison_sec = random.randint(*HEIST_PRISON_SECONDS)
                result = await session.execute(select(User).where(User.telegram_id == tg_id))
                user = result.scalar_one_or_none()
                if user:
                    user.prison_until = datetime.utcnow() + timedelta(seconds=prison_sec)
                    user.prison_reason = "سرقت گروهی ناموفق"
                lines.append(f"🚔 {name}: {fmt_seconds(prison_sec)} زندان")
            await session.commit()

    await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")


@router.callback_query(F.data == "crime_back")
async def crime_back(callback: CallbackQuery, db_user: User):
    text = f"{header('🕵️ خلاف')}\n\n⚠️ همه‌ی این کارها ریسک زندان دارن. تنها یا با تیم؟"
    await callback.message.edit_text(text, reply_markup=crime_kb())
    await callback.answer()
