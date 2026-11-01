from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.auth import (
    CSRF_COOKIE_NAME,
    DUMMY_PASSWORD_HASH,
    PASSWORD_HASHER,
    SESSION_COOKIE_NAME,
    create_session,
    hash_password,
    hash_secret,
    normalize_identity,
    validate_email,
    validate_password,
    validate_username,
    verify_password,
)
from app.database import get_session
from app.models import LoginAttempt, User, UserSession
from app.settings import settings

router = APIRouter(prefix="/api/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class RegistrationRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    confirm_password: str = Field(min_length=12, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("password", "confirm_password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        return validate_password(value)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _limit_keys(identity: str, address: str) -> tuple[str, str]:
    return hash_secret(f"identity:{identity}"), hash_secret(f"ip:{address}")


def _failed_attempt_count(session: Session, key_hash: str, cutoff: datetime) -> int:
    return int(
        session.scalar(
            select(func.count(LoginAttempt.id)).where(
                LoginAttempt.key_hash == key_hash,
                LoginAttempt.attempted_at >= cutoff,
            )
        )
        or 0
    )


def _registration_limit_keys(email: str, address: str) -> tuple[str, str]:
    return hash_secret(f"registration-identity:{email}"), hash_secret(
        f"registration-ip:{address}"
    )


def _set_auth_cookies(response: Response, token: str, csrf_token: str) -> None:
    common = {
        "max_age": settings.session_ttl_seconds,
        "path": "/",
        "secure": settings.session_cookie_secure,
        "samesite": "strict",
    }
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        **common,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        csrf_token,
        httponly=False,
        **common,
    )


@router.post("/register", status_code=201)
def register(
    payload: RegistrationRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=422, detail="Passwords do not match.")

    identity_key, ip_key = _registration_limit_keys(payload.email, _client_ip(request))
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.login_window_seconds)
    if (
        _failed_attempt_count(session, identity_key, cutoff) >= settings.login_identity_limit
        or _failed_attempt_count(session, ip_key, cutoff) >= settings.login_ip_limit
    ):
        record_audit(
            session,
            user_id=None,
            action="registration_failed",
            resource_type="authentication",
            result="rate_limited",
            details={"reason": "rate_limited"},
        )
        session.commit()
        raise HTTPException(
            status_code=429,
            detail="Too many registration attempts. Try again later.",
        )

    session.execute(delete(LoginAttempt).where(LoginAttempt.attempted_at < now - timedelta(days=1)))
    session.add_all(
        [
            LoginAttempt(key_hash=identity_key, attempted_at=now),
            LoginAttempt(key_hash=ip_key, attempted_at=now),
        ]
    )
    duplicate = session.scalar(
        select(User.id).where(
            or_(User.username == payload.username, User.email == payload.email)
        )
    )
    if duplicate is not None:
        record_audit(
            session,
            user_id=None,
            action="registration_failed",
            resource_type="authentication",
            result="failure",
            details={"reason": "username_or_email_exists"},
        )
        session.commit()
        raise HTTPException(
            status_code=409,
            detail="That username or email is already registered.",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role="VIEWER",
        is_active=True,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="That username or email is already registered.",
        ) from None
    record_audit(
        session,
        user_id=user.id,
        action="user_registered",
        resource_type="user",
        resource_id=str(user.id),
        result="success",
        details={"role": "VIEWER"},
    )
    session.commit()
    return {
        "message": "Account created. Sign in with your username or email.",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
        },
    }


@router.post("/login")
def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    identity = normalize_identity(credentials.username)
    identity_key, ip_key = _limit_keys(identity, _client_ip(request))
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=settings.login_window_seconds)
    if (
        _failed_attempt_count(session, identity_key, cutoff) >= settings.login_identity_limit
        or _failed_attempt_count(session, ip_key, cutoff) >= settings.login_ip_limit
    ):
        record_audit(
            session,
            user_id=None,
            action="login_failed",
            resource_type="authentication",
            result="rate_limited",
            details={"reason": "rate_limited"},
        )
        session.commit()
        raise HTTPException(
            status_code=429,
            detail="Too many failed sign-in attempts. Try again later.",
        )

    user = session.scalar(
        select(User).where(or_(User.username == identity, User.email == identity))
    )
    stored_hash = user.password_hash if user is not None else DUMMY_PASSWORD_HASH
    password_valid = verify_password(stored_hash, credentials.password)
    if user is None or not user.is_active or not password_valid:
        session.execute(
            delete(LoginAttempt).where(LoginAttempt.attempted_at < now - timedelta(days=1))
        )
        session.add_all(
            [
                LoginAttempt(key_hash=identity_key, attempted_at=now),
                LoginAttempt(key_hash=ip_key, attempted_at=now),
            ]
        )
        record_audit(
            session,
            user_id=user.id if user is not None else None,
            action="login_failed",
            resource_type="authentication",
            result="failure",
            details={"reason": "invalid_credentials"},
        )
        session.commit()
        raise HTTPException(status_code=401, detail="Invalid username/email or password.")

    if PASSWORD_HASHER.check_needs_rehash(user.password_hash):
        user.password_hash = PASSWORD_HASHER.hash(credentials.password)
    session.execute(delete(LoginAttempt).where(LoginAttempt.key_hash == identity_key))
    auth_session, token, csrf_token = create_session(session, user)
    record_audit(
        session,
        user_id=user.id,
        action="login_succeeded",
        resource_type="authentication",
        result="success",
    )
    session.commit()
    session.refresh(auth_session)
    _set_auth_cookies(response, token, csrf_token)
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
        },
        "csrf_token": csrf_token,
        "expires_at": auth_session.expires_at.isoformat(),
    }


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    user: User = request.state.user
    auth_session: UserSession = request.state.auth_session
    session.delete(
        session.get(UserSession, auth_session.id)
        or auth_session
    )
    record_audit(
        session,
        user_id=user.id,
        action="logout",
        resource_type="authentication",
        result="success",
    )
    session.commit()
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="strict",
    )
    return {"status": "logged_out"}


@router.get("/me")
def current_user(request: Request) -> dict[str, object]:
    user: User = request.state.user
    csrf_token = request.cookies.get(CSRF_COOKIE_NAME)
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "csrf_token": csrf_token,
    }


def normalized_account(username: str, email: str) -> tuple[str, str]:
    try:
        return validate_username(username), validate_email(email)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
