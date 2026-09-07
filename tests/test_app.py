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
        assert len(detail["automations"]) == 3


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
