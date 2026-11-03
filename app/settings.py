import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    prometheus_url: str = os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./cloudnetops.db")
    model_path: str = os.getenv("MODEL_PATH", "data/isolation_forest.joblib")
    blackbox_targets_path: str = os.getenv(
        "BLACKBOX_TARGETS_PATH", "monitoring/prometheus/blackbox_targets.json"
    )
    cpu_threshold_percent: float = float(os.getenv("CPU_THRESHOLD_PERCENT", "85"))
    memory_threshold_percent: float = float(os.getenv("MEMORY_THRESHOLD_PERCENT", "90"))
    disk_threshold_percent: float = float(os.getenv("DISK_THRESHOLD_PERCENT", "90"))
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "28800"))
    session_cookie_secure: bool = os.getenv("SESSION_COOKIE_SECURE", "true").lower() == "true"
    login_identity_limit: int = int(os.getenv("LOGIN_IDENTITY_LIMIT", "5"))
    login_ip_limit: int = int(os.getenv("LOGIN_IP_LIMIT", "20"))
    login_window_seconds: int = int(os.getenv("LOGIN_WINDOW_SECONDS", "900"))
    captcha_mode: str = os.getenv("CAPTCHA_MODE", "recaptcha").strip().lower()
    recaptcha_site_key: str = os.getenv("RECAPTCHA_SITE_KEY", "")
    recaptcha_secret_key: str = os.getenv("RECAPTCHA_SECRET_KEY", "")
    alertmanager_webhook_token_file: str = os.getenv("ALERTMANAGER_WEBHOOK_TOKEN_FILE", "")
    alert_correlation_window_seconds: int = int(
        os.getenv("ALERT_CORRELATION_WINDOW_SECONDS", "600")
    )
    incident_repeat_warning_count: int = int(
        os.getenv("INCIDENT_REPEAT_WARNING_COUNT", "3")
    )
    incident_repeat_critical_count: int = int(
        os.getenv("INCIDENT_REPEAT_CRITICAL_COUNT", "5")
    )
    incident_repeat_window_hours: int = int(
        os.getenv("INCIDENT_REPEAT_WINDOW_HOURS", "24")
    )
    capacity_forecast_warnings_enabled: bool = (
        os.getenv("CAPACITY_FORECAST_WARNINGS_ENABLED", "false").strip().lower() == "true"
    )


settings = Settings()
