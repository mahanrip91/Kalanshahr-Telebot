"""
کازینوی کلان‌شهر - نسخه کامل با بازی‌های امتیازی و حالت گروهی

🎲 تاس: تکی → شرط رو زوج/فرد/عدد خاص؛ گروهی (۲/۳ نفره) → بیشترین عدد استخر رو می‌بره
🎰 اسلات، 🎳 بولینگ، 🎯 دارت، ⚽ فوتبال، 🏀 بسکتبال: تکی → امتیازی (ضریب ۰ تا x۳ با گام
نیم‌واحد بر اساس عددی که تلگرام برمی‌گردونه)؛ گروهی → بیشترین عدد استخر مشترک رو می‌بره
🪙 سکه، 🎡 رولت: بدون تغییر (بدون ریپلای ایموجی، بدون حالت گروهی)

حالت گروهی فقط داخل گروه‌ها فعاله: یه نفر شروع می‌کنه و مبلغ رو تعیین می‌کنه، بقیه با
همون مبلغ می‌پیوندن، همه ایموجی رو می‌فرستن و رو پیام مشترک ریپلای می‌کنن، بیشترین
عدد کل استخر (مجموع شرط همه) رو می‌بره.
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
from core.keyboards import casino_kb, back_kb
from core.texts import header, IN_PRISON_TEXT, NOT_ENOUGH_MONEY, INVALID_AMOUNT_TEXT
from core.economy import add_xp, log_transaction, is_in_prison
from core.reply_guard import set_prompt, check_reply
from config import BET_MIN, BET_MAX_DAILY, BET_COOLDOWN, DICE_REPLY_SECONDS, CASINO_MULTIPLAYER_JOIN_SECONDS
from utils.formatting import fmt_money, fmt_seconds, parse_amount

router = Router(name="casino")


class CasinoStates(StatesGroup):
    waiting_amount = State()             # مبلغ شرط تکی (بازی‌های امتیازی)
    waiting_dice_reply = State()         # منتظر ریپلای ایموجی تکی
    waiting_text_bet = State()           # سکه / رولت
    waiting_dice_type_amount = State()   # مبلغ شرط تاس تکی (بعد از انتخاب نوع شرط)
    waiting_mp_amount = State()          # مبلغ شرط گروهی (شروع‌کننده)


GAMES = {
    "casino_dice":     {"emoji": "🎲", "name": "🎲 تاس شانس",    "max": 6},
    "casino_slot":     {"emoji": "🎰", "name": "🎰 اسلات‌ماشین", "max": 64},
    "casino_bowling":  {"emoji": "🎳", "name": "🎳 بولینگ",      "max": 6},
    "casino_dart":     {"emoji": "🎯", "name": "🎯 دارت",        "max": 6},
    "casino_football": {"emoji": "⚽", "name": "⚽ فوتبال",      "max": 5},
    "casino_basket":   {"emoji": "🏀", "name": "🏀 بسکتبال",     "max": 5},
}

TEXT_GAMES = {
    "casino_coin": {"name": "🪙 شیر یا خط", "win_chance": 0.48, "multiplier": 1.9},
    "casino_roulette": {"name": "🎡 رولت", "win_chance": 0.35, "multiplier": 2.5},
}

BIG_WIN_THRESHOLD = 30000

DICE_BET_LABELS = {"even": "زوج", "odd": "فرد"}
DICE_BET_LABELS.update({f"num:{n}": f"عدد {n}" for n in range(1, 7)})

# بازی‌های گروهی فعال هر گروه: chat_id -> dict
active_group_games: dict[int, dict] = {}


# ==================== توابع کمکی ====================

def _reset_daily_if_needed(user: User):
    today = datetime.utcnow().date()
    if not user.bet_reset_date or user.bet_reset_date.date() != today:
        user.bet_today_total = 0
        user.bet_reset_date = datetime.utcnow()


def _validate_bet(amount, db_user: User):
    """برمیگردونه پیام خطا یا None اگه اوکی بود"""
    if amount is None:
        return INVALID_AMOUNT_TEXT
    if amount < BET_MIN:
        return f"❌ حداقل شرط <code>{fmt_money(BET_MIN)}</code> تومانه."
    if amount > db_user.cash:
        return NOT_ENOUGH_MONEY.format(cash=fmt_money(db_user.cash))
    _reset_daily_if_needed(db_user)
    if db_user.bet_today_total + amount > BET_MAX_DAILY:
        remain = BET_MAX_DAILY - db_user.bet_today_total
        return f"❌ سقف شرط روزانه پر شده. باقی‌مانده: <code>{fmt_money(remain)}</code>"
    return None


def _cooldown_remaining(db_user: User) -> float:
    if not db_user.last_bet:
        return 0
    elapsed = (datetime.utcnow() - db_user.last_bet).total_seconds()
    return max(0, BET_COOLDOWN - elapsed)


def _slot_reels(value: int):
    """مقدار ۱ تا ۶۴ ایموجی اسلات تلگرام رو به ۳ حلقه (هرکدوم ۰ تا ۳) تجزیه می‌کنه"""
    v = value - 1
    return v % 4, (v // 4) % 4, (v // 16) % 4


def _score_multiplier(game_key: str, value: int) -> float:
    """ضریب ۰ تا x۳ (گام نیم‌واحد) بر اساس امتیازی که تلگرام برای ایموجی برمی‌گردونه"""
    if game_key == "casino_slot":
        r1, r2, r3 = _slot_reels(value)
        if r1 == r2 == r3:
            return 3.0
        if r1 == r2 or r2 == r3 or r1 == r3:
            return 1.5
        return 0.0

    max_value = GAMES[game_key]["max"]
    raw = (value - 1) / (max_value - 1) * 3.0
    return round(raw * 2) / 2


def _dice_bet_result(bet_type: str, value: int):
    """برمیگردونه (برد؟, ضریب)"""
    if bet_type in ("even", "odd"):
        is_even = (value % 2 == 0)
        won = (bet_type == "even") == is_even
        return won, (2.0 if won else 0.0)
    num = int(bet_type.split(":")[1])
    won = (num == value)
    return won, (3.0 if won else 0.0)


# ==================== منوی اصلی کازینو ====================

@router.message(F.text.in_({"🎰 کازینو", "کازینو", "شرط بندی", "شرط‌بندی"}))
async def casino_menu(message: Message, db_user: User):
    if is_in_prison(db_user):
        remain = (db_user.prison_until - datetime.utcnow()).total_seconds()
        await message.answer(IN_PRISON_TEXT.format(time=fmt_seconds(remain), reason=db_user.prison_reason or "نامشخص"))
        return

    _reset_daily_if_needed(db_user)
    text = (
        f"{header('🎰 کازینو')}\n\n"
        f"💵 <code>{fmt_money(db_user.cash)}</code> | امروز: <code>{fmt_money(db_user.bet_today_total)}</code>/<code>{fmt_money(BET_MAX_DAILY)}</code>\n\n"
        f"یه بازی انتخاب کن 👇"
    )
    await message.answer(text, reply_markup=casino_kb())


# ==================== انتخاب بازی → انتخاب حالت (تکی/۲نفره/۳نفره) ====================

def _mode_kb(game_key: str, is_group: bool) -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.button(text="👤 تکی", callback_data=f"cg_mode:{game_key}:solo", style="success")
    if is_group:
        b.button(text="👥 ۲ نفره", callback_data=f"cg_mode:{game_key}:2", style="primary")
        b.button(text="👥 ۳ نفره", callback_data=f"cg_mode:{game_key}:3", style="primary")
    b.button(text="🔙 بازگشت", callback_data="casino_back")
    b.adjust(1)
    return b


@router.callback_query(F.data.in_(GAMES.keys()))
async def choose_game(callback: CallbackQuery, db_user: User):
    if is_in_prison(db_user):
        await callback.answer("🚔 تو زندانی نمیتونی شرط ببندی!", show_alert=True)
        return

    remain = _cooldown_remaining(db_user)
    if remain:
        await callback.answer(f"⏳ {fmt_seconds(remain)} دیگه صبر کن!", show_alert=True)
        return

    game = GAMES[callback.data]
    game_name = game["name"]
    is_group = callback.message.chat.type in ("group", "supergroup")

    text = f"{header(game_name)}\n\n💰 حداقل شرط: <code>{fmt_money(BET_MIN)}</code>\n\nمی‌خوای تکی بازی کنی یا با بقیه‌ی گروه؟"
    if not is_group:
        text += "\n\n<i>حالت گروهی فقط داخل گروه‌ها فعاله.</i>"

    await callback.message.edit_text(text, reply_markup=_mode_kb(callback.data, is_group).as_markup())
    await callback.answer()


def _dice_type_kb() -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.button(text="⚪️ زوج", callback_data="dice_bet:even", style="primary")
    b.button(text="⚫️ فرد", callback_data="dice_bet:odd", style="primary")
    for n in range(1, 7):
        b.button(text=f"🎯 {n}", callback_data=f"dice_bet:num:{n}")
    b.button(text="🔙 بازگشت", callback_data="casino_back")
    b.adjust(2, 3, 3, 1)
    return b


@router.callback_query(F.data.startswith("cg_mode:"))
async def cg_mode_chosen(callback: CallbackQuery, state: FSMContext):
    _, game_key, mode = callback.data.split(":")
    game = GAMES[game_key]
    game_name = game["name"]

    if mode == "solo":
        if game_key == "casino_dice":
            text = (
                f"{header('🎲 تاس شانس - تکی')}\n\n"
                f"روی زوج، فرد یا یه عدد خاص شرط ببند:\n"
                f"• زوج/فرد درست دربیاد: <b>x2</b>\n"
                f"• عدد دقیق درست دربیاد: <b>x3</b>"
            )
            await callback.message.edit_text(text, reply_markup=_dice_type_kb().as_markup())
        else:
            await state.set_state(CasinoStates.waiting_amount)
            await callback.message.edit_text(
                f"{header(game_name)}\n\n"
                f"💰 حداقل: <code>{fmt_money(BET_MIN)}</code> | ضریب: ۰ تا x۳ (بسته به امتیاز)\n\n"
                f"↩️ رو همین پیام ریپلای کن و بگو چقدر شرط می‌بندی",
                reply_markup=back_kb("casino_back")
            )
            await set_prompt(state, callback.message.message_id, game=game_key)
        await callback.answer()
        return

    # ---------- حالت گروهی ----------
    if callback.message.chat.type not in ("group", "supergroup"):
        await callback.answer("❌ حالت گروهی فقط داخل گروه‌ها فعاله!", show_alert=True)
        return
    if callback.message.chat.id in active_group_games:
        await callback.answer("❌ همین الان یه بازی گروهی تو این چت در جریانه!", show_alert=True)
        return

    players_needed = int(mode)
    await state.set_state(CasinoStates.waiting_mp_amount)
    await callback.message.edit_text(
        f"{header(game_name + ' - ' + str(players_needed) + ' نفره')}\n\n"
        f"💰 حداقل شرط: <code>{fmt_money(BET_MIN)}</code>\n\n"
        f"↩️ رو همین پیام ریپلای کن و بگو چقدر می‌خوای شرط بذاری (بقیه هم با همین مبلغ وارد میشن)",
        reply_markup=back_kb("casino_back")
    )
    await set_prompt(state, callback.message.message_id, game=game_key, players_needed=players_needed)
    await callback.answer()


@router.callback_query(F.data.startswith("dice_bet:"))
async def dice_bet_type_chosen(callback: CallbackQuery, state: FSMContext):
    bet_type = callback.data.split(":", 1)[1]
    label = DICE_BET_LABELS.get(bet_type, bet_type)
    await state.set_state(CasinoStates.waiting_dice_type_amount)
    await callback.message.edit_text(
        f"{header('🎲 تاس شانس')}\n\n"
        f"شرط تو: <b>{label}</b>\n"
        f"💰 حداقل: <code>{fmt_money(BET_MIN)}</code>\n\n"
        f"↩️ رو همین پیام ریپلای کن و بگو چقدر شرط می‌بندی",
        reply_markup=back_kb("casino_back")
    )
    await set_prompt(state, callback.message.message_id, game="casino_dice", bet_type=bet_type)
    await callback.answer()


# ==================== دریافت مبلغ (تکی) ====================

@router.message(CasinoStates.waiting_dice_type_amount)
async def dice_type_amount(message: Message, state: FSMContext, db_user: User):
    if not await check_reply(message, state):
        return
    amount = parse_amount(message.text)
    err = _validate_bet(amount, db_user)
    if err:
        await message.answer(err)
        return

    data = await state.get_data()
    bet_type = data["bet_type"]
    game = GAMES["casino_dice"]
    label = DICE_BET_LABELS.get(bet_type, bet_type)

    prompt = await message.answer(
        f"{header(game['name'])}\n\n"
        f"💰 <code>{fmt_money(amount)}</code> | شرط: <b>{label}</b> | ⏳ {DICE_REPLY_SECONDS} ثانیه\n\n"
        f"این رو بزن تا کپی شه، بفرستش و <b>رو همین پیام ریپلای کن</b>:\n\n"
        f"<code>{game['emoji']}</code>"
    )
    await state.update_data(
        amount=amount,
        prompt_id=prompt.message_id,
        expires_at=(datetime.utcnow() + timedelta(seconds=DICE_REPLY_SECONDS)).isoformat(),
    )
    await state.set_state(CasinoStates.waiting_dice_reply)


@router.message(CasinoStates.waiting_amount)
async def score_bet_amount(message: Message, state: FSMContext, db_user: User):
    if not await check_reply(message, state):
        return
    amount = parse_amount(message.text)
    err = _validate_bet(amount, db_user)
    if err:
        await message.answer(err)
        return

    data = await state.get_data()
    game_key = data["game"]
    game = GAMES[game_key]

    prompt = await message.answer(
        f"{header(game['name'])}\n\n"
        f"💰 <code>{fmt_money(amount)}</code> | ⏳ {DICE_REPLY_SECONDS} ثانیه\n\n"
        f"این رو بزن تا کپی شه، بفرستش و <b>رو همین پیام ریپلای کن</b>:\n\n"
        f"<code>{game['emoji']}</code>"
    )
    await state.update_data(
        amount=amount,
        prompt_id=prompt.message_id,
        expires_at=(datetime.utcnow() + timedelta(seconds=DICE_REPLY_SECONDS)).isoformat(),
    )
    await state.set_state(CasinoStates.waiting_dice_reply)


@router.message(CasinoStates.waiting_dice_reply, F.dice)
async def solo_dice_resolve(message: Message, state: FSMContext, session, db_user: User):
    data = await state.get_data()
    game_key = data.get("game")
    game = GAMES.get(game_key)
    prompt_id = data.get("prompt_id")
    expires_at = data.get("expires_at")
    amount = data.get("amount")
    bet_type = data.get("bet_type")  # فقط برای تاس

    if not game or not prompt_id or amount is None:
        return
    if not message.reply_to_message or message.reply_to_message.message_id != prompt_id:
        await message.answer(f"❌ رو پیام شرط ریپلای کن: <code>{game['emoji']}</code>")
        return
    if message.dice.emoji != game["emoji"]:
        await message.answer(f"❌ باید همین رو بفرستی: <code>{game['emoji']}</code>")
        return
    if expires_at and datetime.utcnow() > datetime.fromisoformat(expires_at):
        await state.clear()
        await message.answer("⏰ وقتت تموم شد! شرط باطل شد، دوباره امتحان کن.")
        return

    value = message.dice.value

    if game_key == "casino_dice" and bet_type:
        won, multiplier = _dice_bet_result(bet_type, value)
        note = f"🎲 عدد <b>{value}</b> اومد!"
    else:
        multiplier = _score_multiplier(game_key, value)
        won = multiplier > 0
        note = f"🎯 امتیاز <b>{value}</b>! ضریب: <b>x{multiplier}</b>"

    db_user.bet_today_total += amount
    db_user.last_bet = datetime.utcnow()

    if won:
        profit = round(amount * multiplier)
        net = profit - amount
        db_user.cash += net
        await log_transaction(session, db_user.id, "casino_win", net, f"برد در {game['name']}")
        await add_xp(session, db_user, random.randint(5, 15))
        sign = "+" if net >= 0 else ""
        text = (
            f"{header('🎉 برد!')}\n\n{note}\n"
            f"💰 <code>{sign}{fmt_money(net)}</code> | 💵 موجودی: <code>{fmt_money(db_user.cash)}</code>"
        )
        if net >= BIG_WIN_THRESHOLD:
            text = "🎆 <b>برد بزرگ!!!</b> 🎆\n\n" + text
    else:
        db_user.cash -= amount
        await log_transaction(session, db_user.id, "casino_lose", -amount, f"باخت در {game['name']}")
        text = (
            f"{header('😢 باخت')}\n\n{note}\n"
            f"💸 <code>-{fmt_money(amount)}</code> | 💵 موجودی: <code>{fmt_money(db_user.cash)}</code>"
        )

    await session.commit()
    await state.clear()

    b = InlineKeyboardBuilder()
    b.button(text="🔁 دوباره کازینو", callback_data="casino_back", style="success")
    await message.answer(text, reply_markup=b.as_markup())


# ==================== حالت گروهی: راه‌اندازی و پیوستن ====================

@router.message(CasinoStates.waiting_mp_amount)
async def mp_amount_set(message: Message, state: FSMContext, session, db_user: User):
    if not await check_reply(message, state):
        return
    amount = parse_amount(message.text)
    err = _validate_bet(amount, db_user)
    if err:
        await message.answer(err)
        return

    data = await state.get_data()
    game_key = data["game"]
    players_needed = data["players_needed"]
    game = GAMES[game_key]
    chat_id = message.chat.id

    if chat_id in active_group_games:
        await message.answer("❌ همین الان یه بازی گروهی تو این چت در جریانه!")
        await state.clear()
        return

    db_user.cash -= amount
    db_user.bet_today_total += amount
    db_user.last_bet = datetime.utcnow()
    await log_transaction(session, db_user.id, "casino_mp_join", -amount, f"ورود به {game['name']} گروهی")
    await session.commit()
    await state.clear()

    active_group_games[chat_id] = {
        "game": game_key,
        "amount": amount,
        "players_needed": players_needed,
        "phase": "joining",
        "participants": {db_user.telegram_id: {"name": db_user.first_name or "کاربر"}},
        "rolls": {},
    }

    b = InlineKeyboardBuilder()
    b.button(text="🎮 ورود به بازی", callback_data="cg_join", style="success")
    text = (
        f"{header(game['name'] + ' گروهی')}\n\n"
        f"👤 <b>{db_user.first_name}</b> شروع کرد | مبلغ هرنفر: <code>{fmt_money(amount)}</code>\n"
        f"👥 نفرات: 1/{players_needed}\n"
        f"⏳ {CASINO_MULTIPLAYER_JOIN_SECONDS} ثانیه فرصت پیوستن"
    )
    msg = await message.answer(text, reply_markup=b.as_markup())
    active_group_games[chat_id]["lobby_message_id"] = msg.message_id
    asyncio.create_task(_mp_join_timeout(message.bot, chat_id))


@router.callback_query(F.data == "cg_join")
async def mp_join(callback: CallbackQuery, session, db_user: User):
    chat_id = callback.message.chat.id
    lobby = active_group_games.get(chat_id)
    if not lobby or lobby["phase"] != "joining":
        await callback.answer("❌ بازی‌ای برای پیوستن نیست یا زمانش تموم شده!", show_alert=True)
        return
    if db_user.telegram_id in lobby["participants"]:
        await callback.answer("✅ تو همین الان تو بازی‌ای!", show_alert=True)
        return
    if is_in_prison(db_user):
        await callback.answer("🚔 تو زندانی نمیتونی بازی کنی!", show_alert=True)
        return

    amount = lobby["amount"]
    if db_user.cash < amount:
        await callback.answer(f"❌ برای پیوستن {fmt_money(amount)} تومان لازمه!", show_alert=True)
        return
    _reset_daily_if_needed(db_user)
    if db_user.bet_today_total + amount > BET_MAX_DAILY:
        await callback.answer("❌ سقف شرط روزانه‌ت پر شده!", show_alert=True)
        return

    game = GAMES[lobby["game"]]
    db_user.cash -= amount
    db_user.bet_today_total += amount
    db_user.last_bet = datetime.utcnow()
    await log_transaction(session, db_user.id, "casino_mp_join", -amount, f"ورود به {game['name']} گروهی")
    await session.commit()

    lobby["participants"][db_user.telegram_id] = {"name": db_user.first_name or "کاربر"}

    if len(lobby["participants"]) >= lobby["players_needed"]:
        lobby["phase"] = "rolling"
        names = "، ".join(p["name"] for p in lobby["participants"].values())
        pool = amount * len(lobby["participants"])
        prompt = await callback.message.answer(
            f"{header(game['name'] + ' - شروع!')}\n\n"
            f"👥 بازیکنا: {names}\n"
            f"💰 استخر مشترک: <code>{fmt_money(pool)}</code>\n\n"
            f"همه باید این رو بزنن، بفرستنش و <b>رو همین پیام ریپلای کنن</b>:\n\n"
            f"<code>{game['emoji']}</code>"
        )
        lobby["roll_prompt_id"] = prompt.message_id
        asyncio.create_task(_mp_roll_timeout(callback.bot, chat_id))
        await callback.answer("🟢 همه پیوستن! نوبت پرتابه!")
    else:
        try:
            await callback.message.edit_text(
                f"{header(game['name'] + ' گروهی')}\n\n"
                f"مبلغ هرنفر: <code>{fmt_money(amount)}</code>\n"
                f"👥 نفرات: {len(lobby['participants'])}/{lobby['players_needed']}\n"
                f"⏳ {CASINO_MULTIPLAYER_JOIN_SECONDS} ثانیه فرصت پیوستن",
                reply_markup=callback.message.reply_markup
            )
        except Exception:
            pass
        await callback.answer(
            f"🟢 وارد بازی شدی! نفرات فعلی: {len(lobby['participants'])}/{lobby['players_needed']}",
            show_alert=True
        )


@router.message(F.dice, F.chat.type.in_({"group", "supergroup"}))
async def mp_dice_collect(message: Message):
    chat_id = message.chat.id
    lobby = active_group_games.get(chat_id)
    if not lobby or lobby.get("phase") != "rolling":
        return
    if not message.reply_to_message or message.reply_to_message.message_id != lobby.get("roll_prompt_id"):
        return
    game = GAMES[lobby["game"]]
    if message.dice.emoji != game["emoji"]:
        return
    tg_id = message.from_user.id
    if tg_id not in lobby["participants"] or tg_id in lobby["rolls"]:
        return

    lobby["rolls"][tg_id] = message.dice.value

    if len(lobby["rolls"]) >= len(lobby["participants"]):
        await _resolve_mp_game(message.bot, chat_id)


async def _mp_join_timeout(bot, chat_id: int):
    await asyncio.sleep(CASINO_MULTIPLAYER_JOIN_SECONDS)
    lobby = active_group_games.get(chat_id)
    if not lobby or lobby["phase"] != "joining":
        return
    active_group_games.pop(chat_id, None)

    game = GAMES[lobby["game"]]
    amount = lobby["amount"]
    async with async_session() as session:
        for tg_id in lobby["participants"]:
            result = await session.execute(select(User).where(User.telegram_id == tg_id))
            user = result.scalar_one_or_none()
            if user:
                user.cash += amount
                await log_transaction(session, user.id, "casino_mp_refund", amount, f"استرداد {game['name']} گروهی (نفرات ناکافی)")
        await session.commit()

    await bot.send_message(
        chat_id,
        f"😐 <b>{game['name']} گروهی لغو شد!</b>\nتعداد کافی بازیکن جمع نشد، مبلغ همه برگشت داده شد.",
        parse_mode="HTML"
    )


async def _mp_roll_timeout(bot, chat_id: int):
    await asyncio.sleep(DICE_REPLY_SECONDS)
    lobby = active_group_games.get(chat_id)
    if not lobby or lobby["phase"] != "rolling":
        return
    await _resolve_mp_game(bot, chat_id)


async def _resolve_mp_game(bot, chat_id: int):
    lobby = active_group_games.pop(chat_id, None)
    if not lobby:
        return

    game = GAMES[lobby["game"]]
    amount = lobby["amount"]
    participants = lobby["participants"]
    rolls = lobby["rolls"]
    pool = amount * len(participants)

    async with async_session() as session:
        if not rolls:
            for tg_id in participants:
                result = await session.execute(select(User).where(User.telegram_id == tg_id))
                user = result.scalar_one_or_none()
                if user:
                    user.cash += amount
                    await log_transaction(session, user.id, "casino_mp_refund", amount, f"استرداد {game['name']} گروهی")
            await session.commit()
            await bot.send_message(
                chat_id,
                f"😐 هیچکس تو {game['name']} گروهی پرتاب نکرد، مبلغ همه برگشت داده شد.",
                parse_mode="HTML"
            )
            return

        max_val = max(rolls.values())
        winners = {tg_id for tg_id, v in rolls.items() if v == max_val}
        share = round(pool / len(winners))

        lines = [header(f"🏆 نتیجه {game['name']} گروهی"), ""]
        for tg_id, p in participants.items():
            val = rolls.get(tg_id)
            result = await session.execute(select(User).where(User.telegram_id == tg_id))
            user = result.scalar_one_or_none()
            if tg_id in winners:
                if user:
                    user.cash += share
                    await log_transaction(session, user.id, "casino_mp_win", share - amount, f"برد در {game['name']} گروهی")
                lines.append(f"🥇 {p['name']} — امتیاز {val} — <code>+{fmt_money(share - amount)}</code>")
            elif val is not None:
                lines.append(f"😢 {p['name']} — امتیاز {val} — <code>-{fmt_money(amount)}</code>")
            else:
                lines.append(f"⌛ {p['name']} — پرتاب نکرد — <code>-{fmt_money(amount)}</code>")
        await session.commit()

    await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")


# ==================== بازی‌های متنی: سکه و رولت (بدون تغییر) ====================

@router.callback_query(F.data.in_(TEXT_GAMES.keys()))
async def choose_text_game(callback: CallbackQuery, state: FSMContext, db_user: User):
    if is_in_prison(db_user):
        await callback.answer("🚔 تو زندانی نمیتونی شرط ببندی!", show_alert=True)
        return

    remain = _cooldown_remaining(db_user)
    if remain:
        await callback.answer(f"⏳ {fmt_seconds(remain)} دیگه صبر کن!", show_alert=True)
        return

    game = TEXT_GAMES[callback.data]
    await state.set_state(CasinoStates.waiting_text_bet)
    await callback.message.edit_text(
        f"{header(game['name'])}\n\n"
        f"💰 حداقل: <code>{fmt_money(BET_MIN)}</code> | ضریب: x{game['multiplier']}\n\n"
        f"↩️ رو همین پیام ریپلای کن و بگو چقدر شرط می‌بندی",
        reply_markup=back_kb("casino_back")
    )
    await set_prompt(state, callback.message.message_id, game=callback.data)
    await callback.answer()


@router.message(CasinoStates.waiting_text_bet)
async def text_bet_amount(message: Message, state: FSMContext, session, db_user: User):
    if not await check_reply(message, state):
        return
    amount = parse_amount(message.text)
    err = _validate_bet(amount, db_user)
    if err:
        await message.answer(err)
        return

    data = await state.get_data()
    game_key = data["game"]
    game = TEXT_GAMES[game_key]

    won = random.random() < game["win_chance"]
    db_user.cash -= amount
    db_user.bet_today_total += amount
    db_user.last_bet = datetime.utcnow()

    animation = _text_game_animation(game_key)

    if won:
        profit = round(amount * game["multiplier"])
        db_user.cash += profit
        net = profit - amount
        await log_transaction(session, db_user.id, "casino_win", net, f"برد در {game['name']}")
        await add_xp(session, db_user, random.randint(5, 15))
        text = (
            f"{header('🎉 برد!')}\n\n{animation}\n"
            f"💰 <code>+{fmt_money(net)}</code> | 💵 موجودی: <code>{fmt_money(db_user.cash)}</code>"
        )
        if net >= BIG_WIN_THRESHOLD:
            text = "🎆 <b>برد بزرگ!!!</b> 🎆\n\n" + text
    else:
        await log_transaction(session, db_user.id, "casino_lose", -amount, f"باخت در {game['name']}")
        text = (
            f"{header('😢 باخت')}\n\n{animation}\n"
            f"💸 <code>-{fmt_money(amount)}</code> | 💵 موجودی: <code>{fmt_money(db_user.cash)}</code>"
        )

    await session.commit()
    await state.clear()

    b = InlineKeyboardBuilder()
    b.button(text="🔁 دوباره کازینو", callback_data="casino_back", style="success")
    await message.answer(text, reply_markup=b.as_markup())


def _text_game_animation(game: str) -> str:
    if game == "casino_coin":
        result = random.choice(["🌕 شیر", "🌑 خط"])
        return f"🪙 سکه در هوا... {result}!"
    if game == "casino_roulette":
        num = random.randint(0, 36)
        color = "🔴" if num % 2 == 0 else "⚫️"
        return f"🎡 گوی روی عدد {num} {color} ایستاد!"
    return ""


@router.callback_query(F.data == "casino_back")
async def casino_back(callback: CallbackQuery, state: FSMContext, db_user: User):
    await state.clear()
    _reset_daily_if_needed(db_user)
    text = (
        f"{header('🎰 کازینوی کلان‌شهر')}\n\n"
        f"💵 موجودی: <code>{fmt_money(db_user.cash)}</code> تومان\n"
        f"📊 مجموع شرط امروز: <code>{fmt_money(db_user.bet_today_total)}</code> / <code>{fmt_money(BET_MAX_DAILY)}</code>\n\n"
        f"یکی از بازی‌ها رو انتخاب کن:"
    )
    await callback.message.edit_text(text, reply_markup=casino_kb())
    await callback.answer()
