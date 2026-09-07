from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uid() -> str:
    return str(uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    external_booking_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True, nullable=True)
    primary_first_name: Mapped[str] = mapped_column(String(100))
    partner_first_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    venue: Mapped[str] = mapped_column(String(240), index=True)
    venue_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    package_interest: Mapped[str | None] = mapped_column(String(160), nullable=True)
    referral_source: Mapped[str | None] = mapped_column(String(160), index=True, nullable=True)
    landing_page: Mapped[str | None] = mapped_column(Text, nullable=True)
    campaign: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    availability: Mapped[str] = mapped_column(String(30), default="Unknown")
    stage: Mapped[str] = mapped_column(String(30), default="new", index=True)
    outcome_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    estimated_value: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    booking_sync_status: Mapped[str] = mapped_column(String(30), default="not_requested")
    booking_sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    privacy_agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    proposal: Mapped["Proposal | None"] = relationship(back_populates="lead", cascade="all, delete-orphan", uselist=False)
    activities: Mapped[list["Activity"]] = relationship(back_populates="lead", cascade="all, delete-orphan")
    automations: Mapped[list["Automation"]] = relationship(back_populates="lead", cascade="all, delete-orphan")

    @property
    def couple_name(self) -> str:
        return f"{self.primary_first_name} & {self.partner_first_name}"


class BookingEventReceipt(Base):
    """Idempotency receipt for a booking-system snapshot."""
    __tablename__ = "booking_event_receipts"
    event_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    booking_id: Mapped[str] = mapped_column(String(100), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    access_token: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    headline: Mapped[str] = mapped_column(String(240))
    introduction: Mapped[str] = mapped_column(Text)
    personal_message: Mapped[str] = mapped_column(Text, default="")
    packages: Mapped[list] = mapped_column(JSON, default=list)
    testimonials: Mapped[list] = mapped_column(JSON, default=list)
    media: Mapped[list] = mapped_column(JSON, default=list)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    lead: Mapped[Lead] = relationship(back_populates="proposal")


class Activity(Base):
    __tablename__ = "activities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    label: Mapped[str] = mapped_column(String(240))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    visitor_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    lead: Mapped[Lead] = relationship(back_populates="activities")


class Automation(Base):
    __tablename__ = "automations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(60), index=True)
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="scheduled", index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lead: Mapped[Lead] = relationship(back_populates="automations")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
