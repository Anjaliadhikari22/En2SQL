"""
Authentication and role-based access helpers for En2SQL.

The login flow is OTP-first and local-first:
1. Send OTP to an email address.
2. Verify OTP.
3. Users are logged in immediately after OTP verification.
4. Admin verifies OTP, then creates/enters an admin password.
5. A JWT is issued after the role-specific login step.

For an academic/local demo, users are stored in a small JSON file and OTPs are
stored in memory. Production should use a durable database and Redis-style OTP
store.
"""

from __future__ import annotations

import json
import os
import random
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps
from typing import Any, Callable

from flask import g, jsonify, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config

try:
    import jwt
except Exception:  # pragma: no cover - development fallback before requirements install
    jwt = None


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ALLOWED_ROLES = {"admin", "user"}
ADMIN_EMAIL = Config.ADMIN_EMAIL.lower().strip()

# In-memory OTP state: key = "role:email"
OTP_STORE: dict[str, dict[str, Any]] = {}


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def normalize_role(role: str) -> str:
    return (role or "").strip().lower()


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(normalize_email(email)))


def _otp_key(email: str, role: str) -> str:
    return f"{normalize_role(role)}:{normalize_email(email)}"


def validate_role_email(email: str, role: str) -> tuple[bool, str]:
    """Validate email/role and enforce the single allowed admin email."""
    email = normalize_email(email)
    role = normalize_role(role)
    if not is_valid_email(email):
        return False, "Please enter a valid email address."
    if role not in ALLOWED_ROLES:
        return False, "Please select a valid role."
    if role == "admin" and email != ADMIN_EMAIL:
        return False, "You are not authorized to login as admin."
    return True, ""


def _load_users() -> list[dict[str, str]]:
    if not os.path.exists(Config.AUTH_USERS_FILE):
        return []
    try:
        with open(Config.AUTH_USERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_users(users: list[dict[str, str]]) -> None:
    os.makedirs(os.path.dirname(Config.AUTH_USERS_FILE), exist_ok=True)
    with open(Config.AUTH_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)


def find_user(email: str, role: str) -> dict[str, str] | None:
    email = normalize_email(email)
    role = normalize_role(role)
    for user in _load_users():
        if user.get("email") == email and user.get("role") == role:
            return user
    return None


def user_exists(email: str, role: str) -> bool:
    return find_user(email, role) is not None


def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send email with SMTP. Returns False if SMTP is not configured/failed."""
    required = [Config.SMTP_HOST, Config.SMTP_USER, Config.SMTP_PASSWORD, Config.SMTP_FROM]
    if not all(required):
        print("[En2SQL email] SMTP is not fully configured.")
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = Config.SMTP_FROM
    message["To"] = to_email
    message.set_content(body)

    try:
        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception as exc:
        print(f"[En2SQL email] Failed to send email: {exc}")
        return False


def send_unauthorized_admin_alert(attempted_email: str, attempted_role: str, ip: str, user_agent: str) -> None:
    """Alert the real admin when a different email attempts admin login."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    body = (
        "Unauthorized admin login attempt detected for En2SQL.\n\n"
        f"Attempted email: {attempted_email}\n"
        f"Attempted role: {attempted_role}\n"
        f"Date/time: {now}\n"
        f"IP address: {ip or 'Unavailable'}\n"
        f"User agent: {user_agent or 'Unavailable'}\n"
    )
    sent = send_email(
        ADMIN_EMAIL,
        "Unauthorized Admin Login Attempt - En2SQL",
        body,
    )
    if not sent:
        print("[En2SQL security alert]")
        print(body)


def create_otp(email: str, role: str) -> str:
    """Generate and store a 6-digit OTP with expiry."""
    otp = f"{random.randint(0, 999999):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=Config.OTP_EXPIRY_MINUTES)
    OTP_STORE[_otp_key(email, role)] = {
        "otp": otp,
        "expires_at": expires_at,
        "verified": False,
    }
    return otp


def send_otp_email(email: str, otp: str) -> bool:
    body = (
        f"Your En2SQL verification code is: {otp}\n\n"
        f"This OTP is valid for {Config.OTP_EXPIRY_MINUTES} minutes.\n"
        "If you did not request this, please ignore this email."
    )
    return send_email(email, "Your En2SQL Login OTP", body)


def verify_otp(email: str, role: str, otp: str) -> tuple[bool, str]:
    """Verify OTP and return (valid, message)."""
    entry = OTP_STORE.get(_otp_key(email, role))
    if not entry:
        return False, "OTP not found. Please request a new code."
    if datetime.now(timezone.utc) > entry["expires_at"]:
        OTP_STORE.pop(_otp_key(email, role), None)
        return False, "OTP expired. Please request a new code."
    if str(otp or "").strip() != entry["otp"]:
        return False, "Invalid OTP. Please try again."
    entry["verified"] = True
    return True, "OTP verified successfully."


def is_otp_verified(email: str, role: str) -> bool:
    entry = OTP_STORE.get(_otp_key(email, role))
    return bool(entry and entry.get("verified") and datetime.now(timezone.utc) <= entry["expires_at"])


def clear_otp(email: str, role: str) -> None:
    """Remove OTP state after a completed or failed-to-send login attempt."""
    OTP_STORE.pop(_otp_key(email, role), None)


def create_user_if_missing(email: str, role: str = "user") -> dict[str, str]:
    """Create a local passwordless user record if one does not already exist."""
    ok, message = validate_role_email(email, role)
    if not ok:
        raise ValueError(message)

    email = normalize_email(email)
    role = normalize_role(role)
    existing = find_user(email, role)
    if existing:
        return {
            "email": existing["email"],
            "name": existing.get("name") or existing["email"].split("@")[0],
            "role": existing["role"],
        }

    users = _load_users()
    user = {
        "email": email,
        "role": role,
        "name": email.split("@")[0],
        "password_hash": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    users.append(user)
    _save_users(users)
    return {
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
    }


def set_user_password(email: str, role: str, password: str) -> tuple[bool, str]:
    """Create/update a local user password after OTP verification."""
    ok, message = validate_role_email(email, role)
    if not ok:
        return False, message
    if not is_otp_verified(email, role):
        return False, "Please verify OTP before setting a password."
    if len(password or "") < 6:
        return False, "Password must be at least 6 characters."

    email = normalize_email(email)
    role = normalize_role(role)
    users = _load_users()
    existing = None
    for user in users:
        if user.get("email") == email and user.get("role") == role:
            existing = user
            break

    payload = {
        "email": email,
        "role": role,
        "name": "Admin" if role == "admin" else email.split("@")[0],
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        existing.update(payload)
    else:
        users.append(payload)
    _save_users(users)
    OTP_STORE.pop(_otp_key(email, role), None)
    return True, "Password saved successfully."


def admin_password_login(email: str, password: str) -> tuple[bool, str, dict[str, str] | None]:
    """
    Create or verify the admin password after successful admin OTP verification.

    The first successful admin OTP can create the password. Later logins verify
    the stored hash. Plain text passwords are never stored.
    """
    email = normalize_email(email)
    ok, message = validate_role_email(email, "admin")
    if not ok:
        return False, message, None
    if not is_otp_verified(email, "admin"):
        return False, "Please verify OTP before entering the admin password.", None
    if len(password or "") < 6:
        return False, "Password must be at least 6 characters.", None

    users = _load_users()
    existing = None
    for user in users:
        if user.get("email") == email and user.get("role") == "admin":
            existing = user
            break

    if existing and existing.get("password_hash"):
        if not check_password_hash(existing.get("password_hash", ""), password or ""):
            return False, "Admin password is incorrect.", None
        admin = {
            "email": existing["email"],
            "name": existing.get("name") or "Admin",
            "role": "admin",
        }
        clear_otp(email, "admin")
        return True, "Admin login successful.", admin

    payload = {
        "email": email,
        "role": "admin",
        "name": "Admin",
        "password_hash": generate_password_hash(password, method="pbkdf2:sha256"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if existing:
        existing.update(payload)
    else:
        users.append(payload)
    _save_users(users)
    clear_otp(email, "admin")
    return True, "Admin login successful.", {
        "email": payload["email"],
        "name": payload["name"],
        "role": payload["role"],
    }


def authenticate_user(email: str, password: str, role: str) -> dict[str, str] | None:
    """Validate local user credentials and enforce admin email rule."""
    ok, _message = validate_role_email(email, role)
    if not ok:
        return None
    user = find_user(email, role)
    if not user or not check_password_hash(user.get("password_hash", ""), password or ""):
        return None
    return {
        "email": user["email"],
        "name": user.get("name") or ("Admin" if user["role"] == "admin" else user["email"].split("@")[0]),
        "role": user["role"],
    }


def create_token(user: dict[str, str]) -> str:
    """Create a signed JWT for the authenticated local user."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user["email"],
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user["role"],
        "iat": now,
        "exp": now + timedelta(hours=Config.JWT_EXPIRY_HOURS),
    }
    if jwt is None:
        serializer = URLSafeTimedSerializer(Config.JWT_SECRET_KEY)
        return serializer.dumps({
            "sub": user["email"],
            "email": user["email"],
            "name": user.get("name", ""),
            "role": user["role"],
        })
    return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT. Returns None if invalid/expired."""
    if jwt is None:
        serializer = URLSafeTimedSerializer(Config.JWT_SECRET_KEY)
        try:
            return serializer.loads(token, max_age=Config.JWT_EXPIRY_HOURS * 3600)
        except (BadSignature, SignatureExpired):
            return None
    try:
        return jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def _access_denied(status: int = 403):
    return jsonify({
        "error": "Access denied",
        "message": "You are not authorized to access this feature.",
    }), status


def get_request_user() -> dict[str, Any] | None:
    """Return the authenticated user payload attached by require_auth."""
    return getattr(g, "current_user", None)


def require_auth(fn: Callable):
    """Require a valid Bearer token."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = auth_header.replace("Bearer ", "", 1).strip() if auth_header.startswith("Bearer ") else ""
        payload = decode_token(token)
        if not payload:
            return _access_denied(401)
        g.current_user = {
            "email": payload.get("email") or payload.get("sub"),
            "name": payload.get("name", ""),
            "role": payload.get("role", ""),
        }
        return fn(*args, **kwargs)
    return wrapper


def require_role(*roles: str):
    """Require authentication and one of the allowed roles."""
    allowed = {role.lower() for role in roles}

    def decorator(fn: Callable):
        @wraps(fn)
        @require_auth
        def wrapper(*args, **kwargs):
            user = get_request_user() or {}
            if user.get("role") not in allowed:
                return _access_denied(403)
            return fn(*args, **kwargs)
        return wrapper

    return decorator
