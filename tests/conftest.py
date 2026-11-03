import os
import secrets
import tempfile
from pathlib import Path

_TEST_DATABASE = Path(tempfile.gettempdir()) / f"cloudnetops-tests-{os.getpid()}.db"
_TEST_WEBHOOK_TOKEN_FILE = (
    Path(tempfile.gettempdir()) / f"cloudnetops-webhook-token-{os.getpid()}.txt"
)
_TEST_WEBHOOK_TOKEN_FILE.write_text(secrets.token_urlsafe(32), encoding="utf-8")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATABASE.as_posix()}"
os.environ["ALERTMANAGER_WEBHOOK_TOKEN_FILE"] = str(_TEST_WEBHOOK_TOKEN_FILE)
os.environ["CAPTCHA_MODE"] = "test"
os.environ["SESSION_COOKIE_SECURE"] = "false"


def pytest_sessionfinish() -> None:
    from app.database import engine

    engine.dispose()
    _TEST_DATABASE.unlink(missing_ok=True)
    _TEST_WEBHOOK_TOKEN_FILE.unlink(missing_ok=True)
