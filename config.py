import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# مقادیر پیش‌فرض توکن و آیدی مالک - مستقیم همینجا تنظیم شدن.
# اگه یه روز خواستی عوضشون کنی، یا همینجا مقدار رو عوض کن، یا تو فایل .env
# مقدار BOT_TOKEN / OWNER_ID رو ست کن (اگه .env مقدار داشته باشه، همون اولویت داره).
DEFAULT_BOT_TOKEN = "8980685753:AAEYlGjCn2Q37EOgTn8g-0umlNV5w7h7B_E"
DEFAULT_OWNER_ID = "7001392382"


class _Settings:
    def __init__(self):
        self.BOT_TOKEN = os.environ.get("BOT_TOKEN") or DEFAULT_BOT_TOKEN
        owner_id = os.environ.get("OWNER_ID") or DEFAULT_OWNER_ID
        self.OWNER_ID = int(owner_id) if owner_id.strip().lstrip("-").isdigit() else 0
        min_members = os.environ.get("MIN_GROUP_MEMBERS", "10")
        self.MIN_GROUP_MEMBERS = int(min_members) if min_members.strip().isdigit() else 10
        self.DB_PATH = str(BASE_DIR / "database" / "kalanshahr.db")

        if not self.BOT_TOKEN or self.BOT_TOKEN == "PUT_YOUR_TOKEN_HERE":
            raise RuntimeError("❌ BOT_TOKEN تنظیم نشده! فایل .env رو باز کن.")
        if self.OWNER_ID == 0:
            print("⚠️ هشدار: OWNER_ID تنظیم نشده.")


settings = _Settings()

START_CASH = 5000

JOBS = {
    "دستفروش":     {"level": 1,  "salary": 800,   "cooldown": 1800},
    "راننده تاکسی": {"level": 3,  "salary": 1500,  "cooldown": 2400},
    "کارگر ساختمان": {"level": 5,  "salary": 2200,  "cooldown": 3000},
    "فروشنده":     {"level": 8,  "salary": 3200,  "cooldown": 3600},
    "برنامه‌نویس":  {"level": 12, "salary": 5500,  "cooldown": 5400},
    "پزشک":        {"level": 18, "salary": 9000,  "cooldown": 7200},
    "وکیل":        {"level": 25, "salary": 14000, "cooldown": 9000},
    "مدیر شرکت":    {"level": 35, "salary": 25000, "cooldown": 10800},
}

BANK_MIN_INTEREST = 0.025
BANK_MAX_INTEREST = 0.05
BANK_DAILY_DEPOSIT_LIMIT = 200_000
BANK_TRANSFER_FEE_RATE = 0.01

LOAN_INTEREST_RATE = 0.12
LOAN_MAX_DAYS = 7
LOAN_LATE_PENALTY_PER_DAY = 0.03

BET_MIN = 500
BET_MAX_DAILY = 50_000
BET_COOLDOWN = 60
DICE_REPLY_SECONDS = 60  # فرصت ریپلای زدن ایموجی شانسی تو کازینو
CASINO_MULTIPLAYER_JOIN_SECONDS = 60  # فرصت جمع شدن بازیکنا تو بازی گروهی کازینو

DAILY_BASE_REWARD = 2000
DAILY_STREAK_BONUS = 500
DAILY_STREAK_CAP = 10

HEIST_JOIN_SECONDS = 90
HEIST_MIN_PARTICIPANTS = 3

def xp_needed_for_level(level: int) -> int:
    return int(500 * (level ** 1.35))

CITY_LEVELS = [
    {"name": "کویر",       "min_treasury": 0,         "min_members": 0,  "min_contributors": 0,  "min_shops": 0},
    {"name": "روستا",      "min_treasury": 50_000,    "min_members": 10, "min_contributors": 2,  "min_shops": 0},
    {"name": "شهر کوچک",   "min_treasury": 200_000,   "min_members": 20, "min_contributors": 5,  "min_shops": 2},
    {"name": "کلان‌شهر",   "min_treasury": 800_000,   "min_members": 40, "min_contributors": 10, "min_shops": 5},
    {"name": "ابرشهر",     "min_treasury": 3_000_000, "min_members": 80, "min_contributors": 20, "min_shops": 10},
]

ELECTION_PERIOD_DAYS = 7
MAYOR_TERM_DAYS = 7             # طول کل دوره شهرداری
MAYOR_ELECTION_WINDOW_DAYS = 3  # چند روز آخر دوره، خودکار انتخابات برگزار میشه
MAYOR_INACTIVE_DAYS = 5
PRISON_BASE_SECONDS = 1800
