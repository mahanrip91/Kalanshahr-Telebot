"""
موتور مرکزی بازارهای مالی:
- دیتای اولیه شرکت‌ها/کوین‌ها/ارزها
- نوسان دوره‌ای قیمت‌ها (شبیه‌سازی بازار واقعی)
"""
import random
from sqlalchemy import select
from database.models import Stock, Crypto, ForexAsset

STOCKS_SEED = [
    {"symbol": "FOLD", "name": "فولاد دیاره", "price": 12000, "volatility": 0.04},
    {"symbol": "NAFT", "name": "نفت شرق", "price": 28000, "volatility": 0.05},
    {"symbol": "BANK", "name": "بانک کلان‌شهر", "price": 8500, "volatility": 0.03},
    {"symbol": "TECH", "name": "فناوری آینده", "price": 15500, "volatility": 0.06},
    {"symbol": "FOOD", "name": "صنایع غذایی برکت", "price": 6200, "volatility": 0.025},
    {"symbol": "AUTO", "name": "خودروسازی پارس", "price": 9800, "volatility": 0.045},
    {"symbol": "TELE", "name": "مخابرات کلان‌شهر", "price": 11200, "volatility": 0.03},
    {"symbol": "CNST", "name": "ساختمانی البرز", "price": 7300, "volatility": 0.04},
    {"symbol": "MEDI", "name": "دارویی سلامت", "price": 13400, "volatility": 0.035},
    {"symbol": "ENRG", "name": "انرژی خورشیدی", "price": 16800, "volatility": 0.055},
]

CRYPTO_SEED = [
    {"symbol": "KBIT", "name": "کلان‌کوین", "price": 2_500_000, "volatility": 0.15},
    {"symbol": "SHRC", "name": "شهرکوین", "price": 180_000, "volatility": 0.18},
    {"symbol": "DYAR", "name": "دیارتوکن", "price": 45_000, "volatility": 0.20},
    {"symbol": "MOON", "name": "مون‌کوین", "price": 9_000, "volatility": 0.30},
    {"symbol": "STBL", "name": "استیبل‌کوین", "price": 60_000, "volatility": 0.02},
]

FOREX_SEED = [
    {"symbol": "USD", "name": "دلار آمریکا", "unit": "دلار", "price": 68000, "volatility": 0.015},
    {"symbol": "EUR", "name": "یورو", "unit": "یورو", "price": 74000, "volatility": 0.015},
    {"symbol": "GOLD", "name": "طلای ۱۸ عیار", "unit": "گرم", "price": 4_200_000, "volatility": 0.02},
    {"symbol": "COIN", "name": "سکه تمام بهار آزادی", "unit": "عدد", "price": 62_000_000, "volatility": 0.025},
]


async def seed_market(session):
    """اگه دیتای بازار خالی بود، مقداردهی اولیه میکنه"""
    result = await session.execute(select(Stock))
    if not result.scalars().first():
        for item in STOCKS_SEED:
            session.add(Stock(**item, previous_price=item["price"]))

    result = await session.execute(select(Crypto))
    if not result.scalars().first():
        for item in CRYPTO_SEED:
            session.add(Crypto(**item, previous_price=item["price"]))

    result = await session.execute(select(ForexAsset))
    if not result.scalars().first():
        for item in FOREX_SEED:
            session.add(ForexAsset(**item, previous_price=item["price"]))

    await session.commit()


async def fluctuate_market(session):
    """نوسان دوره‌ای قیمت همه دارایی‌ها - این تابع توسط زمان‌بند صدا زده میشه"""
    for model in (Stock, Crypto, ForexAsset):
        result = await session.execute(select(model))
        items = result.scalars().all()
        for item in items:
            item.previous_price = item.price
            change_pct = random.uniform(-item.volatility, item.volatility)
            # کمی گرایش به میانگین برای جلوگیری از رشد/سقوط بی‌نهایت
            new_price = item.price * (1 + change_pct)
            if new_price < item.price * 0.3:
                new_price = item.price * 0.3
            item.price = round(new_price, 2)
    await session.commit()
