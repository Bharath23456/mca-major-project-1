from dataclasses import replace
from urllib.parse import parse_qs

import anyio
import httpx
import pytest

from app import captcha
from app.settings import settings

PROVIDER_TEST_VALUE = "private-test-secret"


def _use_recaptcha_transport(monkeypatch, handler) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def record_request(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    transport = httpx.MockTransport(record_request)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        captcha.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    monkeypatch.setattr(
        captcha,
        "settings",
        replace(
            settings,
            captcha_mode="recaptcha",
            recaptcha_site_key="public-test-site-key",
            recaptcha_secret_key=PROVIDER_TEST_VALUE,
        ),
    )
    return requests


def test_local_test_mode_accepts_only_the_explicit_test_token(monkeypatch) -> None:
    monkeypatch.setattr(captcha, "settings", replace(settings, captcha_mode="test"))

    assert anyio.run(captcha.verify_captcha, captcha.LOCAL_TEST_CAPTCHA_MARKER)
    assert not anyio.run(captcha.verify_captcha, "not-the-test-token")


def test_recaptcha_public_config_contains_no_secret(monkeypatch) -> None:
    monkeypatch.setattr(
        captcha,
        "settings",
        replace(
            settings,
            captcha_mode="recaptcha",
            recaptcha_site_key="public-test-site-key",
            recaptcha_secret_key=PROVIDER_TEST_VALUE,
        ),
    )

    assert captcha.public_captcha_config() == {
        "mode": "recaptcha",
        "site_key": "public-test-site-key",
    }


def test_recaptcha_mode_requires_both_keys(monkeypatch) -> None:
    monkeypatch.setattr(
        captcha,
        "settings",
        replace(
            settings,
            captcha_mode="recaptcha",
            recaptcha_site_key="",
            recaptcha_secret_key="",
        ),
    )

    with pytest.raises(captcha.CaptchaUnavailable, match="not configured"):
        captcha.public_captcha_config()


def test_recaptcha_verification_sends_secret_and_accepts_google_success(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        fields = parse_qs(request.content.decode("utf-8"))
        assert fields["secret"] == [PROVIDER_TEST_VALUE]
        assert fields["response"] == ["captcha-response"]
        return httpx.Response(200, json={"success": True})

    requests = _use_recaptcha_transport(monkeypatch, handler)

    assert anyio.run(captcha.verify_captcha, "captcha-response")
    assert len(requests) == 1
    assert str(requests[0].url) == captcha.RECAPTCHA_VERIFY_URL


def test_recaptcha_rejects_unsuccessful_verification(monkeypatch) -> None:
    requests = _use_recaptcha_transport(
        monkeypatch,
        lambda _: httpx.Response(200, json={"success": False}),
    )

    assert not anyio.run(captcha.verify_captcha, "invalid-response")
    assert len(requests) == 1


def test_recaptcha_service_failure_is_reported(monkeypatch) -> None:
    def unavailable(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline")

    _use_recaptcha_transport(monkeypatch, unavailable)

    with pytest.raises(captcha.CaptchaUnavailable) as error:
        anyio.run(captcha.verify_captcha, "captcha-response")
    assert str(error.value) == "CAPTCHA verification service is unavailable."
