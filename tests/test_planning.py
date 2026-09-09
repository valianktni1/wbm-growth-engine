from datetime import date, datetime, timedelta, timezone
from io import StringIO
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
import json
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_app import main, login
from app import planning, gaps
from app.db import SessionLocal
from app.models import Setting


def totals(year,count=2):
    return {'year':year,'checked_at':datetime.now(timezone.utc).isoformat(),'bookings':count,
            'booked_value':str(count*1350),'months':[{'month':m,'bookings':count if m==8 else 0,
            'booked_value':str(count*1350 if m==8 else 0)} for m in range(1,13)],'scope':'All real Booking weddings'}


def test_year_targets_live_totals_and_honest_snapshots(monkeypatch):
    today=date(2026,9,8)
    monkeypatch.setattr(planning,'london_today',lambda:today)
    monkeypatch.setattr(planning,'live_year',totals)
    with TestClient(main.app) as client:
        assert client.get('/api/admin/planning/year?year=2027').status_code==401
        headers={'X-CSRF-Token':login(client)}
        assert client.put('/api/admin/planning/targets/2027',json={'bookings':20,'value':25000}).status_code==403
        result=client.put('/api/admin/planning/targets/2027',headers=headers,json={'bookings':20,'value':'25000.00'})
        assert result.status_code==200,result.text
        data=client.get('/api/admin/planning/year?year=2027').json()
        assert data['bookings']==2 and data['target']['bookings']==20
        assert data['comparison'] is None
        with SessionLocal() as db:
            assert db.get(Setting,'year-snapshot:2027:2026-09-08').value['bookings']==2
            planning.save_setting(db,'year-snapshot:2026:2025-09-08',totals(2026,1));db.commit()
        data=client.get('/api/admin/planning/year?year=2027').json()
        assert data['comparison']['booking_difference']==1
        assert data['comparison']['value_difference']=='1350'
        assert client.put('/api/admin/planning/targets/2027',headers=headers,json={'bookings':-1,'value':10}).status_code==422
        assert client.get('/api/admin/planning/weekly?year=2027').status_code==200
        def fail(year):raise HTTPException(503,'Unavailable source')
        monkeypatch.setattr(planning,'live_year',fail)
        data=client.get('/api/admin/planning/weekly?year=2027').json()
        assert data['totals_error']=='Unavailable source'
        assert not any(a.get('month') for a in data['actions'])


def test_live_total_validation_fails_closed(monkeypatch):
    data=totals(2027)
    monkeypatch.setattr(planning,'urlopen',lambda *a,**k:StringIO(json.dumps(data)))
    assert planning.live_year(2027)['bookings']==2
    data['bookings']=99
    with pytest.raises(HTTPException) as error:planning.live_year(2027)
    assert error.value.status_code==503
    data=totals(2027);data['checked_at']='2000-01-01T00:00:00Z'
    with pytest.raises(HTTPException):planning.live_year(2027)


def sample(facts):
    now=datetime(2026,9,8,tzinfo=timezone.utc)
    lead=SimpleNamespace(id=str(uuid4()),external_booking_id='booking',couple_name='Jo & Sam',
        event_date=date(2027,7,10),venue='Barn',quote_status='sent',estimated_value=1350)
    return lead,SimpleNamespace(facts={'source_created_at':'2026-08-01T00:00:00Z','booking_status':'quoted',**facts},received_at=now)


def test_conversion_uses_first_quote_and_only_paired_evidence():
    rows=[sample({'first_quote_sent_at':'2026-08-03T00:00:00Z','quote_sent_at':'2026-09-05T00:00:00Z',
                  'quote_accepted_at':'2026-08-08T00:00:00Z','quote_accepted':True,
                  'deposit_paid_date':'2026-08-09','deposit_paid':True,'booking_status':'confirmed'}),
          sample({'booking_status':'confirmed'}),sample({'quote_sent_at':'2026-08-20T00:00:00Z'}),
          sample({'is_test':True}),sample({'archived':True}),sample({'suppressed':True})]
    d=planning.conversion(rows,date(2026,8,1),date(2026,8,31),datetime(2026,9,8,tzinfo=timezone.utc))
    assert d['counts']['enquiries']==4 and d['counts']['booked']==2
    assert d['booking_conversion']==50
    assert d['timings']['enquiry_to_quote']=={'median_days':2.0,'sample':1}
    assert d['timings']['quote_to_acceptance']=={'median_days':5.0,'sample':1}
    assert d['timings']['acceptance_to_fee']=={'median_days':1,'sample':1}
    assert d['holding']['confirmed_without_fee']==1
    assert d['waits']==[] # Latest send alone is not a known first-stage timestamp.


def test_stall_prompts_respect_recent_contact_and_unknown_timings():
    now=datetime(2026,9,8,tzinfo=timezone.utc)
    old=sample({'first_quote_sent_at':'2026-08-03T00:00:00Z'})
    recent=sample({'first_quote_sent_at':'2026-08-03T00:00:00Z','last_contact_at':'2026-09-07T00:00:00Z'})
    d=planning.conversion([old,recent],date(2026,8,1),date(2026,8,31),now)
    assert len(d['waits'])==1 and d['waits'][0]['stage']=='quote'
    assert d['timings']['quote_to_acceptance']['median_days'] is None


def test_venue_materials_and_campaign_snapshot(monkeypatch):
    day=gaps.london_today()+timedelta(days=400)
    def live(start,end):return gaps.Availability(start=start,end=end,checked_at=datetime.now(timezone.utc),
        days=[gaps.Day(date=start+timedelta(days=i),status='available') for i in range((end-start).days+1)],packages=[])
    monkeypatch.setattr(gaps,'booking_window',live)
    kit={'venue':'Example Barn','testimonial':'A wonderful day.','credited_to':'Jo & Sam',
         'photo_urls':['https://example.com/photo.jpg'],'link':'https://example.com/venue'}
    with TestClient(main.app) as client:
        headers={'X-CSRF-Token':login(client)}
        assert client.put('/api/admin/planning/venue-kit',headers=headers,json={**kit,'credited_to':''}).status_code==422
        assert client.put('/api/admin/planning/venue-kit',headers=headers,json={**kit,'photo_urls':['javascript:alert(1)']}).status_code==422
        assert client.put('/api/admin/planning/venue-kit',headers=headers,json=kit).status_code==200
        assert any(k['venue']=='Example Barn' for k in client.get('/api/admin/planning/venues').json()['kits'])
        payload={'dates':[str(day)],'creative':kit,'channel':'facebook'}
        draft=client.post('/api/admin/gaps/draft',headers=headers,json=payload).json()['draft']
        assert 'Example Barn' in draft and 'A wonderful day.' in draft and 'Jo & Sam' in draft
        response=client.post('/api/admin/gaps/campaigns',headers=headers,json={**payload,'name':'Venue campaign','draft':draft})
        assert response.status_code==201,response.text
        cid=response.json()['id']
        result=next(c for c in client.get('/api/admin/gaps/campaigns').json()['campaigns'] if c['id']==cid)
        assert result['creative']['photo_urls']==kit['photo_urls']
