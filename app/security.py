import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Admin


settings = get_settings()
serializer = URLSafeTimedSerializer(settings.session_secret, salt="growth-engine-session-v1")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    result = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt$16384$8$1${base64.b64encode(salt).decode()}${base64.b64encode(result).decode()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, n, r, p, salt, expected = encoded.split("$")
        actual = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def make_session(admin: Admin) -> tuple[str, str]:
    csrf = secrets.token_urlsafe(24)
    token = serializer.dumps({"admin_id": admin.id, "email": admin.email, "csrf": csrf})
    return token, csrf


def current_admin(request: Request, db: Session = Depends(get_db)) -> Admin:
    token = request.cookies.get("growth_session")
    if not token:
        raise HTTPException(401, "Please sign in")
    try:
        data = serializer.loads(token, max_age=settings.session_hours * 3600)
    except (BadSignature, SignatureExpired):
        raise HTTPException(401, "Your session has expired")
    admin = db.get(Admin, data.get("admin_id"))
    if not admin:
        raise HTTPException(401, "Please sign in")
    request.state.session_data = data
    return admin


def csrf_admin(request: Request, x_csrf_token: str | None = Header(default=None), admin: Admin = Depends(current_admin)) -> Admin:
    expected = getattr(request.state, "session_data", {}).get("csrf")
    if not expected or not x_csrf_token or not hmac.compare_digest(expected, x_csrf_token):
        raise HTTPException(403, "Security token missing or invalid")
    return admin

