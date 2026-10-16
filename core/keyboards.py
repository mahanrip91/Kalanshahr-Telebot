"""
کیبوردهای مشترک ربات — منوی اصلی + دکمه‌های رنگی واقعی
"""
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import settings


def main_menu_kb(user_id: int = 0) -> ReplyKeyboardMarkup:
    kb = [
        [KeyboardButton(text="🏠 پنل اصلی", style="primary"), KeyboardButton(text="👤 حساب من", style="primary")],
        [KeyboardButton(text="💼 کار", style="success"), KeyboardButton(text="🏦 بانک", style="success")],
        [KeyboardButton(text="🎰 کازینو", style="danger"), KeyboardButton(text="🕵️ خلاف", style="danger")],
        [KeyboardButton(text="🏗️ ساخت‌وساز"), KeyboardButton(text="🛒 مغازه‌داری")],
        [KeyboardButton(text="📈 بازار مالی"), KeyboardButton(text="🎁 جوایز", style="success")],
        [KeyboardButton(text="📊 رتبه‌بندی"), KeyboardButton(text="🏙️ کلان‌شهر", style="primary")],
        [KeyboardButton(text="📖 راهنما"), KeyboardButton(text="⚙️ تنظیمات")],
    ]
    if user_id == settings.OWNER_ID:
        kb.append([KeyboardButton(text="👑 پنل مالک", style="danger")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)


def back_kb(callback_data: str = "back_main") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔙 بازگشت", callback_data=callback_data)
    return b.as_markup()


def profile_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="تراکنش‌های اخیر", callback_data="profile_history", style="primary")
    b.button(text="دارایی‌ها", callback_data="profile_assets", style="primary")
    b.adjust(2)
    return b.as_markup()


def bank_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="واریز", callback_data="bank_deposit", style="success")
    b.button(text="برداشت", callback_data="bank_withdraw", style="danger")
    b.button(text="سود روزانه", callback_data="bank_interest", style="success")
    b.button(text="انتقال به حساب", callback_data="bank_transfer_start", style="primary")
    b.button(text="درخواست وام", callback_data="loan_request", style="primary")
    b.button(text="بازپرداخت وام", callback_data="loan_repay")
    b.button(text="تاریخچه بانکی", callback_data="bank_history")
    b.adjust(2, 2, 2, 1)
    return b.as_markup()


def casino_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🎲 تاس شانس", callback_data="casino_dice", style="success")
    b.button(text="🎯 دارت", callback_data="casino_dart", style="success")
    b.button(text="🎳 بولینگ", callback_data="casino_bowling", style="primary")
    b.button(text="🏀 بسکتبال", callback_data="casino_basket", style="primary")
    b.button(text="⚽ فوتبال", callback_data="casino_football", style="primary")
    b.button(text="🎰 اسلات‌ماشین", callback_data="casino_slot", style="danger")
    b.button(text="🪙 شیر یا خط", callback_data="casino_coin")
    b.button(text="🎡 رولت", callback_data="casino_roulette")
    b.adjust(2, 2, 2, 2)
    return b.as_markup()


def crime_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🕵️‍♂️ خلاف تکی", callback_data="crime_solo_menu", style="danger")
    b.button(text="👥 خلاف گروهی", callback_data="crime_group_menu", style="danger")
    b.adjust(1)
    return b.as_markup()


def market_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="📈 بورس سهام", callback_data="market_stocks", style="success")
    b.button(text="₿ ارز دیجیتال", callback_data="market_crypto", style="danger")
    b.button(text="💵 دلار و طلا", callback_data="market_forex", style="primary")
    b.button(text="💼 پرتفوی من", callback_data="market_portfolio")
    b.adjust(2, 2)
    return b.as_markup()


def city_kb(is_active: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if is_active:
        b.button(text="🏛️ شهرداری", callback_data="city_hall", style="primary")
        b.button(text="💰 خزانه شهر", callback_data="city_treasury", style="success")
        b.button(text="🚔 زندان شهر", callback_data="city_prison", style="danger")
        b.button(text="📊 وضعیت شهر", callback_data="city_status")
        b.button(text="⚙️ مدیریت شهر", callback_data="city_admin_panel", style="primary")
        b.adjust(2, 2, 1)
    else:
        b.button(text="📊 وضعیت شهر", callback_data="city_status")
    return b.as_markup()


def confirm_kb(yes_cb: str, no_cb: str = "back_main") -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ تایید", callback_data=yes_cb, style="success")
    b.button(text="❌ انصراف", callback_data=no_cb, style="danger")
    b.adjust(2)
    return b.as_markup()
