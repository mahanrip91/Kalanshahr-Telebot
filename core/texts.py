"""
قالب‌های متنی مشترک برای پیام‌های شیک HTML
"""

DIVIDER = "─" * 18
DIVIDER_BOLD = "═" * 18


def header(title: str) -> str:
    return f"{DIVIDER_BOLD}\n<b>{title}</b>\n{DIVIDER_BOLD}"


def section(title: str) -> str:
    return f"\n{DIVIDER}\n<b>{title}</b>\n{DIVIDER}"


WELCOME_TEXT = """
🌆 <b>به کلان‌شهر خوش اومدی، {name}!</b>

اینجا یه شهر شبیه‌سازی‌شده‌ست که خودت باید بسازیش:
کار کن، پول در بیار، تو بورس و ارز دیجیتال سرمایه‌گذاری کن،
خونه و مغازه بخر، تو کازینو شانستو امتحان کن، وارد دنیای خلاف شو،
و بالاخره... شاید یه روز <b>شهردار</b> بشی!

از دکمه‌های پایین صفحه شروع کن، یا کافیه هرجا هستی (حتی تو گروه)
اسم هر بخش رو تایپ کنی 👇
"""

NOT_ENOUGH_MONEY = "❌ <b>پول کافی نداری!</b>\nموجودی نقدت: <code>{cash}</code> تومان"

IN_PRISON_TEXT = "🚔 <b>تو زندانی!</b>\nزمان باقی‌مانده: <code>{time}</code>\nدلیل: {reason}"

COOLDOWN_TEXT = "⏳ باید صبر کنی!\nزمان باقی‌مانده: <code>{time}</code>"

KICKED_TEXT = "🚫 <b>شما توسط مالک ربات اخراج شدید!</b>\nدیگه نمی‌تونی از امکانات کلان‌شهر استفاده کنی."

INVALID_AMOUNT_TEXT = "❌ مبلغ نامعتبره. مثلاً: <code>5000</code> یا <code>5k</code> یا <code>۵هزار</code>"

REPLY_REQUIRED_TEXT = "↩️ باید رو همین پیام ریپلای کنی و جواب بدی."
