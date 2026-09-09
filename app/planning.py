"""Year targets, recorded conversion evidence, venue assets and actionable weekly reviews."""
import hashlib
import json
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from .config import get_settings
from .db import get_db
from .security import current_admin, csrf_admin
from .models import Setting, Campaign
from .intelligence import records, active_record, won, utc, priority, performance_rows
from .gaps import london_today, eligible, lead_card, Creative

router=APIRouter(prefix='/api/admin/planning')


class MonthTotal(BaseModel):
    month:int=Field(ge=1,le=12)
    bookings:int=Field(ge=0)
    booked_value:Decimal=Field(ge=0)


class YearTotal(BaseModel):
    year:int
    checked_at:datetime
    bookings:int=Field(ge=0)
    booked_value:Decimal=Field(ge=0)
    months:list[MonthTotal]
    scope:str


def live_year(year):
    settings=get_settings()
    if not 2000<=year<=2100:
        raise HTTPException(422,'Choose a year between 2000 and 2100.')
    if not settings.booking_webhook_key:
        raise HTTPException(503,'The Booking integration is not configured.')
    request=Request(settings.booking_base_url+'/api/integrations/growth/planning?'+urlencode({'year':year}),
                    headers={'X-Integration-Key':settings.booking_webhook_key,'User-Agent':'WBM-Growth/1.4'})
    try:
        with urlopen(request,timeout=settings.booking_timeout_seconds) as response:
            data=YearTotal.model_validate(json.load(response))
        if data.year!=year or len(data.months)!=12 or {m.month for m in data.months}!=set(range(1,13)):
            raise ValueError('Incomplete year')
        if sum(m.bookings for m in data.months)!=data.bookings or sum((m.booked_value for m in data.months),Decimal(0))!=data.booked_value:
            raise ValueError('Inconsistent totals')
        if abs((datetime.now(timezone.utc)-utc(data.checked_at)).total_seconds())>300:
            raise ValueError('Stale totals')
        return data.model_dump(mode='json')
    except Exception as exc:
        raise HTTPException(503,'Year totals are unavailable. Check the Booking connection and V8.43 update; no zero totals have been assumed.') from exc


def save_setting(db,key,value):
    row=db.get(Setting,key)
    if row:row.value=value
    else:db.add(Setting(key=key,value=value))


class TargetIn(BaseModel):
    bookings:int=Field(ge=0,le=1000)
    value:Decimal=Field(ge=0,le=10000000,max_digits=12,decimal_places=2)


@router.put('/targets/{year}')
def targets(year:int,payload:TargetIn,_=Depends(csrf_admin),db:Session=Depends(get_db)):
    if not 2000<=year<=2100:raise HTTPException(422,'Choose a year between 2000 and 2100.')
    save_setting(db,f'year-target:{year}',payload.model_dump(mode='json'));db.commit()
    return {'ok':True}


def get_year(db,year):
    current=live_year(year)
    today=london_today()
    previous=today.replace(year=today.year-1,day=min(today.day,monthrange(today.year-1,today.month)[1]))
    target=db.get(Setting,f'year-target:{year}')
    saved=db.get(Setting,f'year-snapshot:{year-1}:{previous.isoformat()}')
    comparison=None
    if saved:
        comparison={'snapshot_date':previous.isoformat(),'wedding_year':year-1,
                    'bookings':saved.value['bookings'],'booked_value':saved.value['booked_value'],
                    'booking_difference':current['bookings']-saved.value['bookings'],
                    'value_difference':str(Decimal(current['booked_value'])-Decimal(saved.value['booked_value']))}
    # Snapshots are observations made when the planner/weekly review is opened.
    # They are not reconstructed from today's statuses or claimed to be daily automation.
    save_setting(db,f'year-snapshot:{year}:{today.isoformat()}',current)
    db.commit()
    return {**current,'target':target.value if target else None,'comparison':comparison,
            'comparison_note':'Snapshots are saved when this year is viewed. A same-calendar-day snapshot for the previous wedding year is needed; historical totals are never invented.'}


@router.get('/year')
def year_report(year:int,_=Depends(current_admin),db:Session=Depends(get_db)):
    return get_year(db,year)


def conversion(rows,start,end,now):
    counts={'enquiries':0,'quote_sent':0,'accepted':0,'fee_recorded':0,'booked':0,'cancelled':0}
    times={k:[] for k in ('enquiry_to_quote','quote_to_acceptance','acceptance_to_fee')}
    holding={'prepare':0,'quote':0,'fee':0,'confirmed_without_fee':0}
    waits=[];missing=0;coverage=[]
    for lead,insight in rows:
        if not insight:missing+=1;continue
        f=insight.facts
        if not active_record(f):continue
        created=utc(f.get('source_created_at'))
        if not created:missing+=1;continue
        coverage.append(created.date())
        if created.date()<start or created.date()>end:continue
        counts['enquiries']+=1
        sent=utc(f.get('first_quote_sent_at'))
        accepted=utc(f.get('quote_accepted_at'))
        paid=date.fromisoformat(f['deposit_paid_date']) if f.get('deposit_paid_date') else None
        has_sent=bool(sent or f.get('quote_sent_at'))
        has_accepted=bool(accepted or f.get('quote_accepted'))
        has_paid=bool(paid or f.get('deposit_paid'))
        counts['quote_sent']+=int(has_sent);counts['accepted']+=int(has_accepted)
        counts['fee_recorded']+=int(has_paid);counts['booked']+=int(bool(won(f)))
        counts['cancelled']+=int(f.get('booking_status')=='cancelled')
        # Paired evidence only. Missing/negative intervals never become zero-day results.
        if sent and sent>=created:times['enquiry_to_quote'].append((sent-created).total_seconds()/86400)
        if sent and accepted and accepted>=sent:times['quote_to_acceptance'].append((accepted-sent).total_seconds()/86400)
        if accepted and paid and paid>=accepted.date():times['acceptance_to_fee'].append((paid-accepted.date()).days)
        if won(f):
            if not has_paid:holding['confirmed_without_fee']+=1
            continue
        if not eligible(lead,insight) or lead.event_date<now.date():continue
        stage='fee' if has_accepted else ('quote' if has_sent else 'prepare')
        holding[stage]+=1
        entered=accepted if stage=='fee' else sent if stage=='quote' else created
        contacted=utc(f.get('last_contact_at'))
        incoming=utc(f.get('last_incoming_at'))
        days=(now-entered).days if entered else None
        threshold=7 if stage=='quote' else 3
        if days is not None and days>=threshold and (not contacted or now-contacted>=timedelta(days=3)):
            waits.append({**lead_card(lead,insight),'stage':stage,'days':days,
                'reason':('Review the incoming message first.' if incoming and (not contacted or incoming>contacted) else 'Review all recent contact before deciding on a follow-up.')})
    return {'booking_conversion':round(counts['booked']/counts['enquiries']*100,1) if counts['enquiries'] else None,'counts':counts,'holding':holding,'waits':sorted(waits,key=lambda x:-x['days']),
            'timings':{k:{'median_days':round(median(v),1) if v else None,'sample':len(v)} for k,v in times.items()},
            'missing_evidence':missing,'earliest_synced_enquiry':min(coverage).isoformat() if coverage else None,
            'start':start.isoformat(),'end':end.isoformat()}


@router.get('/conversion')
def conversion_report(start:date,end:date,_=Depends(current_admin),db:Session=Depends(get_db)):
    if start>end:raise HTTPException(422,'The start date must be before the end date.')
    return conversion(records(db),start,end,datetime.now(timezone.utc))


def venue_key(name):return 'venue-kit:'+hashlib.sha256(' '.join(name.split()).casefold().encode()).hexdigest()[:40]


@router.put('/venue-kit')
def save_venue(payload:Creative,_=Depends(csrf_admin),db:Session=Depends(get_db)):
    if not payload.venue or not payload.venue.strip():raise HTTPException(422,'Enter the venue name.')
    save_setting(db,venue_key(payload.venue),payload.model_dump(mode='json'));db.commit()
    return {'ok':True}


@router.get('/venues')
def venues(_=Depends(current_admin),db:Session=Depends(get_db)):
    groups=performance_rows(records(db))['groups']['venues']
    kits=[s.value for s in db.scalars(select(Setting).where(Setting.key.like('venue-kit:%')))]
    return {'venues':groups,'kits':kits}


@router.get('/weekly')
def weekly(year:int,_=Depends(current_admin),db:Session=Depends(get_db)):
    now=datetime.now(timezone.utc);rows=records(db)
    attention=[p for l,i in rows if (p:=priority(l,i,now))]
    order={'reply':0,'accepted':1,'new':2,'interest':3,'waiting':4}
    attention.sort(key=lambda p:(order[p['kind']],p['event_date']))
    actions=[{'title':p['title']+' — '+p['couple_name'],'reason':p['reason'],'url':p['url'],'view':None} for p in attention[:3]]
    totals=None;availability_error=None
    try:totals=get_year(db,year)
    except HTTPException as exc:availability_error=exc.detail
    if totals:
        future=[m for m in totals['months'] if date(year,m['month'],monthrange(year,m['month'])[1])>=london_today()]
        if future:
            quiet=min(future,key=lambda m:m['bookings'])
            actions.append({'title':f'Review {date(year,quiet["month"],1).strftime("%B %Y")} availability',
                'reason':f'{quiet["bookings"]} weddings currently confirmed. Check free dates and holiday blocks before deciding whether to promote this month.',
                'view':'gaps','month':f'{year}-{quiet["month"]:02d}','url':None})
        if not totals['target']:
            actions.append({'title':f'Set your {year} booking target','reason':'Choose your own wedding-count and agreed-value goals so the plan can measure the gap.','view':'planning','url':None})
        else:
            gap=max(0,totals['target']['bookings']-totals['bookings'])
            actions.append({'title':f'{gap} more bookings to your {year} count target' if gap else f'Your {year} count target is reached',
                'reason':f'{totals["bookings"]} weddings confirmed against your chosen target of {totals["target"]["bookings"]}. Value targets are shown separately in the year planner.',
                'view':'planning','url':None})
    venue_rows=performance_rows(rows)['groups']['venues']
    venue=next((v for v in venue_rows if v['bookings'] and v['name']!='Not recorded'),None)
    if venue:
        actions.append({'title':'Prepare a venue post: '+venue['name'],
            'reason':f'{venue["enquiries"]} synced enquiries and {venue["bookings"]} bookings recorded. This suggests a relevant venue to review, not proof a new post will convert.',
            'view':'venues-plan','venue':venue['name'],'url':None})
    drafts=db.scalar(select(Campaign).where(Campaign.status=='draft').order_by(Campaign.created_at.desc()))
    if drafts:actions.append({'title':'Review your saved campaign: '+drafts.name,'reason':'A private draft is ready to review. Check availability again before copying and posting.','view':'campaigns','url':None})
    return {'generated_at':now.isoformat(),'year':year,'actions':actions[:7],'totals_error':availability_error,
            'note':'An on-demand weekly review, updated when opened. Suggestions are based on recorded facts and your targets; nothing is sent or posted.'}
