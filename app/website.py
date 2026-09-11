"""Consent-gated website measurements and cached, read-only Search Console reports."""
import asyncio
import copy
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import select, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .config import get_settings
from .db import SessionLocal, get_db
from .models import Lead, Setting, WebsiteVisit, WebsiteEvent
from .security import current_admin, csrf_admin

router = APIRouter()
ORIGINS = {'https://perfectweddingsbymark.uk', 'https://www.perfectweddingsbymark.uk'}
SOURCES = {'Google', 'Facebook', 'Instagram', 'Bing', 'Other website', 'Direct / unknown'}
PRIVATE_PATH_PARTS = {'wp-admin', 'wp-json', 'bookings', 'p', 'login', 'client', 'admin'}
SCOPES = ['https://www.googleapis.com/auth/webmasters.readonly']
sync_lock = threading.Lock()
rate_lock = threading.Lock()
rates = {}


def now(): return datetime.now(timezone.utc)
def utc(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
def get_value(db, key, default=None):
    row = db.get(Setting, key)
    return copy.deepcopy(row.value) if row else copy.deepcopy(default)

def put_value(db, key, value):
    row = db.get(Setting, key)
    if row: row.value = value
    else: db.add(Setting(key=key, value=value))


def config(db):
    return get_value(db, 'website-config', {'enabled': False, 'token': '', 'pages': {'/': 'Home page', '/packages/': 'Packages & prices', '/contact/': 'Contact & enquiries'}, 'goals_ready': False, 'campaigns': {}, 'started_at': None})


def safe_public_path(path: str) -> bool:
    parts = path.lower().split('/') if path else []
    return bool(re.fullmatch(r'/[a-zA-Z0-9/_-]{0,199}', path or '')) and not any(
        part in PRIVATE_PATH_PARTS or part.startswith('private') for part in parts
    )


def visit_hash(raw_visit_id: str) -> str:
    return hmac.new(
        get_settings().session_secret.encode(), raw_visit_id.encode(), hashlib.sha256
    ).hexdigest()


def match_attribution(db: Session, attribution) -> str | None:
    """Return a stored visit only when every anonymous claim matches our own evidence."""
    if attribution is None or not safe_public_path(attribution.landing_path):
        return None
    hashed = visit_hash(attribution.visit_id)
    visit = db.get(WebsiteVisit, hashed)
    if not visit or visit.source != attribution.source or visit.campaign != attribution.campaign:
        return None
    started = utc(visit.started_at)
    if started < now() - timedelta(days=90) or started > now() + timedelta(minutes=5):
        return None
    page_seen = db.scalar(select(WebsiteEvent.id).where(
        WebsiteEvent.visit_id == hashed,
        WebsiteEvent.kind == 'page_view',
        WebsiteEvent.path == attribution.landing_path,
    ).limit(1))
    if not page_seen or (visit.landing_path and visit.landing_path != attribution.landing_path):
        return None
    if not visit.landing_path:
        visit.landing_path = attribution.landing_path
    return hashed


class WebsiteConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool
    pages: dict[str, str] = Field(min_length=1, max_length=100)
    goals_ready: bool = False

    @field_validator('pages')
    @classmethod
    def validate_pages(cls, pages):
        for path, label in pages.items():
            if not re.fullmatch(r'/[a-zA-Z0-9/_-]{0,199}', path) or not 1 <= len(label.strip()) <= 100:
                raise ValueError('Use public page paths such as /packages/ and a short readable label.')
            if any(p in path.lower().split('/') for p in ['wp-admin', 'wp-json', 'bookings', 'p', 'login']):
                raise ValueError('Private and administration pages cannot be tracked.')
        return {p: v.strip() for p, v in pages.items()}


async def small_json(request, limit=8192):
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit: raise HTTPException(413, 'Request too large')
    try: return json.loads(body)
    except (ValueError, UnicodeDecodeError): raise HTTPException(422, 'Invalid JSON')


@router.get('/api/admin/website/setup')
def setup(_=Depends(current_admin), db: Session=Depends(get_db)):
    cfg = config(db)
    return {'website': cfg, 'google': get_value(db, 'website-google', {}),
            'endpoint': get_settings().app_url.rstrip('/'), 'sync': get_value(db, 'website-google-status', {})}


@router.put('/api/admin/website/setup')
def save_setup(payload: WebsiteConfig, _=Depends(csrf_admin), db: Session=Depends(get_db)):
    cfg = config(db)
    cfg = {**cfg, **payload.model_dump(), 'token': cfg['token'] or secrets.token_urlsafe(24)}
    if payload.enabled and (not config(db)['enabled'] or not cfg['started_at']): cfg['started_at'] = now().isoformat()
    put_value(db, 'website-config', cfg); db.commit()
    return cfg


def allowed(request, db):
    origin = request.headers.get('origin')
    if origin not in ORIGINS: raise HTTPException(403, 'Website origin not allowed')
    cfg = config(db)
    if not cfg['enabled']: raise HTTPException(403, 'Website tracking is paused')
    return cfg, {'Access-Control-Allow-Origin': origin, 'Vary': 'Origin', 'Cache-Control': 'no-store'}


@router.options('/api/website/events')
@router.options('/api/website/config')
def preflight(request: Request, db: Session=Depends(get_db)):
    _, headers = allowed(request, db)
    return Response(status_code=204, headers={**headers, 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type'})


@router.get('/api/website/config')
def public_config(request: Request, token: str='', db: Session=Depends(get_db)):
    from fastapi.responses import JSONResponse
    cfg, headers = allowed(request, db)
    if not hmac.compare_digest(token, cfg['token']): raise HTTPException(403, 'Unknown website')
    return JSONResponse({'pages': list(cfg['pages']), 'measure_all_public': True,
                         'goals_ready': cfg['goals_ready'], 'campaigns': list(cfg['campaigns'])}, headers=headers)


class EventIn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: str = Field(max_length=80)
    event_id: UUID
    visit_id: UUID
    kind: Literal['page_view', 'enquiry_start', 'enquiry_success', 'date_check']
    path: str = Field(max_length=200)
    source: str = Field(max_length=30)
    campaign: str = Field(default='', max_length=80)
    device: Literal['Small screen', 'Large screen']


def enforce_rate(visit):
    minute = int(time.time() // 60)
    with rate_lock:
        for key in list(rates):
            if rates[key][0] != minute: del rates[key]
        for key, limit in [('all', 2000), (visit, 60)]:
            stamp, count = rates.get(key, (minute, 0))
            if count >= limit: raise HTTPException(429, 'Please slow down')
            rates[key] = (stamp, count + 1)


@router.post('/api/website/events')
async def collect(request: Request, db: Session=Depends(get_db)):
    cfg, headers = allowed(request, db)
    from pydantic import ValidationError
    try: payload = EventIn.model_validate(await small_json(request, 2048))
    except ValidationError: raise HTTPException(422, 'Invalid website event')
    if not hmac.compare_digest(payload.token, cfg['token']): raise HTTPException(403, 'Unknown website')
    if not safe_public_path(payload.path): raise HTTPException(422, 'Page is not safe for measurement')
    if payload.source not in SOURCES: raise HTTPException(422, 'Unknown source')
    if payload.kind != 'page_view' and not cfg['goals_ready']: raise HTTPException(409, 'Enquiry tracking has not been verified')
    if payload.campaign and payload.campaign not in cfg['campaigns']: raise HTTPException(422, 'Unknown campaign')
    visit_id = visit_hash(str(payload.visit_id))
    enforce_rate(visit_id)
    if db.get(WebsiteEvent, str(payload.event_id)): return Response(status_code=204, headers=headers)
    visit = db.get(WebsiteVisit, visit_id)
    if not visit:
        visit = WebsiteVisit(id=visit_id, source=payload.source, campaign=payload.campaign,
                             device=payload.device, landing_path=payload.path)
        try:
            with db.begin_nested():
                db.add(visit); db.flush()
        except IntegrityError:
            visit = db.get(WebsiteVisit, visit_id)
            if visit is None: raise HTTPException(409, 'Please retry this visit')
    # Campaign, source and landing page describe the beginning of the visit;
    # subsequent events cannot overwrite them.
    if not visit.landing_path:
        visit.landing_path = payload.path
    db.add(WebsiteEvent(id=str(payload.event_id), visit_id=visit_id, kind=payload.kind, path=payload.path))
    try: db.commit()
    except IntegrityError:
        db.rollback()
        if not db.get(WebsiteEvent, str(payload.event_id)): raise HTTPException(409, 'Please retry this event')
    return Response(status_code=204, headers=headers)


def period_counts(db, start, end, cfg):
    start, end = utc(start), utc(end)
    # Cohort by visit start; outcomes may happen up to the report end.
    visits = db.scalars(select(WebsiteVisit).where(WebsiteVisit.started_at >= start, WebsiteVisit.started_at < end)).all()
    ids = {v.id for v in visits}
    grouped = {}
    if ids:
        rows = db.execute(select(WebsiteEvent.visit_id, WebsiteEvent.kind, func.count()).join(WebsiteVisit, WebsiteEvent.visit_id == WebsiteVisit.id).where(WebsiteVisit.started_at >= start, WebsiteVisit.started_at < end, WebsiteEvent.occurred_at < end).group_by(WebsiteEvent.visit_id, WebsiteEvent.kind)).all()
        for vid, kind, count in rows: grouped.setdefault(vid, {})[kind] = count
    starters = {vid for vid, kinds in grouped.items() if 'enquiry_start' in kinds}
    completed = {vid for vid, kinds in grouped.items() if 'enquiry_success' in kinds}
    linked = db.scalars(select(Lead).where(
        Lead.website_visit_id.in_(ids), Lead.is_test.is_(False)
    )).all() if ids else []
    leads_by_visit = {}
    for lead in linked:
        leads_by_visit.setdefault(lead.website_visit_id, []).append(lead)

    def outcomes(chosen_visits):
        chosen_ids = {visit.id for visit in chosen_visits}
        rows = [lead for visit_id in chosen_ids for lead in leads_by_visit.get(visit_id, [])]
        accepted = [lead for lead in rows if lead.stage in {'engaged', 'booked'}]
        booked = [lead for lead in rows if lead.stage == 'booked']
        return {
            'linked_enquiries': len(rows),
            'quote_accepted': len(accepted),
            'bookings': len(booked),
            'booked_value': float(sum((lead.estimated_value or 0) for lead in booked)),
        }

    sources = []
    for source, count in Counter(v.source for v in visits).most_common():
        matching = [v for v in visits if v.source == source]
        sources.append({'name': source, 'visits': count,
                        'enquiries': sum(v.id in completed for v in matching), **outcomes(matching)})
    pages = db.execute(select(WebsiteEvent.path, func.count()).where(WebsiteEvent.occurred_at >= start, WebsiteEvent.occurred_at < end, WebsiteEvent.kind == 'page_view').group_by(WebsiteEvent.path).order_by(func.count().desc()).limit(20)).all()
    campaigns = []
    for slug, count in Counter(v.campaign for v in visits if v.campaign).most_common():
        matching = [v for v in visits if v.campaign == slug]
        campaigns.append({'name': cfg['campaigns'].get(slug, {}).get('name', slug),
                          'visits': count, 'enquiries': sum(v.id in completed for v in matching),
                          **outcomes(matching)})
    page_views = dict(pages)
    landing_paths = set(page_views) | {v.landing_path for v in visits if v.landing_path}
    page_rows = []
    for path in landing_paths:
        matching = [v for v in visits if v.landing_path == path]
        page_rows.append({'name': cfg['pages'].get(path, path), 'path': path,
                          'views': page_views.get(path, 0), **outcomes(matching)})
    page_rows.sort(key=lambda row: (-row['views'], row['name']))
    return {'visits': len(visits), 'views': sum(k.get('page_view', 0) for k in grouped.values()),
            'starts': len(starters), 'enquiries': len(completed),
            'started_and_completed': len(starters & completed),
            'date_checks': sum('date_check' in k for k in grouped.values()),
            **outcomes(visits), 'sources': sources, 'pages': page_rows[:20],
            'campaigns': campaigns, 'devices': dict(Counter(v.device for v in visits))}


@router.get('/api/admin/website/report')
def report(days: int=28, _=Depends(current_admin), db: Session=Depends(get_db)):
    if days not in (7, 28): raise HTTPException(422, 'Choose 7 or 28 days')
    cfg = config(db)
    end = datetime.combine(now().astimezone(ZoneInfo('Europe/London')).date(), datetime.min.time(), ZoneInfo('Europe/London'))
    start = end - timedelta(days=days); previous_start = start - timedelta(days=days)
    current = period_counts(db, start, end, cfg); previous = period_counts(db, previous_start, start, cfg)
    coverage = bool(cfg['started_at'] and datetime.fromisoformat(cfg['started_at']) <= previous_start)
    last = db.scalar(select(func.max(WebsiteEvent.occurred_at)))
    tips = []
    if not cfg['enabled']: tips.append('Website tracking is not connected yet. Connect it below to start collecting real figures.')
    elif not last: tips.append('No website activity received yet. Check the plugin using an allowed page and choose Allow in its analytics prompt.')
    elif (now() - utc(last)).total_seconds() > 172800: tips.append('No activity has arrived for over two days. Check the website tracker before treating this as a fall in interest.')
    if current['visits'] < 20: tips.append('There is only a small sample so far. Let more visits build up before changing your marketing.')
    if current['sources'] and current['visits'] >= 20: tips.append(f"{current['sources'][0]['name']} brought the most measured visits in this period. Check its enquiry count before deciding to spend more there.")
    if cfg['goals_ready'] and current['starts'] >= 20 and current['started_and_completed'] / current['starts'] < .5:
        tips.append(f"{current['starts']} visits started an enquiry; {current['started_and_completed']} of those also recorded a successful submission. Try the form on your phone. This alone does not prove a fault.")
    google = get_value(db, 'website-google-report')
    return {'days': days, 'start': start.date().isoformat(), 'end': (end - timedelta(days=1)).date().isoformat(), 'current': current, 'previous': previous, 'comparison_ready': coverage, 'enabled': cfg['enabled'], 'goals_ready': cfg['goals_ready'], 'last_event': utc(last).isoformat() if last else None, 'tracking_since': cfg['started_at'], 'tips': tips, 'google': google, 'google_status': get_value(db, 'website-google-status', {}), 'google_connected': bool(get_value(db, 'website-google')), 'booking_attribution': {'connected': True, 'scope': 'Only new website enquiries carrying a verified consenting visit can be linked. Test records are excluded.'}}


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source: Literal['facebook', 'instagram', 'google', 'other']
    path: str = Field(max_length=200)


@router.post('/api/admin/website/campaign-link')
def campaign_link(payload: CampaignIn, _=Depends(csrf_admin), db: Session=Depends(get_db)):
    cfg = config(db)
    if payload.path not in cfg['pages']: raise HTTPException(422, 'Choose a measured public page')
    if len(cfg['campaigns']) >= 200: raise HTTPException(422, 'Campaign limit reached')
    slug = secrets.token_hex(6)
    cfg['campaigns'] = {**cfg['campaigns'], slug: {'name': payload.name, 'source': payload.source, 'path': payload.path}}
    put_value(db, 'website-config', dict(cfg)); db.commit()
    return {'url': 'https://perfectweddingsbymark.uk' + payload.path + '?utm_source=' + payload.source + '&utm_medium=social&utm_campaign=' + slug}


def credentials_path(): return get_settings().storage_root / 'website-search-console.json'


def make_credentials(data):
    from google.oauth2.service_account import Credentials
    # Never use uploaded token hosts, delegated subjects, external-account URLs or executable sources.
    if data.get('type') != 'service_account' or not re.fullmatch(r'[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.iam\.gserviceaccount\.com', data.get('client_email', '')):
        raise ValueError('Use a Google service-account JSON key')
    safe = {k: data[k] for k in ('client_email', 'private_key', 'private_key_id') if k in data}
    safe['token_uri'] = 'https://oauth2.googleapis.com/token'
    return Credentials.from_service_account_info(safe, scopes=SCOPES), safe


@router.post('/api/admin/website/google-connect')
async def google_connect(request: Request, _=Depends(csrf_admin), db: Session=Depends(get_db)):
    data = await small_json(request, 20000)
    if not isinstance(data, dict): raise HTTPException(422, 'Invalid connection details')
    prop = data.get('property')
    if prop not in {'sc-domain:perfectweddingsbymark.uk', 'https://perfectweddingsbymark.uk/', 'https://www.perfectweddingsbymark.uk/'}:
        raise HTTPException(422, 'Choose your exact verified Search Console property')
    try: _, safe = make_credentials(data['credentials'])
    except Exception: raise HTTPException(422, 'The Google service-account key could not be read. Use the original JSON key file.')
    if not sync_lock.acquire(blocking=False): raise HTTPException(409, 'Google refresh is in progress; try again shortly')
    try:
        path = credentials_path(); path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream: json.dump({**safe, 'type': 'service_account'}, stream)
        os.chmod(temporary, 0o600); os.replace(temporary, path)
        put_value(db, 'website-google', {'property': prop, 'email': safe['client_email']})
        db.execute(delete(Setting).where(Setting.key.in_(['website-google-report', 'website-google-status'])))
        db.commit()
    finally: sync_lock.release()
    return {'ok': True, 'message': 'Key saved. Refresh Google figures to check access.'}


@router.delete('/api/admin/website/google-connect')
def google_disconnect(_=Depends(csrf_admin), db: Session=Depends(get_db)):
    if not sync_lock.acquire(blocking=False): raise HTTPException(409, 'Wait for the current Google refresh to finish')
    try:
        credentials_path().unlink(missing_ok=True)
        db.execute(delete(Setting).where(Setting.key.in_(['website-google', 'website-google-status', 'website-google-report'])))
        db.commit()
    finally: sync_lock.release()
    return {'ok': True}


def fetch_google(prop):
    import requests
    from google.auth.transport.requests import Request as GoogleRequest
    with credentials_path().open() as stream: creds, _ = make_credentials(json.load(stream))
    with requests.Session() as session:
        transport = GoogleRequest(session=session)
        creds.refresh(lambda **kwargs: transport(**{**kwargs, 'timeout': 10}))
        end = now().astimezone(ZoneInfo('America/Los_Angeles')).date() - timedelta(days=3)
        start = end - timedelta(days=27)
        url = 'https://www.googleapis.com/webmasters/v3/sites/' + quote(prop, safe='') + '/searchAnalytics/query'
        def query(a, b, dimensions):
            res = session.post(url, headers={'Authorization': 'Bearer ' + creds.token}, json={'startDate': a.isoformat(), 'endDate': b.isoformat(), 'type': 'web', 'dataState': 'final', 'dimensions': dimensions, 'rowLimit': 20}, timeout=10, allow_redirects=False)
            if res.status_code != 200: raise ValueError('Google access failed')
            body = res.json()
            rows = body.get('rows', [])
            if not isinstance(rows, list) or len(rows) > 20: raise ValueError('Unexpected Google response')
            for row in rows:
                if not all(isinstance(row.get(k), (int, float)) and math.isfinite(row[k]) and row[k] >= 0 for k in ['clicks', 'impressions', 'ctr', 'position']): raise ValueError('Invalid Google figures')
            return rows
        current = query(start, end, [])
        previous = query(start - timedelta(days=28), start - timedelta(days=1), [])
        return {'start': start.isoformat(), 'end': end.isoformat(), 'updated_at': now().isoformat(), 'totals': current[0] if current else None, 'previous': previous[0] if previous else None, 'queries': query(start, end, ['query']), 'pages': query(start, end, ['page']), 'devices': query(start, end, ['device'])}


def refresh_google():
    if not sync_lock.acquire(blocking=False): return
    try:
        with SessionLocal() as db:
            connection = get_value(db, 'website-google')
            if not connection: return
            status = get_value(db, 'website-google-status', {})
            if status.get('attempted_at') and (now() - datetime.fromisoformat(status['attempted_at'])).total_seconds() < 60: return
            put_value(db, 'website-google-status', {'state': 'refreshing', 'attempted_at': now().isoformat()}); db.commit()
            try:
                result = fetch_google(connection['property'])
                put_value(db, 'website-google-report', result)
                status = {'state': 'ready', 'attempted_at': now().isoformat()}
            except Exception:
                status = {'state': 'error', 'attempted_at': now().isoformat(), 'message': 'Google could not be refreshed. Check that the API is enabled and the service-account email has access to this Search Console property. Previous figures are retained.'}
            put_value(db, 'website-google-status', status); db.commit()
    finally: sync_lock.release()


@router.post('/api/admin/website/google-refresh', status_code=202)
async def google_refresh(_=Depends(csrf_admin)):
    if not credentials_path().exists(): raise HTTPException(409, 'Connect Google first')
    # Background task is owned by the app lifespan; no live Google wait on a dashboard request.
    refresh_requested.set()
    return {'message': 'Refresh requested. Google figures update in the background.'}


refresh_requested = asyncio.Event()


last_cleanup = 0.0


def maintenance():
    global last_cleanup
    with SessionLocal() as db:
        cutoff = now() - timedelta(days=90)
        if time.monotonic() - last_cleanup > 3600:
            db.execute(delete(WebsiteEvent).where(WebsiteEvent.occurred_at < cutoff))
            db.execute(delete(WebsiteVisit).where(WebsiteVisit.started_at < cutoff, ~WebsiteVisit.id.in_(select(WebsiteEvent.visit_id))))
            db.commit()
            last_cleanup = time.monotonic()
        status = get_value(db, 'website-google-status', {})
        due = not status.get('attempted_at') or (now() - datetime.fromisoformat(status['attempted_at'])).total_seconds() > 21600
    if due or refresh_requested.is_set():
        refresh_requested.clear(); refresh_google()


async def website_loop():
    while True:
        try: await asyncio.to_thread(maintenance)
        except Exception: pass  # Website reporting must never prevent the main app from running.
        await asyncio.sleep(15)
