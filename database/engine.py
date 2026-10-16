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
    """ساخت جدول‌ها و افزودن ستون‌های جدید به دیتابیس‌های قدیمی."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # create_all ستون جدید را به جدول موجود اضافه نمی‌کند.
        result = await conn.exec_driver_sql("PRAGMA table_info(users)")
        columns = {row[1] for row in result.fetchall()}

        if "loan_last_penalty_at" not in columns:
            await conn.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN loan_last_penalty_at DATETIME"
            )


async def wipe_db():
    """پاک کردن کامل دیتابیس و ساخت دوباره جدول‌ها (فقط برای دستور ری‌استارت مالک)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
