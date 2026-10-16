"""
سیستم ساخت‌وساز: خرید زمین، ساخت ملک، ارتقا، تخریب، درآمد اجاره
خرید/ارتقا/فروش هرکدوم قبل از اجرا یه تایید دارن.
"""
from datetime import datetime
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from database.models import User, Property
from core.texts import header, NOT_ENOUGH_MONEY
from core.keyboards import back_kb, confirm_kb
from core.economy import log_transaction
from core.auto_revert import schedule_revert
from utils.formatting import fmt_money, fmt_seconds

router = Router(name="property")

ZONES = {
    "پایین‌شهر":  {"multiplier": 1.0},
    "مرکز‌شهر":   {"multiplier": 1.8},
    "بالای‌شهر":  {"multiplier": 3.2},
}

PROPERTY_TYPES = {
    "آپارتمان": {"base_price": 40_000, "hourly_income": 350},
    "خانه":     {"base_price": 70_000, "hourly_income": 650},
    "ویلا":     {"base_price": 150_000, "hourly_income": 1500},
    "مغازه":    {"base_price": 90_000, "hourly_income": 1000},
}

UPGRADE_COST_MULTIPLIER = 0.6
UPGRADE_INCOME_BOOST = 0.35


@router.message(F.text.in_({"🏗️ ساخت‌وساز", "ساخت‌وساز", "ساخت وساز", "املاک"}))
async def property_menu(message: Message, session, db_user: User):
    text, markup = await _build_property_list(session, db_user)
    await message.answer(text, reply_markup=markup)


def _pending_income(p: Property) -> float:
    hours = (datetime.utcnow() - p.last_collect).total_seconds() / 3600
    hours = min(hours, 72)
    return p.hourly_income * hours


async def _build_property_list(session, db_user: User):
    """متن و کیبورد لیست املاک - جدا شده برای استفاده مجدد (منو + بازگشت خودکار)"""
    props = (await session.execute(select(Property).where(Property.user_id == db_user.id))).scalars().all()
    lines = [header("🏗️ ساخت‌وساز و املاک"), ""]
    if not props:
        lines.append("هنوز هیچ ملکی نداری!")
    else:
        for p in props:
            pending = _pending_income(p)
            lines.append(f"🏠 <b>{p.ptype}</b> در {p.zone} (لول {p.level}) — درآمد در انتظار: <code>{fmt_money(pending)}</code>")

    b = InlineKeyboardBuilder()
    b.button(text="🏗️ خرید ملک جدید", callback_data="prop_buy_menu", style="success")
    if props:
        b.button(text="💰 جمع‌آوری همه درآمدها", callback_data="prop_collect_all")
        b.button(text="📋 مدیریت املاک", callback_data="prop_manage", style="primary")
    b.adjust(1)
    return "\n".join(lines), b.as_markup()


@router.callback_query(F.data == "prop_buy_menu")
async def buy_menu(callback: CallbackQuery):
    b = InlineKeyboardBuilder()
    for zone in ZONES:
        b.button(text=f"📍 {zone}", callback_data=f"prop_zone:{zone}")
    b.button(text="🔙 بازگشت", callback_data="prop_back")
    b.adjust(1)
    await callback.message.edit_text(
        f"{header('📍 انتخاب منطقه')}\n\nهر منطقه قیمت و درآمد متفاوتی داره:",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prop_zone:"))
async def zone_types(callback: CallbackQuery):
    zone = callback.data.split(":", 1)[1]
    mult = ZONES[zone]["multiplier"]

    lines = [header(f"🏗️ ساخت‌وساز در {zone}"), ""]
    b = InlineKeyboardBuilder()
    for ptype, info in PROPERTY_TYPES.items():
        price = round(info["base_price"] * mult)
        income = round(info["hourly_income"] * mult)
        lines.append(f"🏠 <b>{ptype}</b>: <code>{fmt_money(price)}</code> تومان (درآمد {fmt_money(income)}/ساعت)")
        b.button(text=f"{ptype}", callback_data=f"prop_pick:{zone}:{ptype}", style="success")
    b.button(text="🔙 بازگشت", callback_data="prop_buy_menu")
    b.adjust(2, 2, 1)

    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("prop_pick:"))
async def property_confirm_ask(callback: CallbackQuery, db_user: User):
    _, zone, ptype = callback.data.split(":")
    mult = ZONES[zone]["multiplier"]
    info = PROPERTY_TYPES[ptype]
    price = round(info["base_price"] * mult)
    income = round(info["hourly_income"] * mult)

    if db_user.cash < price:
        await callback.answer(f"❌ پول کافی نداری! قیمت: {fmt_money(price)}", show_alert=True)
        return

    await callback.message.edit_text(
        f"{header('✅ تایید خرید ملک')}\n\n"
        f"🏠 <b>{ptype}</b> در <b>{zone}</b>\n"
        f"💰 قیمت: <code>{fmt_money(price)}</code> تومان\n"
        f"📈 درآمد: <code>{fmt_money(income)}</code> تومان در ساعت\n\n"
        f"مطمئنی می‌خوای بخریش؟",
        reply_markup=confirm_kb(f"prop_buy:{zone}:{ptype}", "prop_buy_menu")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prop_buy:"))
async def buy_property(callback: CallbackQuery, session, db_user: User):
    _, zone, ptype = callback.data.split(":")
    mult = ZONES[zone]["multiplier"]
    info = PROPERTY_TYPES[ptype]
    price = round(info["base_price"] * mult)
    income = round(info["hourly_income"] * mult)

    if db_user.cash < price:
        await callback.answer(f"❌ پول کافی نداری! قیمت: {fmt_money(price)}", show_alert=True)
        return

    db_user.cash -= price
    prop = Property(
        user_id=db_user.id, zone=zone, ptype=ptype, level=1,
        purchase_price=price, hourly_income=income, last_collect=datetime.utcnow()
    )
    session.add(prop)
    await log_transaction(session, db_user.id, "property_buy", -price, f"خرید {ptype} در {zone}")
    await session.commit()

    await callback.message.edit_text(
        f"✅ <b>{ptype}</b> در <b>{zone}</b> خریداری شد!\n"
        f"💰 درآمد: <code>{fmt_money(income)}</code> تومان در ساعت\n"
        f"💵 موجودی: <code>{fmt_money(db_user.cash)}</code> تومان",
        reply_markup=back_kb("prop_back")
    )
    await callback.answer("✅ خریداری شد!")


@router.callback_query(F.data == "prop_collect_all")
async def collect_all(callback: CallbackQuery, session, db_user: User):
    props = (await session.execute(select(Property).where(Property.user_id == db_user.id))).scalars().all()
    total = 0
    for p in props:
        total += _pending_income(p)
        p.last_collect = datetime.utcnow()

    if total <= 0:
        await callback.answer("😐 درآمدی برای جمع‌آوری نیست!", show_alert=True)
        return

    db_user.cash += total
    await log_transaction(session, db_user.id, "property_income", total, "درآمد اجاره املاک")
    await session.commit()

    await callback.message.edit_text(
        f"✅ <code>{fmt_money(total)}</code> تومان درآمد اجاره جمع‌آوری شد!\n"
        f"💵 موجودی جدید: <code>{fmt_money(db_user.cash)}</code> تومان",
        reply_markup=back_kb("prop_back")
    )
    await callback.answer()

    revert_text, revert_kb = await _build_property_list(session, db_user)
    schedule_revert(callback.message, revert_text, revert_kb)


@router.callback_query(F.data == "prop_manage")
async def manage_properties(callback: CallbackQuery, session, db_user: User):
    props = (await session.execute(select(Property).where(Property.user_id == db_user.id))).scalars().all()
    if not props:
        await callback.answer("هیچ ملکی نداری!", show_alert=True)
        return

    b = InlineKeyboardBuilder()
    lines = [header("📋 مدیریت املاک"), ""]
    for p in props:
        lines.append(f"🏠 #{p.id} — {p.ptype} در {p.zone} (لول {p.level})")
        b.button(text=f"⬆️ ارتقا #{p.id}", callback_data=f"prop_upgrade_ask:{p.id}", style="success")
        b.button(text=f"🗑 فروش #{p.id}", callback_data=f"prop_sell_ask:{p.id}", style="danger")
    b.button(text="🔙 بازگشت", callback_data="prop_back")
    b.adjust(2)

    await callback.message.edit_text("\n".join(lines), reply_markup=b.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("prop_upgrade_ask:"))
async def upgrade_property_ask(callback: CallbackQuery, session, db_user: User):
    prop_id = int(callback.data.split(":")[1])
    prop = await session.get(Property, prop_id)
    if not prop or prop.user_id != db_user.id:
        await callback.answer("❌ ملک پیدا نشد!", show_alert=True)
        return

    cost = round(prop.purchase_price * UPGRADE_COST_MULTIPLIER * prop.level)
    if db_user.cash < cost:
        await callback.answer(f"❌ برای ارتقا {fmt_money(cost)} تومان لازمه!", show_alert=True)
        return

    new_income = round(prop.hourly_income * (1 + UPGRADE_INCOME_BOOST))
    await callback.message.edit_text(
        f"{header('✅ تایید ارتقا')}\n\n"
        f"🏠 {prop.ptype} در {prop.zone} — لول {prop.level} ← <b>{prop.level + 1}</b>\n"
        f"💰 هزینه: <code>{fmt_money(cost)}</code> تومان\n"
        f"📈 درآمد جدید: <code>{fmt_money(new_income)}</code> تومان در ساعت\n\n"
        f"مطمئنی؟",
        reply_markup=confirm_kb(f"prop_upgrade:{prop.id}", "prop_manage")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prop_upgrade:"))
async def upgrade_property(callback: CallbackQuery, session, db_user: User):
    prop_id = int(callback.data.split(":")[1])
    prop = await session.get(Property, prop_id)
    if not prop or prop.user_id != db_user.id:
        await callback.answer("❌ ملک پیدا نشد!", show_alert=True)
        return

    cost = round(prop.purchase_price * UPGRADE_COST_MULTIPLIER * prop.level)
    if db_user.cash < cost:
        await callback.answer(f"❌ برای ارتقا {fmt_money(cost)} تومان لازمه!", show_alert=True)
        return

    db_user.cash -= cost
    prop.level += 1
    prop.hourly_income = round(prop.hourly_income * (1 + UPGRADE_INCOME_BOOST))
    await log_transaction(session, db_user.id, "property_upgrade", -cost, f"ارتقای {prop.ptype}")
    await session.commit()

    await callback.message.edit_text(
        f"✅ ملک به لول {prop.level} ارتقا پیدا کرد!\n"
        f"📈 درآمد جدید: <code>{fmt_money(prop.hourly_income)}</code> تومان در ساعت\n"
        f"💵 موجودی: <code>{fmt_money(db_user.cash)}</code> تومان",
        reply_markup=back_kb("prop_back")
    )
    await callback.answer("✅ ارتقا پیدا کرد!")


@router.callback_query(F.data.startswith("prop_sell_ask:"))
async def sell_property_ask(callback: CallbackQuery, session, db_user: User):
    prop_id = int(callback.data.split(":")[1])
    prop = await session.get(Property, prop_id)
    if not prop or prop.user_id != db_user.id:
        await callback.answer("❌ ملک پیدا نشد!", show_alert=True)
        return

    sale_price = round(prop.purchase_price * 0.7 * prop.level)
    await callback.message.edit_text(
        f"{header('⚠️ تایید فروش')}\n\n"
        f"🏠 {prop.ptype} در {prop.zone} (لول {prop.level})\n"
        f"💰 مبلغ دریافتی: <code>{fmt_money(sale_price)}</code> تومان\n\n"
        f"این کار برگشت‌ناپذیره، مطمئنی؟",
        reply_markup=confirm_kb(f"prop_sell:{prop.id}", "prop_manage")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("prop_sell:"))
async def sell_property(callback: CallbackQuery, session, db_user: User):
    prop_id = int(callback.data.split(":")[1])
    prop = await session.get(Property, prop_id)
    if not prop or prop.user_id != db_user.id:
        await callback.answer("❌ ملک پیدا نشد!", show_alert=True)
        return

    sale_price = round(prop.purchase_price * 0.7 * prop.level)
    db_user.cash += sale_price
    await log_transaction(session, db_user.id, "property_sell", sale_price, f"فروش {prop.ptype}")
    await session.delete(prop)
    await session.commit()

    await callback.message.edit_text(
        f"✅ ملک فروخته شد!\n💰 دریافتی: <code>{fmt_money(sale_price)}</code> تومان\n"
        f"💵 موجودی: <code>{fmt_money(db_user.cash)}</code> تومان",
        reply_markup=back_kb("prop_back")
    )
    await callback.answer("✅ فروخته شد!")


@router.callback_query(F.data == "prop_back")
async def prop_back(callback: CallbackQuery, session, db_user: User):
    text, markup = await _build_property_list(session, db_user)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()
