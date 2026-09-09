"""Live availability planning and manually attributed campaigns. No sending/publishing."""
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, HttpUrl, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db
from .models import Campaign, CampaignAttribution, Lead, BookingInsight, Setting
from .security import current_admin, csrf_admin
from .intelligence import records, active_record, won, utc

router = APIRouter(prefix='/api/admin/gaps')


def london_today():
    return datetime.now(ZoneInfo('Europe/London')).date()


class Day(BaseModel):
    date: date
    status: Literal['available', 'booked', 'blocked']


class Package(BaseModel):
    id: str
    name: str
    price: Decimal = Field(ge=0)


class Availability(BaseModel):
    start: date
    end: date
    checked_at: datetime
    days: list[Day]
    packages: list[Package]


def booking_window(start, end):
    if start < london_today() or end < start or (end-start).days > 731:
        raise HTTPException(422, 'Choose today or later and no more than 24 months (732 days).')
    settings = get_settings()
    if not settings.booking_webhook_key:
        raise HTTPException(503, 'The Booking integration key is not configured. Availability is unknown.')
    request = Request(settings.booking_base_url + '/api/integrations/growth/availability?' + urlencode({'start':start, 'end':end}),
        headers={'X-Integration-Key':settings.booking_webhook_key, 'User-Agent':'WBM-Growth/1.3'})
    try:
        with urlopen(request, timeout=settings.booking_timeout_seconds) as response:
            data = Availability.model_validate(json.load(response))
        expected = {start + timedelta(days=i) for i in range((end-start).days+1)}
        if data.start != start or data.end != end or len(data.days) != len(expected) or {d.date for d in data.days} != expected:
            raise ValueError('Incomplete dates')
        if abs((datetime.now(timezone.utc)-utc(data.checked_at)).total_seconds()) > 300:
            raise ValueError('Stale availability')
        return data
    except Exception as exc:
        raise HTTPException(503, 'Live Booking availability could not be checked. Refresh after checking the connection and Booking V8.43 update. No dates have been assumed free.') from exc


def eligible(lead, insight):
    return bool(insight and active_record(insight.facts) and not insight.facts.get('suppressed')
                and not won(insight.facts) and insight.facts.get('booking_status') in ('enquiry','quoted'))


def lead_card(lead, insight):
    settings = get_settings()
    f = insight.facts
    return {'id':lead.id, 'name':lead.couple_name, 'date':lead.event_date.isoformat(), 'venue':lead.venue,
            'quote_status':lead.quote_status, 'value':float(lead.estimated_value or 0),
            'synced_at':utc(insight.received_at).isoformat(),
            'last_contact_at':f.get('last_contact_at'), 'last_incoming_at':f.get('last_incoming_at'),
            'url':settings.booking_action_url.rstrip('/')+'/bookings/'+quote(lead.external_booking_id,safe='')+'/activity'}


@router.get('/calendar')
def calendar(start: date, end: date, _=Depends(current_admin), db: Session=Depends(get_db)):
    result = booking_window(start,end).model_dump(mode='json')
    by_date = {d['date']:d for d in result['days']}
    for day in by_date.values():
        day['enquiries'] = []
    for lead, insight in records(db):
        day = by_date.get(lead.event_date.isoformat())
        if day and day['status']=='available' and eligible(lead, insight):
            day['enquiries'].append(lead_card(lead,insight))
    return result


class Creative(BaseModel):
    venue: str = Field(default='',max_length=240)
    testimonial: str = Field(default='',max_length=1200)
    credited_to: str = Field(default='',max_length=160)
    photo_urls: list[HttpUrl] = Field(default_factory=list,max_length=6)
    link: HttpUrl | None = None

    @model_validator(mode='after')
    def credit(self):
        if self.testimonial.strip() and not self.credited_to.strip():
            raise ValueError('Add the testimonial credit before using this wording.')
        return self


class PlanIn(BaseModel):
    dates: list[date] = Field(min_length=1, max_length=12)
    channel: Literal['facebook','google'] = 'facebook'
    package_id: str | None = None
    creative: Creative | None = None


class CampaignIn(PlanIn):
    package_snapshot: Package | None = None
    name: str = Field(min_length=1,max_length=160)
    draft: str = Field(min_length=1,max_length=10000)


def check_plan(payload):
    dates = sorted(set(payload.dates))
    data = booking_window(min(dates),max(dates))
    statuses = {d.date:d.status for d in data.days}
    if any(statuses.get(d) != 'available' for d in dates):
        raise HTTPException(409, 'A selected date is now booked or blocked. Refresh the calendar and adjust your draft.')
    package = next((p for p in data.packages if p.id==payload.package_id),None)
    if payload.package_id and not package:
        raise HTTPException(409,'That package is no longer active. Choose a current package.')
    return dates, package, data.checked_at


def promotion(dates, package, channel, creative=None):
    dates_text = ', '.join(d.strftime('%A %d %B %Y') for d in dates)
    pricing = f'\n\n{package.name}: £{package.price:,.2f}.' if package else ''
    venue_line = f'Planning your wedding at {creative.venue.strip()}?\n\n' if creative and creative.venue.strip() else ''
    testimonial = f'\n\n“{creative.testimonial.strip()}” — {creative.credited_to.strip()}' if creative and creative.testimonial.strip() else ''
    link = str(creative.link) if creative and creative.link else get_settings().booking_action_url.rstrip('/')+'/enquiry'
    intro = ('Still looking for your wedding photographer?' if channel=='facebook' else 'Wedding photography availability')
    return (f'{intro}\n\n{venue_line}I currently have these dates available: {dates_text}.\n\n'
            'If you’d love natural photographs of the laughter, the little moments and the people who make your day yours, I’d love to hear what you’re planning.'
            f'{pricing}{testimonial}\n\nTell me your wedding date and venue, and I’ll confirm availability and talk you through the options.\n\n'
            f'Find out more: {link}\n\nMark | Weddings By Mark')


@router.post('/draft')
def draft(payload:PlanIn, _=Depends(csrf_admin)):
    dates, package, checked = check_plan(payload)
    return {'draft':promotion(dates,package,payload.channel,payload.creative), 'checked_at':checked.isoformat(),
            'package':package.model_dump(mode='json') if package else {}}


@router.post('/campaigns',status_code=201)
def create_campaign(payload:CampaignIn, _=Depends(csrf_admin), db:Session=Depends(get_db)):
    dates, package, _checked = check_plan(payload)
    if package and payload.package_snapshot != package:
        raise HTTPException(409, 'The package has changed since this draft was generated. Generate a fresh draft.')
    if not payload.name.strip() or not payload.draft.strip():
        raise HTTPException(422,'Enter a campaign name and message.')
    campaign = Campaign(name=payload.name.strip(), dates=[d.isoformat() for d in dates],
        channel=payload.channel, draft=payload.draft.strip(),
        package_snapshot=package.model_dump(mode='json') if package else {})
    db.add(campaign)
    db.flush()
    if payload.creative:
        db.add(Setting(key='campaign-creative:'+campaign.id,value=payload.creative.model_dump(mode='json')))
    db.commit()
    return {'id':campaign.id}


def get_campaign(db, campaign_id):
    row = db.get(Campaign,campaign_id)
    if not row:
        raise HTTPException(404,'Campaign not found')
    return row


class CampaignEdit(BaseModel):
    name: str = Field(min_length=1,max_length=160)
    draft: str = Field(min_length=1,max_length=10000)


@router.patch('/campaigns/{campaign_id}')
def edit_campaign(campaign_id:str,payload:CampaignEdit,_=Depends(csrf_admin),db:Session=Depends(get_db)):
    row=get_campaign(db,campaign_id)
    if row.status=='published':
        raise HTTPException(409,'Published campaign wording is retained. Create a new campaign for a new post.')
    if not payload.name.strip() or not payload.draft.strip():
        raise HTTPException(422,'Enter a campaign name and message.')
    row.name=payload.name.strip()
    row.draft=payload.draft.strip()
    db.commit()
    return {'ok':True}


@router.post('/campaigns/{campaign_id}/check')
def recheck(campaign_id:str,_=Depends(csrf_admin),db:Session=Depends(get_db)):
    row=get_campaign(db,campaign_id)
    _dates, package, checked=check_plan(PlanIn(dates=row.dates,channel=row.channel,package_id=row.package_snapshot.get('id')))
    if package and package.model_dump(mode='json') != row.package_snapshot:
        raise HTTPException(409,'The package name or price has changed in Booking. Create a fresh draft using the current price.')
    return {'ok':True,'checked_at':checked.isoformat()}


@router.post('/campaigns/{campaign_id}/published')
def mark_published(campaign_id:str,_=Depends(csrf_admin),db:Session=Depends(get_db)):
    row=get_campaign(db,campaign_id)
    # Records a user's past action; it does not publish or claim live availability.
    row.status='published'
    row.published_at=row.published_at or datetime.now(timezone.utc)
    db.commit()
    return {'ok':True}


@router.get('/campaigns')
def campaigns(_=Depends(current_admin),db:Session=Depends(get_db)):
    source={l.id:(l,i) for l,i in records(db) if i and active_record(i.facts)}
    attribution={r.lead_id:r.campaign_id for r in db.scalars(select(CampaignAttribution))}
    creative={r.key.removeprefix('campaign-creative:'):r.value for r in db.scalars(select(Setting).where(Setting.key.like('campaign-creative:%')))}
    result=[]
    for row in db.scalars(select(Campaign).order_by(Campaign.created_at.desc())):
        leads=[source[k] for k,c in attribution.items() if c==row.id and k in source]
        wins=[l for l,i in leads if won(i.facts)]
        result.append({'id':row.id,'name':row.name,'dates':row.dates,'channel':row.channel,
            'draft':row.draft,'status':row.status,'package':row.package_snapshot,
            'creative':creative.get(row.id), 'created_at':utc(row.created_at).isoformat(), 'published_at':utc(row.published_at).isoformat() if row.published_at else None,
            'enquiries':len(leads),'bookings':len(wins),'booked_value':float(sum((l.estimated_value or Decimal(0) for l in wins),Decimal(0))),
            'leads':[{'id':l.id,'name':l.couple_name,'booked':won(i.facts)} for l,i in leads]})
    return {'campaigns':result,'leads':[{'id':l.id,'name':l.couple_name,'date':l.event_date.isoformat(),
            'campaign_id':attribution.get(l.id)} for l,i in source.values()]}


class AttributionIn(BaseModel):
    lead_id:str


@router.post('/campaigns/{campaign_id}/attribution')
def attribute(campaign_id:str,payload:AttributionIn,_=Depends(csrf_admin),db:Session=Depends(get_db)):
    get_campaign(db,campaign_id)
    lead=db.get(Lead,payload.lead_id)
    insight=db.get(BookingInsight,payload.lead_id)
    if not lead or not lead.external_booking_id or not insight or not active_record(insight.facts):
        raise HTTPException(422,'Choose a synced, non-test, non-archived enquiry.')
    existing=db.get(CampaignAttribution,payload.lead_id)
    if existing and existing.campaign_id!=campaign_id:
        raise HTTPException(409,'This enquiry belongs to another campaign. Remove that attribution first.')
    if not existing:
        db.add(CampaignAttribution(lead_id=payload.lead_id,campaign_id=campaign_id))
        db.commit()
    return {'ok':True}


@router.delete('/campaigns/{campaign_id}/attribution/{lead_id}')
def remove_attribution(campaign_id:str,lead_id:str,_=Depends(csrf_admin),db:Session=Depends(get_db)):
    row=db.get(CampaignAttribution,lead_id)
    if row and row.campaign_id==campaign_id:
        db.delete(row)
        db.commit()
    return {'ok':True}
