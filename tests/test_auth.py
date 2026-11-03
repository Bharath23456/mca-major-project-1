from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app import auth_routes
from app.auth import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    hash_password,
    hash_secret,
)
from app.captcha import LOCAL_TEST_CAPTCHA_MARKER
from app.database import SessionLocal
from app.main import app
from app.models import AuditLog, User, UserSession
from app.settings import settings

TEST_CREDENTIAL = "test-credential-phrase-2026"


@pytest.fixture
def auth_context() -> Iterator[tuple[TestClient, User, str]]:
    with TestClient(app, follow_redirects=False) as client:
        suffix = uuid4().hex[:12]
        with SessionLocal() as session:
            user = User(
                username=f"auth-{suffix}",
                email=f"auth-{suffix}@example.test",
                password_hash=hash_password(TEST_CREDENTIAL),
                role="ADMIN",
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id

        yield client, user, suffix

        with SessionLocal() as session:
            session.execute(delete(UserSession).where(UserSession.user_id == user_id))
            session.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


def login(
    client: TestClient,
    username: str,
    password: str = TEST_CREDENTIAL,
    captcha_token: str = LOCAL_TEST_CAPTCHA_MARKER,
):
    return client.post(
        "/api/auth/login",
        json={
            "username": username,
            "password": password,
            "captcha_token": captcha_token,
        },
    )


def test_public_registration_creates_viewer_who_can_sign_in() -> None:
    suffix = uuid4().hex[:12]
    username = f"signup-{suffix}"
    email = f"signup-{suffix}@example.test"
    signup_secret = TEST_CREDENTIAL
    payload = {
        "username": username,
        "email": email,
        "password": signup_secret,
        "confirm_password": signup_secret,
    }

    with TestClient(app) as client:
        response = client.post("/api/auth/register", json=payload)

        assert response.status_code == 201
        assert response.json()["user"]["role"] == "VIEWER"
        assert signup_secret not in response.text

        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.username == username))
            assert user is not None
            user_id = user.id
            assert user.role == "VIEWER"
            assert user.password_hash.startswith("$argon2id$")
            assert user.password_hash != signup_secret

        duplicate = client.post("/api/auth/register", json=payload)
        assert duplicate.status_code == 409

        signed_in = login(client, email, signup_secret)
        assert signed_in.status_code == 200
        assert signed_in.json()["user"]["role"] == "VIEWER"

        with SessionLocal() as session:
            session.execute(delete(UserSession).where(UserSession.user_id == user_id))
            session.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


def test_registration_rejects_mismatched_passwords() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/register",
            json={
                "username": f"signup-{uuid4().hex[:12]}",
                "email": f"signup-{uuid4().hex[:12]}@example.test",
                "password": TEST_CREDENTIAL,
                "confirm_password": f"not-{TEST_CREDENTIAL}",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Passwords do not match."


def test_successful_login_uses_argon2_and_http_only_session_cookie(auth_context) -> None:
    client, user, _ = auth_context

    response = login(client, user.email)

    assert response.status_code == 200
    assert response.json()["user"]["role"] == "ADMIN"
    assert SESSION_COOKIE_NAME in response.cookies
    assert CSRF_COOKIE_NAME in response.cookies
    assert "httponly" in response.headers["set-cookie"].lower()
    with SessionLocal() as session:
        saved = session.get(User, user.id)
        auth_session = session.scalar(
            select(UserSession).where(UserSession.user_id == user.id)
        )
        assert saved is not None
        assert saved.password_hash.startswith("$argon2id$")
        assert saved.password_hash != TEST_CREDENTIAL
        assert auth_session is not None
        assert auth_session.token_hash == hash_secret(response.cookies[SESSION_COOKIE_NAME])


def test_login_sets_secure_cookie_when_configured(auth_context, monkeypatch) -> None:
    client, user, _ = auth_context
    monkeypatch.setattr(
        auth_routes,
        "settings",
        replace(settings, session_cookie_secure=True),
    )

    response = login(client, user.username)

    assert response.status_code == 200
    cookies = response.headers.get_list("set-cookie")
    assert any(
        cookie.startswith(f"{SESSION_COOKIE_NAME}=") and "secure" in cookie.lower()
        for cookie in cookies
    )


def test_wrong_and_unknown_credentials_return_same_message(auth_context) -> None:
    client, user, suffix = auth_context

    wrong = login(client, user.username, "wrong-password")
    unknown = login(client, f"missing-{suffix}")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert "wrong-password" not in wrong.text


def test_login_rejects_invalid_captcha_without_creating_a_session(auth_context) -> None:
    client, user, _ = auth_context
    invalid_captcha = "invalid-token"

    response = login(client, user.username, captcha_token=invalid_captcha)

    assert response.status_code == 400
    assert response.json()["detail"] == "CAPTCHA verification failed."
    assert SESSION_COOKIE_NAME not in response.cookies
    with SessionLocal() as session:
        assert session.scalar(
            select(UserSession).where(UserSession.user_id == user.id)
        ) is None


def test_captcha_config_exposes_only_public_site_key() -> None:
    with TestClient(app) as client:
        response = client.get("/api/auth/captcha-config")

    assert response.status_code == 200
    assert response.json() == {"mode": "test", "site_key": ""}


def test_disabled_user_cannot_login(auth_context) -> None:
    client, user, _ = auth_context
    with SessionLocal() as session:
        saved = session.get(User, user.id)
        assert saved is not None
        saved.is_active = False
        session.commit()

    response = login(client, user.username)

    assert response.status_code == 401
    assert "cloudnetops_session" not in response.cookies


def test_unauthenticated_api_and_dashboard_are_protected() -> None:
    with TestClient(app, follow_redirects=False) as client:
        api_response = client.get("/api/auth/me")
        page_response = client.get("/")

    assert api_response.status_code == 401
    assert page_response.status_code == 303
    assert page_response.headers["location"] == "/login"


def test_logout_revokes_session_and_clears_cookies(auth_context) -> None:
    client, user, _ = auth_context
    signed_in = login(client, user.username)
    client.headers["X-CSRF-Token"] = signed_in.json()["csrf_token"]

    response = client.post("/api/auth/logout")

    assert response.status_code == 200
    assert response.json() == {"status": "logged_out"}
    assert client.get("/api/auth/me").status_code == 401
    assert SESSION_COOKIE_NAME not in client.cookies


def test_expired_session_is_rejected(auth_context) -> None:
    client, user, _ = auth_context
    signed_in = login(client, user.username)
    token_hash = hash_secret(signed_in.cookies[SESSION_COOKIE_NAME])
    with SessionLocal() as session:
        auth_session = session.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash)
        )
        assert auth_session is not None
        auth_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()

    assert client.get("/api/auth/me").status_code == 401


def test_csrf_token_is_required_for_authenticated_mutations(auth_context) -> None:
    client, user, _ = auth_context
    assert login(client, user.username).status_code == 200

    response = client.post(
        "/api/v1/anomalies/score",
        json={
            "cpu_percent": 20,
            "memory_percent": 40,
            "disk_percent": 50,
            "network_receive_bytes_per_second": 100,
            "network_transmit_bytes_per_second": 100,
        },
    )

    assert response.status_code == 403
    assert "CSRF" in response.json()["detail"]


def test_login_attempts_are_rate_limited(auth_context) -> None:
    client, user, _ = auth_context

    responses = [login(client, user.username, "incorrect") for _ in range(6)]

    assert [response.status_code for response in responses] == [
        401,
        401,
        401,
        401,
        401,
        429,
    ]
