from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Admin, Setting
from .schemas import AccountEmailIn, PasswordChangeIn
from .security import csrf_admin, current_admin, hash_password, make_session, verify_password


router = APIRouter(prefix="/api/admin/account")
settings = get_settings()


def setting_value(db: Session, key: str) -> dict:
    item = db.get(Setting, key)
    return item.value if item and isinstance(item.value, dict) else {}


def renew_session(response: Response, admin: Admin) -> str:
    token, csrf = make_session(admin)
    response.set_cookie(
        "growth_session", token, httponly=True, secure=settings.cookie_secure,
        samesite="lax", max_age=settings.session_hours * 3600,
    )
    return csrf


@router.get("")
def account(admin: Admin = Depends(current_admin), db: Session = Depends(get_db)):
    website = setting_value(db, "website-config")
    google = setting_value(db, "website-google")
    return {
        "email": admin.email,
        "created_at": admin.created_at.isoformat(),
        "session_hours": settings.session_hours,
        "build": settings.build_version,
        "connections": {
            "booking": bool(settings.booking_base_url and settings.booking_webhook_key),
            "website": bool(website.get("enabled") and website.get("token")),
            "google": bool(google.get("email") and google.get("property")),
        },
        "safety": {
            "automatic_email": False,
            "followup_approval": settings.followup_approval_required,
            "client_communications_owner": "Booking System",
        },
    }


@router.put("/email")
def change_email(payload: AccountEmailIn, response: Response,
                 admin: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(400, "Your current password is incorrect")
    new_email = str(payload.new_email).strip().lower()
    if new_email == admin.email:
        raise HTTPException(409, "That is already your login email")
    if db.scalar(select(Admin.id).where(Admin.email == new_email, Admin.id != admin.id)):
        raise HTTPException(409, "That email address is already in use")
    admin.email = new_email
    admin.session_version += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "That email address is already in use")
    csrf = renew_session(response, admin)
    return {"ok": True, "email": admin.email, "csrf_token": csrf,
            "message": "Login email changed. Other signed-in sessions have been closed."}


@router.put("/password")
def change_password(payload: PasswordChangeIn, response: Response,
                    admin: Admin = Depends(csrf_admin), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, admin.password_hash):
        raise HTTPException(400, "Your current password is incorrect")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(422, "The two new passwords do not match")
    if not payload.new_password.strip():
        raise HTTPException(422, "Choose a usable password")
    if verify_password(payload.new_password, admin.password_hash):
        raise HTTPException(409, "Choose a different password from your current one")
    admin.password_hash = hash_password(payload.new_password)
    admin.session_version += 1
    db.commit()
    csrf = renew_session(response, admin)
    return {"ok": True, "csrf_token": csrf,
            "message": "Password changed. Other signed-in sessions have been closed."}
