from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from app.intelligence import priority, performance_rows

NOW = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)


def sample(**changes):
    lead = SimpleNamespace(id='lead', couple_name='Jo & Sam', primary_first_name='Jo', partner_first_name='Sam',
        event_date=date(2027, 8, 1), venue='The Barn', external_booking_id='booking', estimated_value=999,
        referral_source='Google', package_interest='Gold', quote_items=[{'type':'addon','name':'Album','total':100}])
    facts = dict(source_created_at='2026-08-01T00:00:00Z', booking_status='quoted', quote_sent_at='2026-09-01T10:00:00Z',
                 last_contact_at='2026-09-01T10:00:00Z', mail_status='unavailable')
    facts.update(changes)
    return lead, SimpleNamespace(facts=facts, snoozed_until=None, received_at=NOW)


def test_replies_take_priority_and_recent_contact_prevents_chasing():
    lead, insight = sample(last_incoming_at='2026-09-06T10:00:00Z')
    card = priority(lead, insight, NOW)
    assert card['kind'] == 'reply' and card['draft'] == ''
    assert card['url'].endswith('/activity')
    insight.facts['last_contact_at'] = '2026-09-07T10:00:00Z'
    assert priority(lead, insight, NOW) is None


def test_no_sales_chasing_for_terminal_test_archived_or_suppressed():
    for change in ({'booking_status':'cancelled'}, {'booking_status':'confirmed'}, {'deposit_paid':True},
                   {'is_test':True}, {'archived':True}, {'suppressed':True}):
        assert priority(*sample(**change), NOW) is None


def test_snooze_and_unknown_mail_and_link_evidence():
    lead, insight = sample()
    card = priority(lead, insight, NOW)
    assert card['kind'] == 'waiting'
    assert 'no reply' not in card['reason'].lower()
    insight.snoozed_until = NOW + timedelta(hours=24)
    assert priority(lead, insight, NOW) is None
    insight.snoozed_until = NOW - timedelta(hours=1)
    insight.facts['quote_link_at'] = '2026-09-07T11:00:00Z'
    assert priority(lead, insight, NOW)['kind'] == 'interest'


def test_performance_uses_original_cohort_excludes_tests_and_counts_addons_once():
    a = sample(booking_status='confirmed')
    a[0].quote_items += [{'type':'addon','name':'Album','total':50}, {'type':'discount','name':'Discount','total':-20}]
    b = sample(booking_status='cancelled', deposit_paid=True)
    c = sample(is_test=True)
    d = sample(archived=True)
    result = performance_rows([a,b,c,d], date(2026,8,1), date(2026,8,31))
    assert result['enquiries'] == 2 and result['bookings'] == 1
    assert result['conversion'] == 50 and result['booked_value'] == 999
    assert result['groups']['addons'] == [{'name':'Album','bookings':1,'booked_value':150}]
    assert result['groups']['sources'][0]['small_sample']
    assert performance_rows([a], date(2026,9,1))['enquiries'] == 0
