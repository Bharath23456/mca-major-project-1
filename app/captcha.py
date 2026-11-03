import hmac
from typing import Any

import httpx

from app.logging_config import get_json_logger
from app.settings import settings

logger = get_json_logger("cloudnetops.captcha")
LOCAL_TEST_CAPTCHA_MARKER = "cloudnetops-local-captcha-test-token"
RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


class CaptchaUnavailable(RuntimeError):
    """Raised when CAPTCHA verification cannot be configured or reached."""


def public_captcha_config() -> dict[str, str]:
    if settings.captcha_mode == "test":
        return {"mode": "test", "site_key": ""}
    if settings.captcha_mode != "recaptcha":
        raise CaptchaUnavailable("CAPTCHA mode is invalid.")
    if not settings.recaptcha_site_key or not settings.recaptcha_secret_key:
        raise CaptchaUnavailable("reCAPTCHA is not configured.")
    return {"mode": "recaptcha", "site_key": settings.recaptcha_site_key}


async def verify_captcha(token: str, remote_ip: str | None = None) -> bool:
    if settings.captcha_mode == "test":
        return hmac.compare_digest(token, LOCAL_TEST_CAPTCHA_MARKER)
    if settings.captcha_mode != "recaptcha":
        raise CaptchaUnavailable("CAPTCHA mode is invalid.")
    if not settings.recaptcha_secret_key or not settings.recaptcha_site_key:
        raise CaptchaUnavailable("reCAPTCHA is not configured.")

    fields = {"secret": settings.recaptcha_secret_key, "response": token}
    if remote_ip and remote_ip != "unknown":
        fields["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(RECAPTCHA_VERIFY_URL, data=fields)
            response.raise_for_status()
            result: Any = response.json()
    except (httpx.HTTPError, ValueError) as error:
        logger.warning(
            "reCAPTCHA verification service unavailable",
            extra={
                "event": "captcha_verification_unavailable",
                "operation": "siteverify",
                "error_type": type(error).__name__,
            },
        )
        raise CaptchaUnavailable("CAPTCHA verification service is unavailable.") from error

    return isinstance(result, dict) and result.get("success") is True
