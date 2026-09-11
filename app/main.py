import asyncio
from contextlib import suppress
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
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session, selectinload

from .config import get_settings
from .intelligence import router as intelligence_router
from .gaps import router as gaps_router
from .planning import router as planning_router
from .website import match_attribution, router as website_router, website_loop
from .account import router as account_router
from .db import Base, SessionLocal, engine, get_db
from .models import Activity, Admin, Automation, BookingEventReceipt, Lead, Proposal, BookingInsight
from .schemas import ActivityIn, AutomationPatchIn, BookingWebhookIn, LeadCreateIn, LeadPatchIn, LoginIn, ProposalPatchIn, PublicEnquiryIn
from .security import csrf_admin, current_admin, hash_password, make_session, verify_password
from .services import check_booking_availability, forward_to_booking, visitor_fingerprint


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
    columns = {column["name"] for column in inspect(engine).get_columns("leads")}
    admin_columns = {column["name"] for column in inspect(engine).get_columns("admins")}
    website_visit_columns = {column["name"] for column in inspect(engine).get_columns("website_visits")}
    additions = {
        "deposit_amount": "NUMERIC(10, 2)",
        "quote_status": "VARCHAR(30)",
        "quote_items": "JSON",
        "website_visit_id": "VARCHAR(64)",
        "is_test": "BOOLEAN NOT NULL DEFAULT FALSE",
    }
    with engine.begin() as connection:
        if "session_version" not in admin_columns:
            connection.execute(text("ALTER TABLE admins ADD COLUMN session_version INTEGER NOT NULL DEFAULT 1"))
        for name, sql_type in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE leads ADD COLUMN {name} {sql_type}"))
        if "landing_path" not in website_visit_columns:
            connection.execute(text("ALTER TABLE website_visits ADD COLUMN landing_path VARCHAR(200)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_leads_website_visit_id ON leads (website_visit_id)"))
    with SessionLocal() as db:
        admin = db.scalar(select(Admin).where(Admin.email == settings.admin_email))
        if not admin:
            db.add(Admin(email=settings.admin_email, password_hash=hash_password(settings.admin_password)))
            db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    bootstrap()
    website_task = asyncio.create_task(website_loop())
    try:
        yield
    finally:
        website_task.cancel()
        with suppress(asyncio.CancelledError):
            await website_task


app = FastAPI(title=settings.app_name, version="1.6.0", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.include_router(intelligence_router)
app.include_router(gaps_router)
app.include_router(planning_router)
app.include_router(website_router)
app.include_router(account_router)


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
    booking_record_url = settings.booking_action_url.rstrip("/")
    if lead.external_booking_id:
        booking_record_url += f"/bookings/{lead.external_booking_id}/overview"
    data = {
        "id": lead.id, "couple_name": lead.couple_name, "primary_first_name": lead.primary_first_name,
        "external_booking_id": lead.external_booking_id,
        "partner_first_name": lead.partner_first_name, "email": lead.email, "phone": lead.phone,
        "event_date": lead.event_date.isoformat(), "venue": lead.venue, "package_interest": lead.package_interest,
        "referral_source": lead.referral_source, "availability": lead.availability, "stage": lead.stage,
        "estimated_value": float(lead.estimated_value or 0), "deposit_amount": float(lead.deposit_amount or 0),
        "quote_status": lead.quote_status, "quote_items": lead.quote_items or [],
        "booking_sync_status": lead.booking_sync_status,
        "booking_record_url": booking_record_url,
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
            "automation_send_enabled": False,
            "client_communications_owner": "booking_system",
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


def create_lead(payload: PublicEnquiryIn, request: Request, db: Session, should_forward: bool,
                origin: str = "website") -> Lead:
    if payload.website:
        raise HTTPException(400, "Unable to submit this enquiry")
    if not payload.privacy_agreed:
        raise HTTPException(422, "Please agree to the privacy notice")
    if origin == "website":
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
    label = "Manual enquiry added" if origin == "manual" else "Website enquiry received"
    db.add(Activity(lead_id=lead.id, kind="enquiry_received", label=label,
                    details={"source": lead.referral_source or "Not specified", "availability": available}))
    if should_forward:
        lead.booking_sync_status = "pending"
        db.commit()  # Persist the enquiry before making an external request.
        lead.booking_sync_status, lead.booking_sync_error, booking_id = forward_to_booking(raw, lead.id)
        if booking_id:
            lead.external_booking_id = booking_id
    db.commit()
    return load_lead(db, lead.id)


@app.post("/api/public/enquiries", status_code=201)
def public_enquiry(payload: PublicEnquiryIn, request: Request, db: Session = Depends(get_db)):
    lead = create_lead(payload, request, db, False, "website")
    return {"ok": True, "message": "Thank you – your enquiry has arrived safely.", "availability": lead.availability}


def require_booking_key(x_integration_key: str | None) -> None:
    if not settings.booking_webhook_key or not x_integration_key or not hmac.compare_digest(settings.booking_webhook_key, x_integration_key):
        raise HTTPException(401, "Integration key is missing or invalid")


@app.get("/api/integrations/booking/health")
def booking_integration_health(x_integration_key: str | None = Header(default=None)):
    require_booking_key(x_integration_key)
    return {"ok": True, "app": settings.app_name, "direction": "booking-to-growth"}


def booking_stage(payload: BookingWebhookIn) -> str:
    if payload.booking_status == "cancelled":
        return "lost"
    if payload.booking_status in {"confirmed", "in_progress", "completed"} or payload.deposit_paid:
        return "booked"
    if payload.quote_accepted:
        return "engaged"
    if payload.booking_status == "quoted":
        return "qualified"
    return "new"


def merged_booking_stage(current: str, incoming: str) -> str:
    """Do not let an ordinary booking edit erase stronger Growth engagement."""
    if incoming in {"booked", "lost"}:
        return incoming
    if current in {"booked", "lost"}:
        return incoming  # An authoritative booking reopen reverses a terminal state.
    rank = {"new": 0, "qualified": 1, "proposal": 2, "engaged": 3}
    return incoming if rank.get(incoming, 0) >= rank.get(current, 0) else current


@app.post("/api/integrations/booking/enquiry", status_code=201)
def booking_enquiry_webhook(payload: BookingWebhookIn, x_integration_key: str | None = Header(default=None), db: Session = Depends(get_db)):
    require_booking_key(x_integration_key)
    if payload.event_id and db.get(BookingEventReceipt, payload.event_id):
        existing = db.scalar(select(Lead).where(Lead.external_booking_id == payload.booking_id))
        return {"ok": True, "already_processed": True, "lead_id": existing.id if existing else None}
    existing = db.scalar(select(Lead).where(Lead.external_booking_id == payload.booking_id))
    was_existing = bool(existing)
    availability = check_booking_availability(payload.event_date)
    new_stage = booking_stage(payload)
    matched_visit_id = None if payload.is_test else match_attribution(db, payload.website_attribution)
    if existing:
        lead = existing
        previous_stage = lead.stage
        lead.primary_first_name = payload.primary_first_name.strip()
        lead.partner_first_name = payload.partner_first_name.strip()
        lead.email = str(payload.email).lower()
        lead.phone = payload.phone
        lead.event_date = payload.event_date
        lead.venue = payload.venue.strip()
        lead.venue_address = payload.venue_address
        lead.package_interest = payload.package_interest
        lead.referral_source = payload.referral_source or lead.referral_source
        lead.landing_page = payload.landing_page or lead.landing_page
        lead.campaign = payload.campaign or lead.campaign
        lead.message = payload.message or lead.message
        lead.availability = availability
        lead.estimated_value = payload.estimated_value
        lead.deposit_amount = payload.deposit_amount
        lead.quote_status = payload.quote_status
        lead.quote_items = payload.quote_items
        lead.is_test = payload.is_test
        if payload.is_test:
            lead.website_visit_id = None
        elif matched_visit_id and lead.website_visit_id in (None, matched_visit_id):
            lead.website_visit_id = matched_visit_id
        lead.booking_sync_status = "source"
        lead.booking_sync_error = None
        lead.stage = new_stage if payload.intelligence else merged_booking_stage(previous_stage, new_stage)
        if previous_stage != lead.stage:
            db.add(Activity(lead_id=lead.id, kind="booking_status_changed",
                            label=f"Booking system updated: {lead.stage}",
                            details={"previous_stage": previous_stage,
                                     "booking_status": payload.booking_status,
                                     "deposit_paid": payload.deposit_paid}))
    else:
        lead = Lead(external_booking_id=payload.booking_id, primary_first_name=payload.primary_first_name.strip(),
                    partner_first_name=payload.partner_first_name.strip(), email=str(payload.email).lower(), phone=payload.phone,
                    event_date=payload.event_date, venue=payload.venue.strip(), venue_address=payload.venue_address,
                    package_interest=payload.package_interest, referral_source=payload.referral_source,
                    landing_page=payload.landing_page, campaign=payload.campaign, message=payload.message,
                    availability=availability, booking_sync_status="source", stage=new_stage,
                    estimated_value=payload.estimated_value, deposit_amount=payload.deposit_amount,
                    quote_status=payload.quote_status, quote_items=payload.quote_items,
                    website_visit_id=matched_visit_id, is_test=payload.is_test)
        db.add(lead)
        db.flush()
        db.add(Activity(lead_id=lead.id, kind="enquiry_received", label="Booking-system enquiry received",
                        details={"source": lead.referral_source or "Not specified", "availability": availability}))
    if lead.stage in {"booked", "lost"}:
        for automation in db.scalars(select(Automation).where(
                Automation.lead_id == lead.id, Automation.status == "scheduled")).all():
            automation.status = "cancelled"
            automation.error = f"Cancelled automatically because booking status became {new_stage}"
    if payload.intelligence:
        insight = db.get(BookingInsight, lead.id)
        if not insight:
            insight = BookingInsight(lead_id=lead.id)
            db.add(insight)
        insight.facts = payload.intelligence.model_dump(mode='json')
        insight.received_at = datetime.now(timezone.utc)
    if payload.event_id:
        db.add(BookingEventReceipt(event_id=payload.event_id, booking_id=payload.booking_id))
    db.commit()
    return {"ok": True, "status": "synchronised", "lead_id": lead.id,
            "proposal_created": False, "duplicate_ignored": was_existing and not payload.event_id,
            "stage": lead.stage}


@app.post("/api/admin/leads", status_code=201)
def admin_create_lead(payload: LeadCreateIn, request: Request, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    public_payload = PublicEnquiryIn(**payload.model_dump(exclude={"forward_to_booking"}))
    return lead_json(create_lead(public_payload, request, db, settings.booking_enquiry_forwarding, "manual"), True)


@app.get("/api/admin/dashboard")
def dashboard(_: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    leads = db.scalars(select(Lead).where(Lead.created_at >= month_start).options(selectinload(Lead.proposal), selectinload(Lead.activities)).order_by(Lead.updated_at.desc())).all()
    booked = [x for x in leads if x.stage == "booked"]
    quoted = [x for x in leads if x.stage in {"qualified", "proposal", "engaged", "booked"}]
    attention_order = {"engaged": 0, "new": 1, "qualified": 2, "proposal": 3}
    hot = sorted((x for x in leads if x.stage not in {"booked", "lost"}),
                 key=lambda x: (attention_order.get(x.stage, 9), -x.updated_at.timestamp()))[:8]
    new_count = sum(1 for x in leads if x.stage == "new")
    accepted_count = sum(1 for x in leads if x.stage == "engaged")
    return {"metrics": {"new_enquiries": len(leads), "quotes_progressing": len(quoted), "bookings": len(booked),
                        "booked_value": float(sum((x.estimated_value or Decimal("0")) for x in booked))},
            "hot_leads": [lead_json(x) for x in hot],
            "actions": [
                {"kind": "new", "count": new_count, "label": "new enquiries waiting for a quote"},
                {"kind": "accepted", "count": accepted_count, "label": "accepted quotes waiting for confirmation"},
            ]}


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
    raise HTTPException(410, "Quotes are managed in the Booking System")


@app.post("/api/admin/leads/{lead_id}/proposal/publish")
def publish_proposal(lead_id: str, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    raise HTTPException(410, "Quotes are published from the Booking System")


@app.post("/api/admin/leads/{lead_id}/proposal/send")
def email_proposal(lead_id: str, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    raise HTTPException(410, "Quotes and client emails are managed in the Booking System")


@app.patch("/api/admin/automations/{automation_id}")
def patch_automation(automation_id: str, payload: AutomationPatchIn, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    item = db.get(Automation, automation_id)
    if not item:
        raise HTTPException(404, "Follow-up not found")
    if item.status != "scheduled":
        raise HTTPException(409, "Only scheduled follow-ups can be edited")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(item, key, value)
    if changes and item.approved_at:
        item.approved_at = None
    db.commit()
    return automation_json(item)


@app.post("/api/admin/automations/{automation_id}/approve")
def approve_automation(automation_id: str, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    item = db.get(Automation, automation_id)
    if not item:
        raise HTTPException(404, "Follow-up not found")
    if item.status != "scheduled":
        raise HTTPException(409, "Only scheduled follow-ups can be approved")
    item.approved_at = datetime.now(timezone.utc)
    db.commit()
    return automation_json(item)


@app.post("/api/admin/automations/{automation_id}/cancel")
def cancel_automation(automation_id: str, _: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    item = db.get(Automation, automation_id)
    if not item:
        raise HTTPException(404, "Follow-up not found")
    if item.status not in {"scheduled", "failed"}:
        raise HTTPException(409, "This follow-up can no longer be cancelled")
    item.status = "cancelled"
    item.approved_at = None
    db.add(Activity(lead_id=item.lead_id, kind="followup_cancelled", label=f"{item.kind.replace('_', ' ').title()} cancelled"))
    db.commit()
    return automation_json(item)


@app.get("/p/{slug}/{token}", response_class=HTMLResponse)
def public_proposal(slug: str, token: str, request: Request, db: Session = Depends(get_db)):
    item = db.scalar(select(Proposal).where(Proposal.slug == slug, Proposal.access_token == token, Proposal.published.is_(True)).options(selectinload(Proposal.lead)))
    if not item:
        raise HTTPException(404, "This proposal is not available")
    if item.expires_at and item.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(410, "This proposal has expired. Please contact Mark.")
    availability = check_booking_availability(item.lead.event_date)
    return templates.TemplateResponse(request=request, name="proposal.html", context={"proposal": item, "lead": item.lead,
                                      "availability": availability, "business_phone": settings.business_phone})


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
        db.commit()
    return Response(status_code=204)


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(ROOT / "static" / "login.html")


@app.get("/", include_in_schema=False)
def admin_page():
    return FileResponse(ROOT / "static" / "admin.html")
