"""
زمان‌بند وظایف پس‌زمینه:
- نوسان بازار مالی هر چند دقیقه
- بررسی سررسید وام و اعلان
- بررسی غیرفعالی شهردار و عزل خودکار
- شروع خودکار انتخابات (۳ روز پایانی دوره شهردار، یا وقتی شهر شهردار نداره)
- پایان دوره انتخابات
"""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from database.engine import async_session
from database.models import User, City, Candidate
from services.market_engine import fluctuate_market
from handlers.city.mayor import ensure_election_state
from config import MAYOR_INACTIVE_DAYS

logger = logging.getLogger("scheduler")


async def job_fluctuate_market():
    async with async_session() as session:
        await fluctuate_market(session)
    logger.info("قیمت بازارها بروزرسانی شد.")


async def job_check_loans(bot):
    async with async_session() as session:
        now = datetime.utcnow()
        result = await session.execute(
            select(User).where(User.loan_amount > 0, User.loan_due.isnot(None))
        )
        users = result.scalars().all()
        for user in users:
            if not user.loan_due:
                continue
            hours_left = (user.loan_due - now).total_seconds() / 3600
            # هشدار ۲۴ ساعت قبل از سررسید
            if 0 < hours_left <= 24:
                try:
                    await bot.send_message(
                        user.telegram_id,
                        "⚠️ <b>یادآوری وام</b>\nکمتر از ۲۴ ساعت تا سررسید وامت مونده! "
                        "یادت نره از بخش بانک تسویه کنی وگرنه جریمه دیرکرد میخوری.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass


async def job_check_mayors(bot):
    """اگه شهردار غیرفعال بود، عزل خودکار و شروع دوباره انتخابات"""
    async with async_session() as session:
        now = datetime.utcnow()
        result = await session.execute(select(City).where(City.mayor_telegram_id.isnot(None)))
        cities = result.scalars().all()
        for city in cities:
            if not city.mayor_last_active:
                continue
            days_inactive = (now - city.mayor_last_active).days
            if days_inactive >= MAYOR_INACTIVE_DAYS:
                city.mayor_telegram_id = None
                city.mayor_elected_at = None
                await session.commit()
                try:
                    await bot.send_message(
                        city.chat_id,
                        "🏛️ <b>شهردار به دلیل غیرفعالی از سمتش عزل شد!</b>\n"
                        "انتخابات جدید به‌زودی و به‌طور خودکار شروع میشه.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass


async def job_auto_start_elections(bot):
    """اگه دوره شهردار به ۳ روز پایانی رسیده باشه، یا شهر اصلاً شهردار نداره،
    خودکار وارد فاز انتخابات میشه - بدون نیاز به هیچ دستور دستی."""
    async with async_session() as session:
        result = await session.execute(
            select(City).where(City.is_active == True, City.election_active == False)
        )
        cities = result.scalars().all()
        for city in cities:
            await ensure_election_state(session, city)
            if city.election_active:
                try:
                    await bot.send_message(
                        city.chat_id,
                        "🗳️ <b>انتخابات شهرداری شروع شد!</b>\n"
                        "از «🏛️ شهرداری» می‌تونید کاندید بشید یا رای بدید.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass


async def job_check_elections(bot):
    """پایان دوره انتخابات و اعلام برنده"""
    async with async_session() as session:
        now = datetime.utcnow()
        result = await session.execute(
            select(City).where(City.election_active == True, City.election_ends_at <= now)
        )
        cities = result.scalars().all()
        for city in cities:
            cand_result = await session.execute(
                select(Candidate).where(Candidate.city_id == city.id).order_by(Candidate.votes.desc())
            )
            candidates = cand_result.scalars().all()
            city.election_active = False

            if candidates and candidates[0].votes > 0:
                winner = candidates[0]
                city.mayor_telegram_id = winner.telegram_id
                city.mayor_elected_at = now
                city.mayor_last_active = now
                await session.commit()
                try:
                    await bot.send_message(
                        city.chat_id,
                        f"🎉 <b>انتخابات تموم شد!</b>\n\n"
                        f"👑 شهردار جدید کلان‌شهر: <b>{winner.name}</b>\n"
                        f"با {winner.votes} رای انتخاب شد!",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass
            else:
                await session.commit()
                try:
                    await bot.send_message(
                        city.chat_id,
                        "😐 <b>انتخابات بدون برنده تموم شد!</b>\nهیچ‌کس رای کافی نگرفت. دوباره کاندید بشید.",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass


def setup_scheduler(bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    # اولین نوسان بلافاصله بعد از بالا اومدن ربات هم اجرا بشه، وگرنه تا ۱۰ دقیقه اول هیچ تغییری دیده نمیشه
    scheduler.add_job(job_fluctuate_market, "interval", minutes=5, id="market_fluctuate",
                       next_run_time=datetime.utcnow())
    scheduler.add_job(job_check_loans, "interval", hours=1, args=[bot], id="check_loans")
    scheduler.add_job(job_check_mayors, "interval", hours=6, args=[bot], id="check_mayors")
    scheduler.add_job(job_auto_start_elections, "interval", minutes=15, args=[bot], id="auto_start_elections")
    scheduler.add_job(job_check_elections, "interval", minutes=5, args=[bot], id="check_elections")
    scheduler.start()
    return scheduler
