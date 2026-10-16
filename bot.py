"""
فایل اصلی اجرای ربات کلان‌شهر
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from database.engine import init_db, async_session
from services.market_engine import seed_market
from services.scheduler import setup_scheduler
from core.middlewares import DBUserMiddleware
from core.menu_router import router as menu_priority_router

# ---------------- ایمپورت همه هندلرها ----------------
from handlers import start, profile, work, bank, loan, betting, property as property_handler
from handlers import shop, rewards, leaderboard, settings as settings_handler, admin, crime, help as help_handler
from handlers.market import stocks, crypto, forex
from handlers.city import activation, status, mayor, treasury, prison, admin_panel

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("kalanshahr")


async def main():
    logger.info("در حال آماده‌سازی دیتابیس...")
    await init_db()

    async with async_session() as session:
        await seed_market(session)
    logger.info("بازارهای مالی مقداردهی شدن.")

    bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    session=AiohttpSession(proxy="http://127.0.0.1:10819")
)
    dp = Dispatcher(storage=MemoryStorage())

    # میان‌افزار دیتابیس/کاربر روی تمام آپدیت‌ها
    dp.update.middleware(DBUserMiddleware())

    # ثبت روترها
    dp.include_router(admin.router)  # دستورات مالک باید زودتر از همه چک بشن (ری‌استارت، اخراج و...)
    dp.include_router(menu_priority_router)  # دکمه‌های اصلی همیشه اولویت دارن، حتی وسط یه فلوی نیمه‌کاره
    dp.include_router(start.router)
    dp.include_router(help_handler.router)
    dp.include_router(activation.router)
    dp.include_router(status.router)
    dp.include_router(mayor.router)
    dp.include_router(treasury.router)
    dp.include_router(prison.router)
    dp.include_router(admin_panel.router)

    dp.include_router(profile.router)
    dp.include_router(work.router)
    dp.include_router(bank.router)
    dp.include_router(loan.router)
    dp.include_router(betting.router)
    dp.include_router(crime.router)

    dp.include_router(stocks.router)
    dp.include_router(crypto.router)
    dp.include_router(forex.router)

    dp.include_router(property_handler.router)
    dp.include_router(shop.router)
    dp.include_router(rewards.router)
    dp.include_router(leaderboard.router)
    dp.include_router(settings_handler.router)

    scheduler = setup_scheduler(bot)

    logger.info("ربات کلان‌شهر در حال اجراست... 🏙️")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, polling_timeout=30)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("ربات متوقف شد.")
