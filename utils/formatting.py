"""
توابع فرمت‌دهی متن و اعداد + پارس هوشمند مبلغ ورودی کاربر
"""
import re
from datetime import datetime, timedelta

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
ENGLISH_DIGITS = "0123456789"
_DIGIT_MAP = str.maketrans(PERSIAN_DIGITS + ARABIC_DIGITS, ENGLISH_DIGITS * 2)

_WORD_MULTIPLIERS = [
    ("میلیارد", 1_000_000_000),
    ("میلیون", 1_000_000),
    ("هزار", 1_000),
]

# همه‌ی زمان‌های ذخیره‌شده تو دیتابیس UTC هستن (datetime.utcnow) - این درسته و نباید
# عوض بشه. فقط موقع نمایش به کاربر باید تبدیل به وقت تهران (UTC+3:30) بشه.
TEHRAN_OFFSET = timedelta(hours=3, minutes=30)


def to_tehran(dt: datetime):
    """زمان UTC ذخیره‌شده رو فقط برای نمایش به وقت تهران تبدیل می‌کنه"""
    if dt is None:
        return None
    return dt + TEHRAN_OFFSET


def fmt_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M") -> str:
    """فرمت زمان به وقت تهران برای نمایش به کاربر (به‌جای strftime مستقیم رو UTC)"""
    if dt is None:
        return "-"
    return to_tehran(dt).strftime(fmt)


def fmt_money(amount: float) -> str:
    """فرمت زیبای پول، مثلاً 1250000 -> 1,250,000"""
    amount = int(round(amount))
    return f"{amount:,}"


def fmt_percent(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value * 100:.2f}%"


def progress_bar(current: int, total: int, length: int = 12) -> str:
    """نوار پیشرفت متنی برای XP و سطح"""
    if total <= 0:
        total = 1
    ratio = min(max(current / total, 0), 1)
    filled = int(ratio * length)
    return "🟩" * filled + "⬜️" * (length - filled)


def fmt_seconds(seconds) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} ثانیه"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} دقیقه"
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours < 24:
        return f"{hours} ساعت و {remaining_minutes} دقیقه"
    days = hours // 24
    remaining_hours = hours % 24
    return f"{days} روز و {remaining_hours} ساعت"


def parse_amount(text: str):
    """
    پارس هوشمند مبلغ ورودی کاربر. حالت‌های پشتیبانی‌شده:
    4000 | 4,000 | 4k | 4K | 4m | ۴۰۰۰ | ۴هزار | ۴ هزار | ۴ هزار تومان |
    ۴میلیون | ۴.۵ میلیون | 4.5m
    خروجی: عدد صحیح مثبت یا None اگه نامعتبر بود
    """
    if not text or not isinstance(text, str):
        return None

    t = text.strip().translate(_DIGIT_MAP)
    t = t.replace(",", "").replace("٬", "").replace("_", "")
    t = t.replace("تومان", "").replace("تومن", "").replace("ریال", "")
    t = t.strip()
    if not t:
        return None

    # حالت k / m / b انگلیسی مثل 4k یا 2.5m
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([kKmMbB])", t)
    if m:
        num = float(m.group(1))
        mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[m.group(2).lower()]
        val = int(round(num * mult))
        return val if val > 0 else None

    # حالت کلمات فارسی: هزار / میلیون / میلیارد (با یا بدون فاصله، با یا بدون عدد قبلش)
    for word, mult in _WORD_MULTIPLIERS:
        if word in t:
            num_part = t.replace(word, "").strip()
            if num_part == "":
                num = 1.0
            else:
                num_part = num_part.replace(" ", "")
                try:
                    num = float(num_part)
                except ValueError:
                    return None
            val = int(round(num * mult))
            return val if val > 0 else None

    # فقط عدد ساده (با احتمال اعشار)
    t_clean = t.replace(" ", "")
    if re.fullmatch(r"\d+(\.\d+)?", t_clean):
        val = int(round(float(t_clean)))
        return val if val > 0 else None

    return None
