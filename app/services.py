import hashlib
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import Activity, Automation, Lead, Proposal, Setting


settings = get_settings()

DEFAULT_PACKAGES = [
    {"code": "half-day", "name": "Half Day Photography", "price": 475, "description": "Ceremony, family photographs, relaxed couple portraits and candid coverage, with 300+ photographs in a private online gallery."},
    {"code": "silver", "name": "Silver – Full Day Photography", "price": 699, "description": "Up to eight hours from bridal preparation to the first dance, 600+ photographs, private gallery, guest QR uploads and a wedding album."},
    {"code": "gold", "name": "Gold – Photography & Highlight Film", "price": 899, "description": "Full-day photography plus a 5–7 minute highlight film and drone coverage where permitted and weather allows."},
    {"code": "platinum", "name": "Platinum – Complete Photo & Video", "price": 1350, "description": "Full-day photography, highlight film, full ceremony and speeches, drone coverage and a two-person team."},
    {"code": "ultimate", "name": "Ultimate Wedding Collection", "price": 1799, "description": "Complete photography and video coverage, drone where permitted, Selfie Booth and three 12×12 wedding albums."},
]

DEFAULT_TESTIMONIALS = []  # Only verified, owner-supplied reviews may be published.


def get_package_catalogue(db: Session) -> list[dict]:
    item = db.get(Setting, "package_catalogue")
    packages = (item.value or {}).get("packages") if item else None
    return packages if isinstance(packages, list) and packages else DEFAULT_PACKAGES


def check_booking_availability(event_date) -> str:
    query = urlencode({"date": event_date.isoformat()})
    request = Request(f"{settings.booking_base_url}/api/public/availability?{query}", headers={"User-Agent": "WBM-Growth-Engine/1.0"})
    try:
        with urlopen(request, timeout=settings.booking_timeout_seconds) as response:
            value = response.read(100).decode().strip()
            return value if value in {"Available", "Booked", "Unavailable"} else "Unknown"
    except (HTTPError, URLError, TimeoutError):
        return "Unknown"


def forward_to_booking(payload: dict, growth_lead_id: str) -> tuple[str, str | None, str | None]:
    if not settings.booking_enquiry_forwarding:
        return "disabled", None, None
    booking_payload = {
        "event_id": f"growth-enquiry:{growth_lead_id}",
        "growth_lead_id": growth_lead_id,
        "primary_first_name": payload["primary_first_name"],
        "partner_first_name": payload["partner_first_name"],
        "email": payload["email"],
        "phone": payload.get("phone"),
        "event_date": str(payload["event_date"]),
        "venue": payload["location"],
        "venue_address": payload.get("venue_address"),
        "package_interest": payload.get("package_interest"),
        "message": payload.get("message"),
        "referral_source": payload.get("heard_about_us") or "Not specified",
        "is_test": False,
    }
    request = Request(
        f"{settings.booking_base_url}/api/integrations/growth/enquiry",
        data=json.dumps(booking_payload).encode(),
        headers={"Content-Type": "application/json", "X-Integration-Key": settings.booking_webhook_key,
                 "User-Agent": "WBM-Growth-Engine/1.0.3"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.booking_timeout_seconds) as response:
            if 200 <= response.status < 300:
                result = json.loads(response.read().decode("utf-8"))
                return "synced", None, result.get("booking_id")
            return "failed", f"Booking system returned HTTP {response.status}", None
    except HTTPError as exc:
        detail = exc.read(500).decode(errors="replace")
        return "failed", f"HTTP {exc.code}: {detail}"[:1000], None
    except (URLError, TimeoutError) as exc:
        return "failed", str(exc)[:1000], None


def create_default_proposal(db: Session, lead: Lead) -> Proposal:
    import secrets
    import re

    base = re.sub(r"[^a-z0-9]+", "-", f"{lead.primary_first_name}-{lead.partner_first_name}").strip("-")
    proposal = Proposal(
        lead_id=lead.id,
        slug=f"{base}-{secrets.token_hex(3)}",
        access_token=secrets.token_urlsafe(24),
        headline=f"Your wedding, {lead.primary_first_name} & {lead.partner_first_name}",
        introduction=f"Thank you for asking me about your wedding at {lead.venue}. Please check the date status below and contact me before making plans.",
        personal_message="I would love to hear a little more about the day you are planning. Everything below can be tailored around the two of you.",
        packages=get_package_catalogue(db),
        testimonials=DEFAULT_TESTIMONIALS,
        media=[],
        expires_at=None,
    )
    db.add(proposal)
    db.flush()
    return proposal


def schedule_proposal_followups(db: Session, lead: Lead) -> None:
    if not lead.proposal.sent_at:
        return
    now = lead.proposal.sent_at
    proposal_url = f"{settings.app_url.rstrip('/')}/p/{lead.proposal.slug}/{lead.proposal.access_token}"
    rows = [
        ("followup_24h", now + timedelta(hours=24), f"Just checking you received your wedding information", f"Hi {lead.primary_first_name},\n\nI just wanted to make sure the wedding information I sent arrived safely. You can return to it here:\n\n{proposal_url}\n\nThere is absolutely no pressure. If you have any questions, simply reply and I will be happy to help.\n\nMark\nWeddings By Mark"),
        ("followup_3d", now + timedelta(days=3), f"Any questions about your wedding photography?", f"Hi {lead.primary_first_name},\n\nI hope the wedding planning is going well. I wanted to check whether you had any questions about the packages or how I work on the day.\n\nYour information is here:\n{proposal_url}\n\nMark\nWeddings By Mark"),
        ("proposal_expiry", now + timedelta(days=max(1, settings.proposal_days_valid - 1)), "Your Weddings By Mark proposal", f"Hi {lead.primary_first_name},\n\nA quick note to let you know that your proposal is due to expire tomorrow. If you need a little longer or would like to discuss anything, just reply to this email.\n\n{proposal_url}\n\nMark\nWeddings By Mark"),
    ]
    for kind, scheduled_for, subject, body in rows:
        exists = db.scalar(select(Automation.id).where(Automation.lead_id == lead.id, Automation.kind == kind))
        if not exists:
            db.add(Automation(lead_id=lead.id, kind=kind, subject=subject, body=body, scheduled_for=scheduled_for, approval_required=settings.followup_approval_required))


def send_email(to_email: str, subject: str, body: str) -> None:
    if not (settings.smtp_host and settings.smtp_username and settings.smtp_password):
        raise RuntimeError("SMTP is not configured")
    message = EmailMessage()
    message["From"] = f"{settings.email_from_name} <{settings.smtp_username}>"
    message["To"] = to_email
    message["Subject"] = subject
    message["Reply-To"] = settings.smtp_username
    message.set_content(body)
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20, context=ssl.create_default_context()) as server:
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)


def process_due_automations(db: Session) -> int:
    if not settings.automation_send_enabled:
        return 0
    now = datetime.now(timezone.utc)
    items = db.scalars(select(Automation).where(Automation.status == "scheduled", Automation.scheduled_for <= now).limit(20)).all()
    sent = 0
    for item in items:
        if item.approval_required and not item.approved_at:
            continue
        if item.lead.stage in {"booked", "lost"}:
            item.status = "cancelled"
            continue
        try:
            item.attempts += 1
            send_email(item.lead.email, item.subject, item.body)
            item.status = "sent"
            item.sent_at = now
            item.error = None
            db.add(Activity(lead_id=item.lead_id, kind="email_sent", label=f"{item.kind.replace('_', ' ').title()} sent"))
            sent += 1
        except Exception as exc:
            item.error = str(exc)[:1000]
            item.status = "failed" if item.attempts >= 3 else "scheduled"
            item.scheduled_for = now + timedelta(minutes=60)
    db.commit()
    return sent


def visitor_fingerprint(ip: str, user_agent: str) -> str:
    value = f"{settings.session_secret}|{ip}|{user_agent}".encode()
    return hashlib.sha256(value).hexdigest()
