"""
راهنمای تعاملی ربات — به شکل منوی دکمه‌ای
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.texts import header
from config import settings

router = Router(name="help")

TOPICS = {
    "profile": ("👤 حساب من", "پروفایل، سطح، XP و ثروتت رو نشون میده."),
    "work": ("💼 کار", "یه شغل انتخاب کن و کار کن تا حقوق و XP بگیری. عوض کردن شغل کول‌داون رو ریست می‌کنه."),
    "bank": ("🏦 بانک", "واریز/برداشت، سود روزانه، وام، و انتقال با شماره حساب یکتای خودت."),
    "casino": ("🎰 کازینو", "تاس، دارت، بولینگ، بسکتبال، فوتبال، اسلات، سکه، رولت. برای بازی‌های ایموجی، اونو کپی کن، بفرست، رو پیام بات ریپلای کن."),
    "crime": ("🕵️ خلاف", "خلاف تکی (چند نوع، ریسک متفاوت) و خلاف گروهی (سرقت بزرگ بانک، فقط تو گروه)."),
    "property": ("🏗️ ساخت‌وساز", "زمین بخر، ملک بساز، ارتقا بده، اجاره جمع کن."),
    "shop": ("🛒 مغازه‌داری", "مغازه بزن، کالا بخر، بفروش، کارگر استخدام کن."),
    "market": ("📈 بازار مالی", "بورس، ارز دیجیتال، دلار و طلا. قیمت‌ها هر ۱۰ دقیقه عوض میشن."),
    "rewards": ("🎁 جوایز", "جایزه روزانه با استریک، کد هدیه، دعوت دوستان."),
    "leaderboard": ("📊 رتبه‌بندی", "ثروت، سطح، و تعداد املاک."),
    "city": ("🏙️ کلان‌شهر", "فقط تو گروه. مالک گروه خودکار شهردار میشه. شهرداری، خزانه، زندان."),
    "transfer": ("💸 انتقال پول", "بنویس «انتقال پول» تا با آیدی/یوزرنیم پول نقدی بفرستی (۲٪ کارمزد)."),
    "amount": ("💰 نوشتن مبلغ", "هرجوری بنویس: 5000 یا 5k یا ۵هزار یا ۵ میلیون."),
    "settings": ("⚙️ تنظیمات", "اطلاعات حساب، شماره حساب بانکی، لغو عملیات نیمه‌کاره."),
    "owner_panel": ("👑 پنل مالک", "فقط مالک ربات می‌بینه‌ش. از دکمه 👑 پنل مالک یا دستور /پنل_مالک باز می‌شه. شامل: شارژ نقدی/بانکی کاربرا، اخراج/رفع اخراج، ساخت کد هدیه، آمار کلی، ریست کاربر، پیام همگانی، و ری‌استارت کامل ربات."),
    "city_admin_panel": ("⚙️ پنل ادمین شهر", "فقط ادمین‌های گروه بهش دسترسی دارن. از دکمه ⚙️ مدیریت شهر یا دستور /مدیریت_شهر باز می‌شه. شامل: آمار شهر، لیست کمک‌کنندگان خزانه، و تنظیم درصد مالیات."),
}


def help_main_kb(user_id: int = 0) -> InlineKeyboardBuilder:
    b = InlineKeyboardBuilder()
    b.button(text="👤 حساب من", callback_data="help:profile")
    b.button(text="💼 کار", callback_data="help:work")
    b.button(text="🏦 بانک", callback_data="help:bank")
    b.button(text="🎰 کازینو", callback_data="help:casino")
    b.button(text="🕵️ خلاف", callback_data="help:crime")
    b.button(text="🏗️ ساخت‌وساز", callback_data="help:property")
    b.button(text="🛒 مغازه‌داری", callback_data="help:shop")
    b.button(text="📈 بازار مالی", callback_data="help:market")
    b.button(text="🎁 جوایز", callback_data="help:rewards")
    b.button(text="📊 رتبه‌بندی", callback_data="help:leaderboard")
    b.button(text="🏙️ کلان‌شهر", callback_data="help:city")
    b.button(text="💸 انتقال پول", callback_data="help:transfer")
    b.button(text="💰 نوشتن مبلغ", callback_data="help:amount")
    b.button(text="⚙️ تنظیمات", callback_data="help:settings")
    if user_id == settings.OWNER_ID:
        b.button(text="👑 پنل مالک", callback_data="help:owner_panel", style="danger")
    b.button(text="⚙️ پنل ادمین شهر", callback_data="help:city_admin_panel", style="primary")
    if user_id == settings.OWNER_ID:
        b.adjust(2, 2, 2, 2, 2, 2, 2)
    else:
        b.adjust(2, 2, 2, 2, 2, 2, 1)
    return b


HELP_INTRO = f"{header('📖 راهنمای کلان‌شهر')}\n\nیه بخش رو انتخاب کن تا توضیحش رو ببینی 👇"


@router.message(Command("help"))
@router.message(F.text.in_({"راهنما", "/راهنما", "کمک", "📖 راهنما"}))
async def show_help(message: Message):
    await message.answer(HELP_INTRO, reply_markup=help_main_kb(message.from_user.id).as_markup())


@router.callback_query(F.data.startswith("help:"))
async def show_topic(callback: CallbackQuery):
    key = callback.data.split(":", 1)[1]
    title, desc = TOPICS.get(key, ("❓", "چیزی پیدا نشد."))
    b = InlineKeyboardBuilder()
    b.button(text="🔙 بازگشت", callback_data="help_back")
    await callback.message.edit_text(
        f"{header(title)}\n\n{desc}",
        reply_markup=b.as_markup()
    )
    await callback.answer()


@router.callback_query(F.data == "help_back")
async def help_back(callback: CallbackQuery):
    await callback.message.edit_text(HELP_INTRO, reply_markup=help_main_kb(callback.from_user.id).as_markup())
    await callback.answer()
