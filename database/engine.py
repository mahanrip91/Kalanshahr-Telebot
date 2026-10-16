"""
موتور اتصال به دیتابیس (SQLite + SQLAlchemy Async)
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from database.models import Base
from config import settings

os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)

engine = create_async_engine(f"sqlite+aiosqlite:///{settings.DB_PATH}", echo=False)

async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db():
    """ساخت تمام جدول‌ها در صورت نبودن"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def wipe_db():
    """پاک کردن کامل دیتابیس و ساخت دوباره جدول‌ها (فقط برای دستور ری‌استارت مالک)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
