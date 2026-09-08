from functools import lru_cache
from pathlib import Path
import os

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str = os.getenv("APP_NAME", "Weddings By Mark Growth Engine")
    app_url: str = os.getenv("APP_URL", "http://localhost:30110")
    environment: str = os.getenv("APP_ENV", "production")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./growth-engine.db")
    storage_root: Path = Path(os.getenv("STORAGE_ROOT", "./storage"))
    backup_root: Path = Path(os.getenv("BACKUP_ROOT", "./backups"))
    session_secret: str = os.getenv("SESSION_SECRET", "development-only-change-me")
    admin_email: str = os.getenv("ADMIN_EMAIL", "mark@perfectweddingsbymark.uk").lower()
    admin_password: str = os.getenv("ADMIN_PASSWORD", "ChangeMe-now")
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "true").lower() == "true"
    session_hours: int = int(os.getenv("SESSION_HOURS", "12"))
    booking_base_url: str = os.getenv("BOOKING_BASE_URL", "https://booking.weddingsbymark.uk").rstrip("/")
    booking_enquiry_forwarding: bool = os.getenv("BOOKING_ENQUIRY_FORWARDING", "false").lower() == "true"
    booking_webhook_key: str = os.getenv("BOOKING_WEBHOOK_KEY", "")
    booking_timeout_seconds: int = int(os.getenv("BOOKING_TIMEOUT_SECONDS", "12"))
    booking_action_url: str = os.getenv("BOOKING_ACTION_URL", "https://booking.weddingsbymark.uk")
    business_phone: str = os.getenv("BUSINESS_PHONE", "07981 150073")
    automation_send_enabled: bool = os.getenv("AUTOMATION_SEND_ENABLED", "false").lower() == "true"
    automation_scan_seconds: int = int(os.getenv("AUTOMATION_SCAN_SECONDS", "60"))
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "465"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    smtp_use_ssl: bool = os.getenv("SMTP_USE_SSL", "true").lower() == "true"
    email_from_name: str = os.getenv("EMAIL_FROM_NAME", "Mark at Weddings By Mark")
    followup_approval_required: bool = os.getenv("FOLLOWUP_APPROVAL_REQUIRED", "true").lower() == "true"
    proposal_days_valid: int = int(os.getenv("PROPOSAL_DAYS_VALID", "7"))
    build_version: str = "2026.09.08-fill-my-dates-v1.3.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
