"""Evidence-based priorities and cohort reporting; never sends messages."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db
from .models import BookingInsight, Lead
from .security import current_admin, csrf_admin

router = APIRouter(prefix='/api/admin/intelligence')


def utc(value):
    if not value:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def records(db):
    return db.execute(select(Lead, BookingInsight).outerjoin(BookingInsight, BookingInsight.lead_id == Lead.id)
                      .where(Lead.external_booking_id.is_not(None))).all()


def active_record(f):
    return not (f.get('is_test') or f.get('archived'))


def won(f):
    return f['booking_status'] != 'cancelled' and (f['booking_status'] in {'confirmed', 'in_progress', 'completed'} or f.get('deposit_paid'))


def priority(lead, insight, now):
    if not insight or not active_record(insight.facts) or insight.facts.get('suppressed'):
        return None
    f = insight.facts
    if won(f) or f['booking_status'] == 'cancelled' or lead.event_date < now.date():
        return None
    if utc(insight.snoozed_until) and utc(insight.snoozed_until) > now:
        return None
    sent, contacted, incoming = (utc(f.get(k)) for k in ('quote_sent_at', 'last_contact_at', 'last_incoming_at'))
    clicked, created = utc(f.get('quote_link_at')), utc(f['source_created_at'])
    section, draft = 'journey', ''
    greeting = f'Hi {lead.primary_first_name} & {lead.partner_first_name},'
    if incoming and incoming >= created and (not contacted or incoming > contacted):
        kind, title, section = 'reply', 'A message needs a look', 'activity'
        reason = 'An incoming email from this address is newer than the last recorded outgoing message. Check the conversation before replying.'
    elif f.get('quote_accepted'):
        kind, title, section = 'accepted', 'Quote accepted · check the booking fee', 'payments'
        reason = 'An accepted quote has no first payment recorded. Check your bank before contacting the couple.'
        draft = f'{greeting}\n\nThank you for accepting your quote. If you have any questions about the booking fee or the next steps, just let me know and I’ll be happy to help.\n\nMark'
    elif not sent and f['booking_status'] == 'enquiry':
        kind, title = 'new', 'Prepare their quote'
        reason = f'Enquiry received {created.strftime("%d %b %Y")}; no successful quote email is recorded in Booking.'
    elif clicked and now - clicked <= timedelta(days=1) and (not contacted or clicked > contacted):
        kind, title = 'interest', 'Recent quote-link activity'
        reason = 'A quote-link access was recorded in the last 24 hours. This is an interest signal, not proof a person read it; automated scanners can open links.'
        draft = f'{greeting}\n\nI hope the plans for your wedding at {lead.venue} are coming together nicely. Is there anything you’d like to ask about the coverage or how I work on the day?\n\nMark'
    elif sent and now - max(sent, contacted or sent) >= timedelta(days=3):
        kind, title = 'waiting', 'Quote waiting · review the conversation'
        reason = 'At least three days since the last recorded outgoing contact. Check for replies or contact outside Booking before following up.'
        draft = f'{greeting}\n\nI just wanted to check whether you had any questions about the wedding information I sent for {lead.venue}. There’s absolutely no pressure—if there’s anything I can help with, just let me know.\n\nMark'
    else:
        return None
    return {'lead_id': lead.id, 'couple_name': lead.couple_name, 'event_date': lead.event_date.isoformat(),
            'venue': lead.venue, 'kind': kind, 'title': title, 'reason': reason,
            'value': float(lead.estimated_value or 0), 'draft': draft,
            'url': get_settings().booking_action_url.rstrip('/') + '/bookings/' + quote(lead.external_booking_id, safe='') + '/' + section,
            'mail_status': f.get('mail_status', 'not_configured'), 'mail_checked_at': f.get('mail_checked_at'),
            'last_incoming_at': f.get('last_incoming_at'), 'last_contact_at': f.get('last_contact_at'),
            'quote_sent_at': f.get('quote_sent_at'), 'quote_link_at': f.get('quote_link_at'),
            'synced_at': utc(insight.received_at).isoformat(),
            'stale': now - utc(insight.received_at) > timedelta(minutes=30)}


@router.get('/today')
def today(_=Depends(current_admin), db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    rows = records(db)
    cards = [card for lead, insight in rows if (card := priority(lead, insight, now))]
    order = {'reply': 0, 'accepted': 1, 'new': 2, 'interest': 3, 'waiting': 4}
    cards.sort(key=lambda c: (order[c['kind']], c['event_date'], c['couple_name']))
    return {'cards': cards, 'missing_evidence': sum(1 for _, i in rows if not i),
            'snoozed': sum(1 for _, i in rows if i and utc(i.snoozed_until) and utc(i.snoozed_until) > now),
            'generated_at': now.isoformat()}


class SnoozeIn(BaseModel):
    hours: int = Field(default=24, ge=0, le=168)


@router.post('/{lead_id}/snooze')
def snooze(lead_id: str, payload: SnoozeIn, _=Depends(csrf_admin), db: Session = Depends(get_db)):
    row = db.get(BookingInsight, lead_id)
    if not row:
        raise HTTPException(404, 'Booking evidence not received yet')
    row.snoozed_until = datetime.now(timezone.utc) + timedelta(hours=payload.hours) if payload.hours else None
    db.commit()
    return {'ok': True}


@router.post('/reset-snoozes')
def reset_snoozes(_=Depends(csrf_admin), db: Session = Depends(get_db)):
    for row in db.scalars(select(BookingInsight).where(BookingInsight.snoozed_until.is_not(None))):
        row.snoozed_until = None
    db.commit()
    return {'ok': True}


def performance_rows(rows, start=None, end=None):
    groups = {k: {} for k in ('sources', 'venues', 'packages', 'addons')}
    included, missing = [], 0
    for lead, insight in rows:
        if not insight:
            missing += 1
            continue
        f = insight.facts
        if not active_record(f):
            continue
        created = utc(f['source_created_at']).date()
        if (start and created < start) or (end and created > end):
            continue
        included.append((lead, f))
        for group, label in [('sources', lead.referral_source or 'Not recorded'), ('venues', lead.venue or 'Not recorded'),
                             ('packages', next((x.get('name') for x in lead.quote_items or [] if x.get('type') == 'package'), None) or lead.package_interest or 'Not selected')]:
            label = label.strip() or 'Not recorded'
            row = groups[group].setdefault(label.casefold(), {'name': label, 'enquiries': 0, 'bookings': 0, 'booked_value': 0.0})
            row['enquiries'] += 1
            if won(f):
                row['bookings'] += 1
                row['booked_value'] += float(lead.estimated_value or 0)
        if won(f):
            selected = defaultdict(float)
            for item in lead.quote_items or []:
                if item.get('type') == 'addon':
                    selected[str(item.get('name') or 'Unnamed add-on').strip()] += float(item.get('total') or 0)
            for name, value in selected.items():
                row = groups['addons'].setdefault(name.casefold(), {'name': name, 'bookings': 0, 'booked_value': 0.0})
                row['bookings'] += 1
                row['booked_value'] += value
    for group in ('sources', 'venues', 'packages'):
        for row in groups[group].values():
            row['conversion'] = round(row['bookings'] / row['enquiries'] * 100, 1)
            row['small_sample'] = row['enquiries'] < 10
            row['booked_value'] = round(row['booked_value'], 2)
    wins = [l for l, f in included if won(f)]
    total = sum(float(l.estimated_value or 0) for l in wins)
    return {'groups': {k: sorted(v.values(), key=lambda r: (-r['booked_value'], r['name'])) for k, v in groups.items()},
            'enquiries': len(included), 'bookings': len(wins), 'booked_value': round(total, 2),
            'conversion': round(len(wins) / len(included) * 100, 1) if included else 0,
            'average_booking': round(total / len(wins), 2) if wins else 0, 'missing_evidence': missing}


@router.get('/performance')
def performance(start: date | None = None, end: date | None = None, _=Depends(current_admin), db: Session = Depends(get_db)):
    if start and end and start > end:
        raise HTTPException(422, 'The start date must be before the end date')
    return performance_rows(records(db), start, end)
