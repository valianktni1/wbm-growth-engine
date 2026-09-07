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


def test_complete_enquiry_and_proposal_journey(monkeypatch):
    monkeypatch.setattr(main, "check_booking_availability", lambda _: "Available")
    with TestClient(main.app) as client:
        csrf = login(client)
        response = client.post("/api/admin/leads", headers={"X-CSRF-Token": csrf}, json={**enquiry_payload(), "forward_to_booking": False})
        assert response.status_code == 201, response.text
        lead = response.json()
        assert lead["availability"] == "Available"
        assert lead["proposal"]["published"] is False

        published = client.post(f"/api/admin/leads/{lead['id']}/proposal/publish", headers={"X-CSRF-Token": csrf})
        assert published.status_code == 200
        proposal = published.json()
        assert proposal["published"] is True

        page = client.get(proposal["url"].replace("http://localhost:30110", ""))
        assert page.status_code == 200
        assert "Sophie &amp; Liam" in page.text
        assert "Heaton House Farm" in page.text

        activity = client.post(f"/api/public/proposals/{lead['proposal']['url'].split('/')[-1]}/activity",
                               json={"kind": "package_viewed", "label": "Gold selected", "details": {"package": "Gold"}})
        assert activity.status_code == 204
        detail = client.get(f"/api/admin/leads/{lead['id']}").json()
        assert detail["stage"] == "engaged"
        assert len(detail["automations"]) == 0  # Publishing is not sending.
        assert lead['proposal']['testimonials'] == []
        assert 'Open secure booking area' not in page.text
        blocked = client.post(f"/api/admin/leads/{lead['id']}/proposal/send", headers={"X-CSRF-Token": csrf})
        assert blocked.status_code == 409
        monkeypatch.setattr(main.settings, 'automation_send_enabled', True)
        monkeypatch.setattr(main, 'send_email', lambda *args: None)
        sent = client.post(f"/api/admin/leads/{lead['id']}/proposal/send", headers={"X-CSRF-Token": csrf})
        assert sent.status_code == 200
        detail = client.get(f"/api/admin/leads/{lead['id']}").json()
        assert len(detail['automations']) == 3
        first, second = detail["automations"][:2]
        changed = client.patch(
            f"/api/admin/automations/{first['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"subject": "A personally checked follow-up"},
        )
        assert changed.status_code == 200
        assert changed.json()["subject"] == "A personally checked follow-up"
        approved = client.post(
            f"/api/admin/automations/{first['id']}/approve",
            headers={"X-CSRF-Token": csrf},
        )
        assert approved.status_code == 200
        assert approved.json()["approved_at"]
        revised = client.patch(
            f"/api/admin/automations/{first['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"body": "A revised message that must be approved again."},
        )
        assert revised.status_code == 200
        assert revised.json()["approved_at"] is None
        cancelled = client.post(
            f"/api/admin/automations/{second['id']}/cancel",
            headers={"X-CSRF-Token": csrf},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        repeat = client.post(f"/api/admin/leads/{lead['id']}/proposal/send", headers={"X-CSRF-Token": csrf})
        assert repeat.status_code == 409


def test_package_catalogue_can_update_unpublished_drafts(monkeypatch):
    monkeypatch.setattr(main, "check_booking_availability", lambda _: "Available")
    with TestClient(main.app) as client:
        csrf = login(client)
        payload = enquiry_payload()
        payload["email"] = "catalogue@example.com"
        payload["primary_first_name"] = "Catalog"
        created = client.post(
            "/api/admin/leads",
            headers={"X-CSRF-Token": csrf},
            json={**payload, "forward_to_booking": False},
        )
        assert created.status_code == 201
        lead_id = created.json()["id"]

        current = client.get("/api/admin/settings/package-catalogue")
        assert current.status_code == 200
        assert any(item["code"] == "ultimate" and item["price"] == 1799 for item in current.json()["packages"])
        assert any(item["code"] == "platinum" and item["price"] == 1350 for item in current.json()["packages"])

        packages = [
            {"code": "bespoke", "name": "Bespoke Collection", "price": 999,
             "description": "A test package for an unpublished proposal."}
        ]
        saved = client.put(
            "/api/admin/settings/package-catalogue",
            headers={"X-CSRF-Token": csrf},
            json={"packages": packages, "apply_to_drafts": True},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["drafts_updated"] >= 1
        detail = client.get(f"/api/admin/leads/{lead_id}").json()
        assert detail["proposal"]["packages"] == packages


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
        created = client.post("/api/integrations/booking/enquiry", headers=headers,
                              json={**base, "event_id": "booking-snapshot-456-v1"})
        assert created.status_code == 201
        lead_id = created.json()["lead_id"]
        assert created.json()["stage"] == "new"

        booked = client.post("/api/integrations/booking/enquiry", headers=headers, json={
            **base, "event_id": "booking-snapshot-456-v2", "booking_status": "confirmed",
            "deposit_paid": True, "estimated_value": 899,
        })
        assert booked.status_code == 201
        assert booked.json()["lead_id"] == lead_id
        assert booked.json()["stage"] == "booked"

        repeated = client.post("/api/integrations/booking/enquiry", headers=headers, json={
            **base, "event_id": "booking-snapshot-456-v2", "booking_status": "confirmed",
            "deposit_paid": True, "estimated_value": 899,
        })
        assert repeated.json()["already_processed"] is True

        cancelled = client.post("/api/integrations/booking/enquiry", headers=headers, json={
            **base, "event_id": "booking-snapshot-456-v3", "booking_status": "cancelled",
            "estimated_value": 899,
        })
        assert cancelled.json()["stage"] == "lost"
