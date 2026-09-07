from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class PublicEnquiryIn(BaseModel):
    primary_first_name: str = Field(min_length=1, max_length=100)
    partner_first_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    event_date: date
    location: str = Field(min_length=1, max_length=240)
    venue_address: str | None = Field(default=None, max_length=1000)
    package_interest: str | None = Field(default=None, max_length=160)
    heard_about_us: str | None = Field(default=None, max_length=160)
    message: str | None = Field(default=None, max_length=5000)
    landing_page: str | None = Field(default=None, max_length=2000)
    campaign: str | None = Field(default=None, max_length=200)
    privacy_agreed: bool
    website: str = Field(default="", max_length=200)


class LeadCreateIn(PublicEnquiryIn):
    forward_to_booking: bool = False


class IntelligenceIn(BaseModel):
    version: int = 1
    source_created_at: datetime
    archived: bool = False
    suppressed: bool = False
    is_test: bool = False
    booking_status: str = Field(max_length=30)
    deposit_paid: bool = False
    quote_accepted: bool = False
    quote_sent_at: datetime | None = None
    last_contact_at: datetime | None = None
    quote_link_at: datetime | None = None
    quote_link_count: int = Field(default=0, ge=0)
    last_incoming_at: datetime | None = None
    mail_status: Literal['not_configured', 'recent_inbox', 'unavailable'] = 'not_configured'
    mail_checked_at: datetime | None = None


class BookingWebhookIn(BaseModel):
    intelligence: IntelligenceIn | None = None
    event_id: str | None = Field(default=None, min_length=8, max_length=160)
    booking_id: str = Field(min_length=1, max_length=100)
    primary_first_name: str = Field(min_length=1, max_length=100)
    partner_first_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    event_date: date
    venue: str = Field(min_length=1, max_length=240)
    venue_address: str | None = Field(default=None, max_length=1000)
    package_interest: str | None = Field(default=None, max_length=160)
    referral_source: str | None = Field(default=None, max_length=160)
    landing_page: str | None = Field(default=None, max_length=2000)
    campaign: str | None = Field(default=None, max_length=200)
    message: str | None = Field(default=None, max_length=5000)
    booking_status: Literal["enquiry", "quoted", "confirmed", "in_progress", "completed", "cancelled"] = "enquiry"
    quote_accepted: bool = False
    quote_status: str | None = Field(default=None, max_length=30)
    quote_items: list[dict] = Field(default_factory=list, max_length=100)
    deposit_paid: bool = False
    deposit_amount: Decimal = Field(default=Decimal("0"), ge=0)
    estimated_value: Decimal = Field(default=Decimal("0"), ge=0)
    is_test: bool = False
    received_at: datetime | None = None
    updated_at: datetime | None = None


class LeadPatchIn(BaseModel):
    stage: Literal["new", "qualified", "proposal", "engaged", "booked", "lost"] | None = None
    package_interest: str | None = Field(default=None, max_length=160)
    estimated_value: Decimal | None = Field(default=None, ge=0)
    outcome_reason: str | None = Field(default=None, max_length=160)


class ProposalPatchIn(BaseModel):
    headline: str | None = Field(default=None, min_length=1, max_length=240)
    introduction: str | None = Field(default=None, min_length=1, max_length=5000)
    personal_message: str | None = Field(default=None, max_length=5000)
    packages: list[dict] | None = None
    testimonials: list[dict] | None = None
    media: list[dict] | None = None


class ActivityIn(BaseModel):
    kind: Literal["proposal_opened", "package_viewed", "film_played", "booking_clicked", "consultation_clicked"]
    label: str = Field(min_length=1, max_length=240)
    details: dict = Field(default_factory=dict)


class AutomationPatchIn(BaseModel):
    subject: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, min_length=1, max_length=10000)
    scheduled_for: datetime | None = None
