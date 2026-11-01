import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from re import fullmatch

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserSession
from app.settings import settings

PASSWORD_HASHER = PasswordHasher()
DUMMY_PASSWORD_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
SESSION_COOKIE_NAME = "cloudnetops_session"
CSRF_COOKIE_NAME = "cloudnetops_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_identity(value: str) -> str:
    return value.strip().casefold()


def validate_username(value: str) -> str:
    normalized = normalize_identity(value)
    if not fullmatch(r"[a-z0-9][a-z0-9_.-]{2,63}", normalized):
        raise ValueError(
            "Username must be 3–64 characters using letters, numbers, '.', '_' or '-'."
        )
    return normalized


def validate_email(value: str) -> str:
    normalized = normalize_identity(value)
    if (
        len(normalized) > 254
        or "@" not in normalized
        or normalized.startswith("@")
        or normalized.endswith("@")
        or any(character.isspace() for character in normalized)
    ):
        raise ValueError("Enter a valid email address.")
    local, domain = normalized.rsplit("@", maxsplit=1)
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("Enter a valid email address.")
    return normalized


def validate_password(value: str) -> str:
    if len(value) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if len(value) > 128:
        raise ValueError("Password cannot exceed 128 characters.")
    return value


def hash_password(password: str) -> str:
    return PASSWORD_HASHER.hash(validate_password(password))


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return PASSWORD_HASHER.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def create_session(session: Session, user: User) -> tuple[UserSession, str, str]:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    auth_session = UserSession(
        user_id=user.id,
        token_hash=hash_secret(token),
        csrf_token_hash=hash_secret(csrf_token),
        expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
        created_at=now,
        last_seen_at=now,
    )
    session.add(auth_session)
    return auth_session, token, csrf_token


def user_session_for_token(session: Session, token: str) -> UserSession | None:
    return session.scalar(select(UserSession).where(UserSession.token_hash == hash_secret(token)))


def session_is_expired(auth_session: UserSession, now: datetime | None = None) -> bool:
    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at <= (now or datetime.now(UTC))


def csrf_token_is_valid(auth_session: UserSession, csrf_token: str | None) -> bool:
    return bool(
        csrf_token
        and secrets.compare_digest(auth_session.csrf_token_hash, hash_secret(csrf_token))
    )


def get_current_user(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def require_roles(*roles: str):
    def role_dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail="You do not have permission for this action.",
            )
        return user

    return role_dependency
