"""
تمام مدل‌های دیتابیس کلان‌شهر
"""
from datetime import datetime
from sqlalchemy import (
    BigInteger, Integer, Float, String, Boolean, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ==================== کاربر ====================

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str] = mapped_column(String(128), default="")

    level: Mapped[int] = mapped_column(Integer, default=1)
    xp: Mapped[int] = mapped_column(Integer, default=0)

    cash: Mapped[float] = mapped_column(Float, default=5000)
    bank_balance: Mapped[float] = mapped_column(Float, default=0)
    account_number: Mapped[str] = mapped_column(String(32), nullable=True, unique=True)

    loan_amount: Mapped[float] = mapped_column(Float, default=0)
    loan_due: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    job: Mapped[str] = mapped_column(String(64), nullable=True)
    job_level: Mapped[int] = mapped_column(Integer, default=1)
    last_work: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    last_daily: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    daily_streak: Mapped[int] = mapped_column(Integer, default=0)

    last_bet: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    bet_today_total: Mapped[float] = mapped_column(Float, default=0)
    bet_reset_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    bank_deposit_today: Mapped[float] = mapped_column(Float, default=0)
    bank_deposit_reset: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    referred_by: Mapped[int] = mapped_column(BigInteger, nullable=True)

    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    banned_reason: Mapped[str] = mapped_column(String(255), nullable=True)
    prison_until: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    prison_reason: Mapped[str] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def total_wealth(self) -> float:
        return self.cash + self.bank_balance


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    type: Mapped[str] = mapped_column(String(64))
    amount: Mapped[float] = mapped_column(Float)
    description: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GiftCode(Base):
    __tablename__ = "gift_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    amount: Mapped[float] = mapped_column(Float)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    used_by_ids: Mapped[str] = mapped_column(Text, default="")  # comma separated telegram_ids
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ==================== بازارهای مالی ====================

class Stock(Base):
    __tablename__ = "stocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    price: Mapped[float] = mapped_column(Float)
    previous_price: Mapped[float] = mapped_column(Float, default=0)
    volatility: Mapped[float] = mapped_column(Float, default=0.05)


class StockHolding(Base):
    __tablename__ = "stock_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"))
    amount: Mapped[float] = mapped_column(Float, default=0)
    avg_buy_price: Mapped[float] = mapped_column(Float, default=0)


class Crypto(Base):
    __tablename__ = "cryptos"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    price: Mapped[float] = mapped_column(Float)
    previous_price: Mapped[float] = mapped_column(Float, default=0)
    volatility: Mapped[float] = mapped_column(Float, default=0.12)


class CryptoHolding(Base):
    __tablename__ = "crypto_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    crypto_id: Mapped[int] = mapped_column(ForeignKey("cryptos.id"))
    amount: Mapped[float] = mapped_column(Float, default=0)
    avg_buy_price: Mapped[float] = mapped_column(Float, default=0)


class ForexAsset(Base):
    """دلار، یورو، طلا و..."""
    __tablename__ = "forex_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    unit: Mapped[str] = mapped_column(String(32), default="واحد")
    price: Mapped[float] = mapped_column(Float)
    previous_price: Mapped[float] = mapped_column(Float, default=0)
    volatility: Mapped[float] = mapped_column(Float, default=0.03)


class ForexHolding(Base):
    __tablename__ = "forex_holdings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("forex_assets.id"))
    amount: Mapped[float] = mapped_column(Float, default=0)
    avg_buy_price: Mapped[float] = mapped_column(Float, default=0)


# ==================== املاک و مغازه ====================

class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    zone: Mapped[str] = mapped_column(String(64))
    ptype: Mapped[str] = mapped_column(String(32))
    level: Mapped[int] = mapped_column(Integer, default=1)
    purchase_price: Mapped[float] = mapped_column(Float)
    hourly_income: Mapped[float] = mapped_column(Float)
    last_collect: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    capital: Mapped[float] = mapped_column(Float, default=0)
    inventory_count: Mapped[int] = mapped_column(Integer, default=0)
    inventory_value: Mapped[float] = mapped_column(Float, default=0)
    total_profit: Mapped[float] = mapped_column(Float, default=0)
    employees: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


# ==================== کلان‌شهر (گروه) ====================

class City(Base):
    """هر گروه تلگرامی که فعال بشه یه شهره"""
    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), default="")

    status: Mapped[str] = mapped_column(String(32), default="کویر")
    treasury: Mapped[float] = mapped_column(Float, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)

    mayor_telegram_id: Mapped[int] = mapped_column(BigInteger, nullable=True)
    mayor_elected_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    mayor_last_active: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    tax_rate: Mapped[float] = mapped_column(Float, default=0.0)

    election_active: Mapped[bool] = mapped_column(Boolean, default=False)
    election_ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    current_round: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    name: Mapped[str] = mapped_column(String(128))
    votes: Mapped[int] = mapped_column(Integer, default=0)
    election_round: Mapped[int] = mapped_column(Integer, default=1)


class Vote(Base):
    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    voter_telegram_id: Mapped[int] = mapped_column(BigInteger)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    election_round: Mapped[int] = mapped_column(Integer, default=1)


class CityContribution(Base):
    """تاریخچه کمک‌های مالی به خزانه شهر"""
    __tablename__ = "city_contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))
    telegram_id: Mapped[int] = mapped_column(BigInteger)
    amount: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
