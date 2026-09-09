import importlib
import os
from pathlib import Path

os.environ.update({
    "DATABASE_URL": "sqlite:///./test-growth-engine.db",
    "STORAGE_ROOT": "./test-storage",
    "BACKUP_ROOT": "./test-backups",
    "SESSION_SECRET": "test-secret-that-is-long-enough-for-tests-only-123456789",
    "ADMIN_EMAIL": "mark@example.com",
    "ADMIN_PASSWORD": "CorrectHorseBatteryStaple",
    "COOKIE_SECURE": "false",
    "BOOKING_ENQUIRY_FORWARDING": "false",
    "AUTOMATION_SEND_ENABLED": "false",
    "BOOKING_WEBHOOK_KEY": "test-booking-webhook-key-which-is-long-and-private-123456789",
})

from fastapi.testclient import TestClient
from app import main
from app.models import Admin
from app.security import hash_password


def setup_module():
    Path("test-growth-engine.db").unlink(missing_ok=True)


def login(client):
    response = client.post("/api/auth/login", json={"email": "mark@example.com", "password": "CorrectHorseBatteryStaple"})
    assert response.status_code == 200
    return response.json()["csrf_token"]


def enquiry_payload():
    return {
        "primary_first_name": "Sophie", "partner_first_name": "Liam", "email": "sophie@example.com",
        "phone": "07123456789", "event_date": "2027-09-18", "location": "Heaton House Farm",
        "package_interest": "Gold", "heard_about_us": "Google venue search", "message": "We love natural photographs.",
        "landing_page": "https://perfectweddingsbymark.uk/heaton-house-farm", "campaign": "venue-pages",
        "privacy_agreed": True, "website": ""
    }


def test_growth_capture_does_not_create_a_competing_proposal(monkeypatch):
    monkeypatch.setattr(main, "check_booking_availability", lambda _: "Available")
    with TestClient(main.app) as client:
        csrf = login(client)
        response = client.post("/api/admin/leads", headers={"X-CSRF-Token": csrf}, json={**enquiry_payload(), "forward_to_booking": False})
        assert response.status_code == 201, response.text
        lead = response.json()
        assert lead["availability"] == "Available"
        assert lead["proposal"] is None
        detail = client.get(f"/api/admin/leads/{lead['id']}").json()
        assert detail["automations"] == []
        retired = client.post(
            f"/api/admin/leads/{lead['id']}/proposal/publish",
            headers={"X-CSRF-Token": csrf},
        )
        assert retired.status_code == 410


def test_public_enquiry_requires_privacy(monkeypatch):
    monkeypatch.setattr(main, "check_booking_availability", lambda _: "Available")
    with TestClient(main.app) as client:
        payload = enquiry_payload()
        payload["email"] = "another@example.com"
        payload["privacy_agreed"] = False
        response = client.post("/api/public/enquiries", json=payload)
        assert response.status_code == 422


def test_honeypot_rejected(monkeypatch):
    monkeypatch.setattr(main, "check_booking_availability", lambda _: "Available")
    with TestClient(main.app) as client:
        payload = enquiry_payload()
        payload["email"] = "robot@example.com"
        payload["website"] = "spam.example"
        response = client.post("/api/public/enquiries", json=payload)
        assert response.status_code == 400


def test_health_is_safe():
    with TestClient(main.app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "password" not in response.text.lower()


def test_admin_can_change_growth_login_and_close_other_sessions():
    old_email = "account-test@example.com"
    new_email = "changed-account@example.com"
    old_password = "OriginalAccountPassword123"
    new_password = "ReplacementAccountPassword456"
    with TestClient(main.app) as first, TestClient(main.app) as second:
        with main.SessionLocal() as db:
            db.query(Admin).filter(Admin.email.in_([old_email, new_email])).delete(synchronize_session=False)
            db.add(Admin(email=old_email, password_hash=hash_password(old_password)))
            db.commit()

        def sign_in(client, email=old_email, password=old_password):
            result = client.post("/api/auth/login", json={"email": email, "password": password})
            assert result.status_code == 200, result.text
            return result.json()["csrf_token"]

        csrf_first = sign_in(first)
        sign_in(second)
        account = first.get("/api/admin/account")
        assert account.status_code == 200
        assert account.json()["email"] == old_email
        assert "password" not in account.text.lower()
        assert first.put("/api/admin/account/password", json={
            "current_password": old_password, "new_password": new_password,
            "confirm_password": new_password,
        }).status_code == 403
        wrong = first.put("/api/admin/account/password", headers={"X-CSRF-Token": csrf_first}, json={
            "current_password": "IncorrectPassword999", "new_password": new_password,
            "confirm_password": new_password,
        })
        assert wrong.status_code == 400
        mismatch = first.put("/api/admin/account/password", headers={"X-CSRF-Token": csrf_first}, json={
            "current_password": old_password, "new_password": new_password,
            "confirm_password": "DifferentAccountPassword789",
        })
        assert mismatch.status_code == 422
        changed = first.put("/api/admin/account/password", headers={"X-CSRF-Token": csrf_first}, json={
            "current_password": old_password, "new_password": new_password,
            "confirm_password": new_password,
        })
        assert changed.status_code == 200, changed.text
        csrf_first = changed.json()["csrf_token"]
        assert second.get("/api/admin/account").status_code == 401
        assert first.get("/api/admin/account").status_code == 200
        assert first.post("/api/auth/login", json={"email": old_email, "password": old_password}).status_code == 401

        changed_email = first.put("/api/admin/account/email", headers={"X-CSRF-Token": csrf_first}, json={
            "current_password": new_password, "new_email": new_email,
        })
        assert changed_email.status_code == 200, changed_email.text
        assert changed_email.json()["email"] == new_email
        assert first.get("/api/admin/account").json()["email"] == new_email
        assert first.post("/api/auth/login", json={"email": old_email, "password": new_password}).status_code == 401
        assert first.post("/api/auth/login", json={"email": new_email, "password": new_password}).status_code == 200

        with main.SessionLocal() as db:
            db.query(Admin).filter(Admin.email.in_([old_email, new_email])).delete(synchronize_session=False)
            db.commit()


def test_intelligence_sync_reporting_and_snooze(monkeypatch):
    monkeypatch.setattr(main, 'check_booking_availability', lambda _: 'Available')
    from datetime import datetime, timezone
    headers = {'X-Integration-Key': os.environ['BOOKING_WEBHOOK_KEY']}
    payload = {'booking_id':'insight-1','event_id':'insight-event-1', 'primary_first_name':'Kit',
               'partner_first_name':'Alex','email':'kit@example.com','event_date':'2030-06-01','venue':'Barn',
               'intelligence':{'source_created_at':'2026-09-01T10:00:00Z','booking_status':'enquiry'}}
    with TestClient(main.app) as client:
        assert client.get('/api/admin/intelligence/today').status_code == 401
        csrf = login(client)
        created = client.post('/api/integrations/booking/enquiry', headers=headers, json=payload)
        assert created.status_code == 201
        lead_id = created.json()['lead_id']
        assert any(c['lead_id']==lead_id for c in client.get('/api/admin/intelligence/today').json()['cards'])
        assert client.post(f'/api/admin/intelligence/{lead_id}/snooze', json={'hours':24}).status_code == 403
        assert client.post(f'/api/admin/intelligence/{lead_id}/snooze', headers={'X-CSRF-Token':csrf}, json={'hours':24}).status_code == 200
        assert not any(c['lead_id']==lead_id for c in client.get('/api/admin/intelligence/today').json()['cards'])
        assert client.post('/api/admin/intelligence/reset-snoozes', headers={'X-CSRF-Token':csrf}).status_code == 200
        assert client.get('/api/admin/intelligence/performance?start=2026-10-01&end=2026-09-01').status_code == 422
        report=client.get('/api/admin/intelligence/performance?start=2026-09-01&end=2026-09-02').json()
        assert report['enquiries']==1


def test_booking_webhook_is_authenticated_and_idempotent(monkeypatch):
    monkeypatch.setattr(main, "check_booking_availability", lambda _: "Available")
    payload = {
        "booking_id": "booking-123", "primary_first_name": "Emma", "partner_first_name": "Josh",
        "email": "emma@example.com", "event_date": "2027-06-06", "venue": "Bordesley Park",
        "package_interest": "Platinum", "referral_source": "Venue referral"
    }
    with TestClient(main.app) as client:
        rejected = client.post("/api/integrations/booking/enquiry", json=payload)
        assert rejected.status_code == 401
        headers = {"X-Integration-Key": os.environ["BOOKING_WEBHOOK_KEY"]}
        created = client.post("/api/integrations/booking/enquiry", headers=headers, json=payload)
        assert created.status_code == 201
        repeated = client.post("/api/integrations/booking/enquiry", headers=headers, json=payload)
        assert repeated.status_code == 201
        assert repeated.json()["duplicate_ignored"] is True


def test_booking_snapshots_update_stage_and_are_idempotent(monkeypatch):
    monkeypatch.setattr(main, "check_booking_availability", lambda _: "Booked")
    headers = {"X-Integration-Key": os.environ["BOOKING_WEBHOOK_KEY"]}
    base = {
        "booking_id": "booking-snapshot-456", "primary_first_name": "Ava",
        "partner_first_name": "Noah", "email": "ava@example.com",
        "event_date": "2028-04-22", "venue": "Test Barn",
        "package_interest": "Gold", "referral_source": "Website",
    }
    with TestClient(main.app) as client:
        login(client)
        created = client.post("/api/integrations/booking/enquiry", headers=headers,
                              json={**base, "event_id": "booking-snapshot-456-v1"})
        assert created.status_code == 201
        lead_id = created.json()["lead_id"]
        assert created.json()["stage"] == "new"

        booked = client.post("/api/integrations/booking/enquiry", headers=headers, json={
            **base, "event_id": "booking-snapshot-456-v2", "booking_status": "confirmed",
            "deposit_paid": True, "deposit_amount": 100, "estimated_value": 1049,
            "quote_status": "accepted",
            "quote_items": [
                {"type": "package", "code": "gold", "name": "Gold", "total": 899},
                {"type": "addon", "code": "extra-hour", "name": "Extra hour", "total": 150},
            ],
        })
        assert booked.status_code == 201
        assert booked.json()["lead_id"] == lead_id
        assert booked.json()["stage"] == "booked"
        detail = client.get(f"/api/admin/leads/{lead_id}").json()
        assert detail["deposit_amount"] == 100
        assert detail["quote_status"] == "accepted"
        assert detail["quote_items"][1]["name"] == "Extra hour"
        assert detail["booking_record_url"].endswith("/bookings/booking-snapshot-456/overview")

        repeated = client.post("/api/integrations/booking/enquiry", headers=headers, json={
            **base, "event_id": "booking-snapshot-456-v2", "booking_status": "confirmed",
            "deposit_paid": True, "deposit_amount": 100, "estimated_value": 1049,
            "quote_status": "accepted",
            "quote_items": [
                {"type": "package", "code": "gold", "name": "Gold", "total": 899},
                {"type": "addon", "code": "extra-hour", "name": "Extra hour", "total": 150},
            ],
        })
        assert repeated.json()["already_processed"] is True

        cancelled = client.post("/api/integrations/booking/enquiry", headers=headers, json={
            **base, "event_id": "booking-snapshot-456-v3", "booking_status": "cancelled",
            "estimated_value": 899,
        })
        assert cancelled.json()["stage"] == "lost"
