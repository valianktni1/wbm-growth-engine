from datetime import datetime, timedelta, timezone
from uuid import uuid4
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, delete
from test_app import main, login
from app import website
from app.db import SessionLocal
from app.models import WebsiteEvent, WebsiteVisit, Setting


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(website, 'maintenance', lambda: None)
    with TestClient(main.app) as c:
        with SessionLocal() as db:
            db.execute(delete(WebsiteEvent)); db.execute(delete(WebsiteVisit))
            db.execute(delete(Setting).where(Setting.key.like('website-%'))); db.commit()
        website.rates.clear()
        yield c


def configure(c, goals=True):
    headers={'X-CSRF-Token': login(c)}
    r=c.put('/api/admin/website/setup', headers=headers, json={'enabled': True, 'goals_ready':goals, 'pages':{'/':'Home', '/packages/':'Packages'}})
    assert r.status_code==200, r.text
    return headers, r.json()['token']


def event(token, **changes):
    return {'token':token,'event_id':str(uuid4()),'visit_id':str(uuid4()),'kind':'page_view','path':'/','source':'Facebook','campaign':'','device':'Small screen',**changes}


def post(c, data): return c.post('/api/website/events',headers={'Origin':'https://perfectweddingsbymark.uk'},json=data)


def test_auth_origin_size_and_field_limits(client):
    assert client.get('/api/admin/website/report').status_code==401
    headers,token=configure(client)
    assert client.put('/api/admin/website/setup',json={'enabled':False,'pages':{'/':'Home'}}).status_code==403
    assert client.post('/api/website/events',json=event(token)).status_code==403
    assert post(client,event(token,path='/private-client/')).status_code==422
    assert post(client,event(token,email='couple@example.com')).status_code==422
    assert post(client,event('wrong')).status_code==403
    assert client.post('/api/website/events',content='x'*2049,headers={'Origin':'https://perfectweddingsbymark.uk'}).status_code==413
    assert client.get('/api/website/config?token='+token,headers={'Origin':'https://evil.example'}).status_code==403
    r=post(client,event(token));assert r.status_code==204
    assert r.headers['access-control-allow-origin']=='https://perfectweddingsbymark.uk'
    assert 'access-control-allow-credentials' not in r.headers


def test_visit_dedup_first_source_and_same_visit_funnel(client):
    _,token=configure(client)
    first=event(token)
    assert post(client,first).status_code==204
    assert post(client,first).status_code==204
    for kind in ['enquiry_start','enquiry_success','enquiry_success']:
        assert post(client,event(token,visit_id=first['visit_id'],source='Google',kind=kind)).status_code==204
    assert post(client,event(token,kind='enquiry_success')).status_code==204
    yesterday=datetime.now(timezone.utc)-timedelta(days=1)
    with SessionLocal() as db:
        for v in db.scalars(select(WebsiteVisit)):v.started_at=yesterday
        for e in db.scalars(select(WebsiteEvent)):e.occurred_at=yesterday
        db.commit()
    d=client.get('/api/admin/website/report').json()['current']
    assert d['visits']==2 and d['views']==1
    assert d['starts']==1 and d['enquiries']==2 and d['started_and_completed']==1
    assert d['sources']==[{'name':'Facebook','visits':2,'enquiries':2}]
    with SessionLocal() as db:
        assert all(v.id!=first['visit_id'] for v in db.scalars(select(WebsiteVisit)))


def test_unconnected_is_not_zero_conversion_and_campaign_persists(client):
    headers,token=configure(client,False)
    assert post(client,event(token,kind='enquiry_success')).status_code==409
    d=client.get('/api/admin/website/report').json()
    assert not d['goals_ready'] and not d['comparison_ready'] and d['google'] is None
    assert d['booking_attribution'].startswith('Not connected')
    r=client.post('/api/admin/website/campaign-link',headers=headers,json={'name':'Hazel Gap post','source':'facebook','path':'/packages/'})
    assert r.status_code==200
    from urllib.parse import urlsplit,parse_qs
    slug=parse_qs(urlsplit(r.json()['url']).query)['utm_campaign'][0]
    assert slug in client.get('/api/admin/website/setup').json()['website']['campaigns']
    assert post(client,event(token,campaign=slug)).status_code==204
    assert post(client,event(token,campaign='unregistered-name')).status_code==422


def test_cache_only_dashboard_and_failure_retains_report(client,monkeypatch):
    configure(client)
    previous={'start':'2026-08-01','end':'2026-08-28','totals':{'clicks':23},'updated_at':'2026-09-01T12:00:00+00:00'}
    with SessionLocal() as db:
        website.put_value(db,'website-google',{'property':'sc-domain:perfectweddingsbymark.uk'})
        website.put_value(db,'website-google-report',previous);db.commit()
    def fail(_):raise RuntimeError('upstream confidential error')
    monkeypatch.setattr(website,'fetch_google',fail)
    assert client.get('/api/admin/website/report').json()['google']==previous
    website.refresh_google()
    d=client.get('/api/admin/website/report').json()
    assert d['google']==previous and d['google_status']['state']=='error'
    assert 'confidential' not in str(d)


def test_google_key_sanitized_private_and_disconnect(client,monkeypatch,tmp_path):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048).private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
    raw={'type':'service_account','client_email':'growth@wbm-project.iam.gserviceaccount.com','private_key':private,'private_key_id':'test','token_uri':'https://evil.example/token','subject':'owner@example.com'}
    creds,safe=website.make_credentials(raw)
    assert safe['token_uri']=='https://oauth2.googleapis.com/token' and 'subject' not in safe
    assert creds.scopes==website.SCOPES
    monkeypatch.setattr(website,'credentials_path',lambda:tmp_path/'key.json')
    headers,_=configure(client)
    r=client.post('/api/admin/website/google-connect',headers=headers,json={'property':'sc-domain:perfectweddingsbymark.uk','credentials':raw})
    assert r.status_code==200,r.text
    assert (tmp_path/'key.json').stat().st_mode & 0o777==0o600
    assert private not in client.get('/api/admin/website/setup').text
    assert client.delete('/api/admin/website/google-connect').status_code==403
    assert client.delete('/api/admin/website/google-connect',headers=headers).status_code==200
    assert not (tmp_path/'key.json').exists()


def test_google_queries_use_separate_totals_final_dates_and_bounded_calls(client,monkeypatch,tmp_path):
    import requests
    from types import SimpleNamespace
    key=tmp_path/'key.json';key.write_text('{}')
    monkeypatch.setattr(website,'credentials_path',lambda:key)
    monkeypatch.setattr(website,'make_credentials',lambda _: (SimpleNamespace(token='private-test-token',refresh=lambda request:None),{}))
    calls=[]
    class Session:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def close(self):pass
        def post(self,url,**kwargs):
            calls.append((url,kwargs)); dims=kwargs['json']['dimensions']
            return SimpleNamespace(status_code=200,json=lambda:{'rows':[{'keys':['top'] if dims else [],'clicks':4 if dims else 100,'impressions':200,'ctr':.5,'position':3}]})
    monkeypatch.setattr(requests,'Session',Session)
    result=website.fetch_google('sc-domain:perfectweddingsbymark.uk')
    assert result['totals']['clicks']==100 and result['queries'][0]['clicks']==4
    assert len(calls)==5
    assert all(k['timeout']==10 and k['allow_redirects'] is False and k['json']['dataState']=='final' for _,k in calls)
    assert calls[0][1]['json']['dimensions']==[] and calls[1][1]['json']['dimensions']==[]
    assert 'sc-domain%3Aperfectweddingsbymark.uk' in calls[0][0]


def test_rate_limit_and_resume_coverage(client):
    headers,token=configure(client)
    first=event(token)
    for _ in range(60):assert post(client,first).status_code==204
    assert post(client,first).status_code==429
    assert client.put('/api/admin/website/setup',headers=headers,json={'enabled':False,'pages':{'/':'Home'}}).status_code==200
    assert post(client,event(token)).status_code==403
    assert client.get('/api/admin/website/report?days=999').status_code==422
