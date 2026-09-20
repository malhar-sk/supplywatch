from datetime import date, datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from core.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, future=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    primary_producers: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RawSignal(Base):
    __tablename__ = "raw_signals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DisruptionScore(Base):
    __tablename__ = "disruption_scores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    factors: Mapped[dict] = mapped_column(JSONB)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tier: Mapped[str] = mapped_column(String(20), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiUsageCounter(Base):
    __tablename__ = "api_usage_counters"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"), index=True)
    day: Mapped[str] = mapped_column(String(10), index=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"), index=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    webhook_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AlertHistory(Base):
    __tablename__ = "alert_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("alert_subscriptions.id"), index=True)
    score_at_trigger: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str] = mapped_column(Text)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DailySnapshot(Base):
    """One row per (material, day). Written by the daily snapshot job.

    Unique on (material_id, snapshot_date) so the job's upsert is
    idempotent: re-running it for a date that already has a row updates
    that row instead of inserting a duplicate.
    """

    __tablename__ = "daily_snapshots"
    __table_args__ = (UniqueConstraint("material_id", "snapshot_date", name="uq_daily_snapshot_material_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("materials.id"), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    factors: Mapped[dict] = mapped_column(JSONB)
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


class GuestDemoSnapshot(Base):
    """Guest-mode snapshot table, deliberately isolated from per-user data.

    Keyed on material_name (plain string) rather than a Material FK, and
    written to only by the guest snapshot job, so there is no join path
    from guest traffic into the authenticated-user schema.
    """

    __tablename__ = "guest_demo_snapshots"
    __table_args__ = (UniqueConstraint("material_name", "snapshot_date", name="uq_guest_snapshot_material_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    material_name: Mapped[str] = mapped_column(String(120), index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    trend: Mapped[str] = mapped_column(String(16), default="unchanged")
    summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
