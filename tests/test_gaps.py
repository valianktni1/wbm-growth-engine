from datetime import timedelta, datetime, timezone
from decimal import Decimal
from io import StringIO
import json
from uuid import uuid4
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_app import main, login
from app import gaps
from app.db import SessionLocal
from app.models import Lead, BookingInsight, Campaign


def live(start, end, status='available'):
    return gaps.Availability(start=start,end=end,checked_at=datetime.now(timezone.utc),
        days=[gaps.Day(date=start+timedelta(days=i),status=status) for i in range((end-start).days+1)],
        packages=[gaps.Package(id='platinum',name='Platinum',price=Decimal('1350.00'))])


def test_campaign_lifecycle_attribution_and_live_booking_changes(monkeypatch):
    day=gaps.london_today()+timedelta(days=20)
    monkeypatch.setattr(gaps,'booking_window',lambda start,end:live(start,end))
    with TestClient(main.app) as client:
        assert client.get(f'/api/admin/gaps/calendar?start={day}&end={day}').status_code==401
        csrf=login(client); headers={'X-CSRF-Token':csrf}
        plan={'dates':[str(day)],'package_id':'platinum','channel':'facebook'}
        assert client.post('/api/admin/gaps/draft',json=plan).status_code==403
        draft=client.post('/api/admin/gaps/draft',headers=headers,json=plan).json()
        assert '£1,350.00' in draft['draft'] and '£1,299' not in draft['draft']
        payload={**plan,'package_snapshot':draft['package'],'name':'Autumn availability','draft':draft['draft']}
        result=client.post('/api/admin/gaps/campaigns',headers=headers,json=payload)
        assert result.status_code==201,result.text
        cid=result.json()['id']; url='/api/admin/gaps/campaigns/'+cid
        with SessionLocal() as db:
            lead=Lead(external_booking_id=str(uuid4()),primary_first_name='Jo',partner_first_name='Sam',
                      event_date=day,venue='Barn',email='jo@example.com',estimated_value=1350)
            db.add(lead);db.flush();lid=lead.id
            db.add(BookingInsight(lead_id=lid,facts={'booking_status':'quoted','source_created_at':datetime.now(timezone.utc).isoformat()}))
            db.commit()
        calendar=client.get(f'/api/admin/gaps/calendar?start={day}&end={day}').json()
        assert any(l['id']==lid for l in calendar['days'][0]['enquiries'])
        assert client.post(url+'/attribution',headers=headers,json={'lead_id':lid}).status_code==200
        assert client.post(url+'/attribution',headers=headers,json={'lead_id':lid}).status_code==200
        campaigns=lambda:next(c for c in client.get('/api/admin/gaps/campaigns').json()['campaigns'] if c['id']==cid)
        assert campaigns()['enquiries']==1 and campaigns()['bookings']==0
        with SessionLocal() as db:
            insight=db.get(BookingInsight,lid);insight.facts={**insight.facts,'booking_status':'confirmed'};db.commit()
        assert campaigns()['bookings']==1 and campaigns()['booked_value']==1350
        assert client.patch(url,headers=headers,json={'name':'Edited','draft':'My reviewed post'}).status_code==200
        assert client.post(url+'/published',headers=headers).status_code==200
        assert client.patch(url,headers=headers,json={'name':'Changed','draft':'New'}).status_code==409
        with SessionLocal() as db:
            assert db.get(Campaign,cid).draft=='My reviewed post'
        second=client.post('/api/admin/gaps/campaigns',headers=headers,json=payload).json()['id']
        assert client.post('/api/admin/gaps/campaigns/'+second+'/attribution',headers=headers,json={'lead_id':lid}).status_code==409
        monkeypatch.setattr(gaps,'booking_window',lambda start,end:live(start,end,'blocked'))
        assert client.post(url+'/check',headers=headers).status_code==409
        assert client.post('/api/admin/gaps/campaigns',headers=headers,json=payload).status_code==409
        assert client.delete(url+'/attribution/'+lid,headers=headers).status_code==200
        assert campaigns()['enquiries']==0


def test_price_change_between_generate_save_and_copy_is_rejected(monkeypatch):
    day=gaps.london_today()+timedelta(days=21)
    monkeypatch.setattr(gaps,'booking_window',lambda start,end:live(start,end))
    with TestClient(main.app) as client:
        headers={'X-CSRF-Token':login(client)}
        plan={'dates':[str(day)],'package_id':'platinum','channel':'google'}
        draft=client.post('/api/admin/gaps/draft',headers=headers,json=plan).json()
        payload={**plan,'package_snapshot':draft['package'],'name':'Price check','draft':draft['draft']}
        cid=client.post('/api/admin/gaps/campaigns',headers=headers,json=payload).json()['id']
        def updated(start,end):
            data=live(start,end);data.packages[0].price=Decimal('1400.00');return data
        monkeypatch.setattr(gaps,'booking_window',updated)
        assert client.post('/api/admin/gaps/campaigns',headers=headers,json=payload).status_code==409
        assert client.post('/api/admin/gaps/campaigns/'+cid+'/check',headers=headers).status_code==409


def test_unknown_stale_and_incomplete_data_never_become_free_dates(monkeypatch):
    today=gaps.london_today()
    def response(data):
        return lambda *a,**k:StringIO(json.dumps(data))
    data=live(today,today+timedelta(days=1)).model_dump(mode='json')
    monkeypatch.setattr(gaps,'urlopen',response(data))
    assert len(gaps.booking_window(today,today+timedelta(days=1)).days)==2
    data['days'].pop()
    with pytest.raises(HTTPException) as error:gaps.booking_window(today,today+timedelta(days=1))
    assert error.value.status_code==503
    data=live(today,today).model_dump(mode='json');data['checked_at']='2020-01-01T00:00:00Z'
    monkeypatch.setattr(gaps,'urlopen',response(data))
    with pytest.raises(HTTPException):gaps.booking_window(today,today)
    def fail(*args,**kwargs):raise TimeoutError()
    monkeypatch.setattr(gaps,'urlopen',fail)
    with pytest.raises(HTTPException) as error:gaps.booking_window(today,today)
    assert error.value.status_code==503
    for start,end in [(today-timedelta(days=1),today),(today,today+timedelta(days=184)),(today+timedelta(days=1),today)]:
        with pytest.raises(HTTPException) as error:gaps.booking_window(start,end)
        assert error.value.status_code==422


def test_excluded_leads_never_recommended():
    from types import SimpleNamespace
    lead=SimpleNamespace()
    assert not gaps.eligible(lead,None)
    for flags in ({'is_test':True},{'archived':True},{'suppressed':True},{'booking_status':'cancelled'}, {'booking_status':'confirmed'},{'deposit_paid':True}):
        assert not gaps.eligible(lead,SimpleNamespace(facts={'booking_status':'quoted',**flags}))
