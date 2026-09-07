import asyncio
import hmac
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .db import Base, SessionLocal, engine, get_db
from .models import Activity, Admin, Automation, Lead, Proposal
from .schemas import ActivityIn, AutomationPatchIn, BookingWebhookIn, LeadCreateIn, LeadPatchIn, LoginIn, ProposalPatchIn, PublicEnquiryIn
from .security import csrf_admin, current_admin, hash_password, make_session, verify_password
from .services import check_booking_availability, create_default_proposal, forward_to_booking, process_due_automations, schedule_proposal_followups, send_email, visitor_fingerprint


settings = get_settings()
ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=ROOT / "templates")
hits: dict[str, list[datetime]] = defaultdict(list)
login_failures: dict[str, list[datetime]] = defaultdict(list)


def bootstrap() -> None:
    if settings.environment == "production":
        unsafe = (
            "CHANGE_ME" in settings.session_secret
            or settings.session_secret == "development-only-change-me"
            or len(settings.session_secret) < 48
            or "CHANGE_ME" in settings.admin_password
            or len(settings.admin_password) < 12
        )
        if unsafe:
            raise RuntimeError("Refusing to start with unsafe production administrator or session credentials")
    settings.storage_root.mkdir(parents=True, exist_ok=True)
    settings.backup_root.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        admin = db.scalar(select(Admin).where(Admin.email == settings.admin_email))
        if not admin:
            db.add(Admin(email=settings.admin_email, password_hash=hash_password(settings.admin_password)))
            db.commit()


async def automation_loop() -> None:
    while True:
        await asyncio.sleep(max(30, settings.automation_scan_seconds))
        with SessionLocal() as db:
            process_due_automations(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap()
    task = asyncio.create_task(automation_loop())
    yield
    task.cancel()


app = FastAPI(title=settings.app_name, version="1.0.0", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data: https:; media-src 'self' https:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'self'"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def lead_json(lead: Lead, detail: bool = False) -> dict:
    data = {
        "id": lead.id, "couple_name": lead.couple_name, "primary_first_name": lead.primary_first_name,
        "external_booking_id": lead.external_booking_id,
        "partner_first_name": lead.partner_first_name, "email": lead.email, "phone": lead.phone,
        "event_date": lead.event_date.isoformat(), "venue": lead.venue, "package_interest": lead.package_interest,
        "referral_source": lead.referral_source, "availability": lead.availability, "stage": lead.stage,
        "estimated_value": float(lead.estimated_value or 0), "booking_sync_status": lead.booking_sync_status,
        "created_at": lead.created_at.isoformat(), "updated_at": lead.updated_at.isoformat(),
        "proposal": proposal_json(lead.proposal) if lead.proposal else None,
    }
    if detail:
        data.update({"venue_address": lead.venue_address, "landing_page": lead.landing_page, "campaign": lead.campaign,
                     "message": lead.message, "outcome_reason": lead.outcome_reason, "booking_sync_error": lead.booking_sync_error,
                     "activities": [activity_json(x) for x in sorted(lead.activities, key=lambda x: x.occurred_at, reverse=True)],
                     "automations": [automation_json(x) for x in sorted(lead.automations, key=lambda x: x.scheduled_for)]})
    return data


def proposal_json(item: Proposal) -> dict:
    return {"id": item.id, "slug": item.slug, "url": f"{settings.app_url.rstrip('/')}/p/{item.slug}/{item.access_token}",
            "headline": item.headline, "introduction": item.introduction, "personal_message": item.personal_message,
            "packages": item.packages or [], "testimonials": item.testimonials or [], "media": item.media or [],
            "published": item.published, "sent_at": item.sent_at.isoformat() if item.sent_at else None,
            "expires_at": item.expires_at.isoformat() if item.expires_at else None}


def activity_json(item: Activity) -> dict:
    return {"id": item.id, "kind": item.kind, "label": item.label, "details": item.details or {}, "occurred_at": item.occurred_at.isoformat()}


def automation_json(item: Automation) -> dict:
    return {"id": item.id, "kind": item.kind, "subject": item.subject, "body": item.body,
            "scheduled_for": item.scheduled_for.isoformat(), "approval_required": item.approval_required,
            "approved_at": item.approved_at.isoformat() if item.approved_at else None, "status": item.status,
            "sent_at": item.sent_at.isoformat() if item.sent_at else None, "error": item.error}


def load_lead(db: Session, lead_id: str) -> Lead:
    lead = db.scalar(select(Lead).where(Lead.id == lead_id).options(selectinload(Lead.proposal), selectinload(Lead.activities), selectinload(Lead.automations)))
    if not lead:
        raise HTTPException(404, "Enquiry not found")
    return lead


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name, "build": settings.build_version,
            "booking_connection_configured": bool(settings.booking_base_url),
            "booking_forwarding_enabled": settings.booking_enquiry_forwarding,
            "smtp_configured": bool(settings.smtp_host and settings.smtp_username and settings.smtp_password),
            "automation_send_enabled": settings.automation_send_enabled,
            "followup_approval_required": settings.followup_approval_required}


@app.post("/api/auth/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "unknown")
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)
    recent = [x for x in login_failures[ip] if x > cutoff]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many sign-in attempts. Please wait 15 minutes.")
    admin = db.scalar(select(Admin).where(Admin.email == str(payload.email).lower()))
    if not admin or not verify_password(payload.password, admin.password_hash):
        recent.append(datetime.now(timezone.utc))
        login_failures[ip] = recent
        raise HTTPException(401, "Email or password is incorrect")
    login_failures.pop(ip, None)
    token, csrf = make_session(admin)
    response.set_cookie("growth_session", token, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=settings.session_hours * 3600)
    return {"ok": True, "csrf_token": csrf, "email": admin.email}


@app.post("/api/auth/logout")
def logout(response: Response, _: Admin = Depends(csrf_admin)):
    response.delete_cookie("growth_session")
    return {"ok": True}


@app.get("/api/auth/me")
def me(request: Request, admin: Admin = Depends(current_admin)):
    return {"email": admin.email, "csrf_token": request.state.session_data["csrf"]}


@app.get("/api/public/availability")
def availability(date: str = Query(...)):
    try:
        event_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(422, "Use a valid date in YYYY-MM-DD format")
    return {"date": date, "status": check_booking_availability(event_date)}


def rate_limit(request: Request) -> None:
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "unknown")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = [x for x in hits[ip] if x > cutoff]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many enquiries. Please try again later.")
    recent.append(datetime.now(timezone.utc))
    hits[ip] = recent


def create_lead(payload: PublicEnquiryIn, request: Request, db: Session, should_forward: bool) -> Lead:
    if payload.website:
        raise HTTPException(400, "Unable to submit this enquiry")
    if not payload.privacy_agreed:
        raise HTTPException(422, "Please agree to the privacy notice")
    rate_limit(request)
    duplicate_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    duplicate = db.scalar(select(Lead).where(Lead.email == str(payload.email).lower(), Lead.event_date == payload.event_date, Lead.created_at >= duplicate_cutoff))
    if duplicate:
        return duplicate
    raw = payload.model_dump(mode="json")
    available = check_booking_availability(payload.event_date)
    lead = Lead(primary_first_name=payload.primary_first_name.strip(), partner_first_name=payload.partner_first_name.strip(),
                email=str(payload.email).lower(), phone=payload.phone, event_date=payload.event_date,
                venue=payload.location.strip(), venue_address=payload.venue_address,
                package_interest=payload.package_interest, referral_source=payload.heard_about_us,
                landing_page=payload.landing_page, campaign=payload.campaign, message=payload.message,
                availability=available)
    db.add(lead)
    db.flush()
    create_default_proposal(db, lead)
    db.add(Activity(lead_id=lead.id, kind="enquiry_received", label="Website enquiry received",
                    details={"source": lead.referral_source or "Not specified", "availability": available}))
    if should_forward:
        lead.booking_sync_status, lead.booking_sync_error = forward_to_booking(raw)
    db.commit()
    return load_lead(db, lead.id)


@app.post("/api/public/enquiries", status_code=201)
def public_enquiry(payload: PublicEnquiryIn, request: Request, db: Session = Depends(get_db)):
    lead = create_lead(payload, request, db, settings.booking_enquiry_forwarding)
    return {"ok": True, "message": "Thank you – your enquiry has arrived safely.", "availability": lead.availability}


@app.post("/api/integrations/booking/enquiry", status_code=201)
def booking_enquiry_webhook(payload: BookingWebhookIn, x_integration_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    if not settings.booking_webhook_key or not x_integration_key or not hmac.compare_digest(settings.booking_webhook_key, x_integration_key):
        raise HTTPException(401, "Integration key is missing or invalid")
    existing = db.scalar(select(Lead).where(Lead.external_booking_id == payload.booking_id))
    if existing:
        return {"ok": True, "duplicate_ignored": True, "lead_id": existing.id}
    availability = check_booking_availability(payload.event_date)
    lead = Lead(external_booking_id=payload.booking_id, primary_first_name=payload.primary_first_name.strip(),
                partner_first_name=payload.partner_first_name.strip(), email=str(payload.email).lower(), phone=payload.phone,
                event_date=payload.event_date, venue=payload.venue.strip(), venue_address=payload.venue_address,
                package_interest=payload.package_interest, referral_source=payload.referral_source,
                landing_page=payload.landing_page, campaign=payload.campaign, message=payload.message,
                availability=availability, booking_sync_status="source")
    db.add(lead)
    db.flush()
    create_default_proposal(db, lead)
    db.add(Activity(lead_id=lead.id, kind="enquiry_received", label="Booking-system enquiry received",
                    details={"source": lead.referral_source or "Not specified", "availability": availability}))
    db.commit()
    return {"ok": True, "lead_id": lead.id, "proposal_created": True}


@app.post("/api/admin/leads", status_code=201)
def admin_create_lead(payload: LeadCreateIn, request: Request, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    public_payload = PublicEnquiryIn(**payload.model_dump(exclude={"forward_to_booking"}))
    return lead_json(create_lead(public_payload, request, db, payload.forward_to_booking), True)


@app.get("/api/admin/dashboard")
def dashboard(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    leads = db.scalars(select(Lead).where(Lead.created_at >= month_start).options(selectinload(Lead.proposal), selectinload(Lead.activities)).order_by(Lead.updated_at.desc())).all()
    booked = [x for x in leads if x.stage == "booked"]
    opened = [x for x in leads if any(a.kind == "proposal_opened" for a in x.activities)]
    hot = sorted(leads, key=lambda x: sum(1 for a in x.activities if a.kind in {"proposal_opened", "package_viewed", "film_played", "booking_clicked"}), reverse=True)[:8]
    return {"metrics": {"new_enquiries": len(leads), "proposal_opened": len(opened), "bookings": len(booked),
                        "booked_value": float(sum((x.estimated_value or Decimal("0")) for x in booked))},
            "hot_leads": [lead_json(x) for x in hot],
            "actions": [{"kind": "approval", "count": db.scalar(select(func.count()).select_from(Automation).where(Automation.status == "scheduled", Automation.approval_required.is_(True), Automation.approved_at.is_(None))) or 0,
                         "label": "Follow-ups waiting for approval"}]}


@app.get("/api/admin/leads")
def list_leads(stage: str | None = None, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    stmt = select(Lead).options(selectinload(Lead.proposal)).order_by(Lead.updated_at.desc())
    if stage:
        stmt = stmt.where(Lead.stage == stage)
    return [lead_json(x) for x in db.scalars(stmt).all()]


@app.get("/api/admin/leads/{lead_id}")
def get_lead(lead_id: str, _: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    return lead_json(load_lead(db, lead_id), True)


@app.patch("/api/admin/leads/{lead_id}")
def patch_lead(lead_id: str, payload: LeadPatchIn, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    lead = load_lead(db, lead_id)
    before = lead.stage
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(lead, key, value)
    if lead.stage != before:
        db.add(Activity(lead_id=lead.id, kind="stage_changed", label=f"Moved from {before} to {lead.stage}"))
        if lead.stage in {"booked", "lost"}:
            for automation in lead.automations:
                if automation.status == "scheduled":
                    automation.status = "cancelled"
    db.commit()
    return lead_json(load_lead(db, lead_id), True)


@app.patch("/api/admin/leads/{lead_id}/proposal")
def patch_proposal(lead_id: str, payload: ProposalPatchIn, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    lead = load_lead(db, lead_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(lead.proposal, key, value)
    db.commit()
    return proposal_json(lead.proposal)


@app.post("/api/admin/leads/{lead_id}/proposal/publish")
def publish_proposal(lead_id: str, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    lead = load_lead(db, lead_id)
    lead.proposal.published = True
    lead.stage = "proposal"
    schedule_proposal_followups(db, lead)
    db.add(Activity(lead_id=lead.id, kind="proposal_published", label="Personal proposal published"))
    db.commit()
    return proposal_json(lead.proposal)


@app.post("/api/admin/leads/{lead_id}/proposal/send")
def email_proposal(lead_id: str, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    lead = load_lead(db, lead_id)
    if not lead.proposal.published:
        raise HTTPException(409, "Publish the proposal before emailing it")
    url = proposal_json(lead.proposal)["url"]
    subject = f"Your wedding photography information – {lead.primary_first_name} & {lead.partner_first_name}"
    body = f"Hi {lead.primary_first_name},\n\nThank you again for getting in touch about your wedding at {lead.venue}. I have prepared your personal wedding information here:\n\n{url}\n\nIf you have any questions, simply reply to this email.\n\nMark\nWeddings By Mark\n{settings.business_phone}"
    try:
        send_email(lead.email, subject, body)
    except Exception as exc:
        raise HTTPException(503, f"The proposal is published but the email could not be sent: {str(exc)}")
    lead.proposal.sent_at = datetime.now(timezone.utc)
    db.add(Activity(lead_id=lead.id, kind="proposal_sent", label="Personal proposal emailed"))
    db.commit()
    return {"ok": True, "sent_to": lead.email}


@app.patch("/api/admin/automations/{automation_id}")
def patch_automation(automation_id: str, payload: AutomationPatchIn, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    item = db.get(Automation, automation_id)
    if not item:
        raise HTTPException(404, "Follow-up not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    return automation_json(item)


@app.post("/api/admin/automations/{automation_id}/approve")
def approve_automation(automation_id: str, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    item = db.get(Automation, automation_id)
    if not item:
        raise HTTPException(404, "Follow-up not found")
    item.approved_at = datetime.now(timezone.utc)
    db.commit()
    return automation_json(item)


@app.get("/p/{slug}/{token}", response_class=HTMLResponse)
def public_proposal(slug: str, token: str, request: Request, db: Session = Depends(get_db)):
    item = db.scalar(select(Proposal).where(Proposal.slug == slug, Proposal.access_token == token, Proposal.published.is_(True)).options(selectinload(Proposal.lead)))
    if not item:
        raise HTTPException(404, "This proposal is not available")
    return templates.TemplateResponse(request=request, name="proposal.html", context={"proposal": item, "lead": item.lead,
                                      "booking_action_url": settings.booking_action_url, "business_phone": settings.business_phone})


@app.post("/api/public/proposals/{token}/activity", status_code=204)
def proposal_activity(token: str, payload: ActivityIn, request: Request, db: Session = Depends(get_db)):
    proposal = db.scalar(select(Proposal).where(Proposal.access_token == token, Proposal.published.is_(True)))
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    ip = forwarded or (request.client.host if request.client else "unknown")
    fingerprint = visitor_fingerprint(ip, request.headers.get("user-agent", ""))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    duplicate = db.scalar(select(Activity.id).where(Activity.lead_id == proposal.lead_id, Activity.kind == payload.kind,
                                                     Activity.label == payload.label, Activity.visitor_hash == fingerprint,
                                                     Activity.occurred_at >= cutoff))
    if not duplicate:
        db.add(Activity(lead_id=proposal.lead_id, kind=payload.kind, label=payload.label,
                        details=payload.details, visitor_hash=fingerprint))
        if payload.kind in {"package_viewed", "film_played", "booking_clicked"} and proposal.lead.stage not in {"booked", "lost"}:
            proposal.lead.stage = "engaged"
        db.commit()
    return Response(status_code=204)


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(ROOT / "static" / "login.html")


@app.get("/", include_in_schema=False)
def admin_page():
    return FileResponse(ROOT / "static" / "admin.html")
