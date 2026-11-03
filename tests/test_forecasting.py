import math
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app import main
from app.anomaly_detection.capacity import forecast_capacity
from app.auth import hash_password
from app.database import SessionLocal
from app.models import AnomalyEvent, AuditLog, User, UserSession

TEST_CREDENTIAL = "forecast-test-credential-2026"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(main.app) as test_client:
        suffix = uuid4().hex[:12]
        username = f"forecast-admin-{suffix}"
        with SessionLocal() as session:
            user = User(
                username=username,
                email=f"{username}@example.test",
                password_hash=hash_password(TEST_CREDENTIAL),
                role="ADMIN",
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id

        login = test_client.post(
            "/api/auth/login",
            json={
                "username": username,
                "password": TEST_CREDENTIAL,
                "captcha_token": "cloudnetops-local-captcha-test-token",
            },
        )
        assert login.status_code == 200
        test_client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        yield test_client

        with SessionLocal() as session:
            session.execute(delete(UserSession).where(UserSession.user_id == user_id))
            session.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


def hourly_series(values: list[float]) -> tuple[list[float], float]:
    latest = datetime.now(UTC).timestamp()
    timestamps = [latest - (len(values) - index - 1) * 3600 for index in range(len(values))]
    return timestamps, latest


def test_linear_forecast_and_holdout_backtest_use_synthetic_trend() -> None:
    timestamps, latest = hourly_series([80, 81, 82, 83, 84, 85, 86, 87, 88, 89])

    result = forecast_capacity(
        timestamps,
        [80, 81, 82, 83, 84, 85, 86, 87, 88, 89],
        horizon_hours=6,
        min_samples=8,
        now_timestamp=latest,
        warning_threshold_percent=95,
    )

    assert result["status"] == "forecast_available"
    assert result["trend_percent_per_hour"] == pytest.approx(1.0)
    assert result["predicted_value_percent"] == pytest.approx(95.0)
    assert result["time_to_exhaustion_hours"] is None
    assert result["backtest"]["actual_samples"] == 2
    assert result["backtest"]["mean_absolute_error_percent"] == pytest.approx(0.0)


def test_exhaustion_estimate_is_reported_only_when_within_horizon() -> None:
    values = [90, 91, 92, 93, 94, 95, 96, 97]
    timestamps, latest = hourly_series(values)

    result = forecast_capacity(
        timestamps,
        values,
        horizon_hours=6,
        now_timestamp=latest,
    )

    assert result["time_to_exhaustion_hours"] == pytest.approx(3.0)
    assert result["predicted_value_percent"] == pytest.approx(103.0)


def test_insufficient_or_stale_observations_do_not_create_forecasts() -> None:
    timestamps, latest = hourly_series([45, 46, 47, 48, 49, 50, 51])
    insufficient = forecast_capacity(
        timestamps, [45, 46, 47, 48, 49, 50, 51], now_timestamp=latest
    )
    stale = forecast_capacity(
        timestamps,
        [45, 46, 47, 48, 49, 50, 51],
        min_samples=7,
        now_timestamp=latest + 601,
    )

    assert insufficient["status"] == "insufficient_data"
    assert insufficient["predicted_value_percent"] is None
    assert stale["status"] == "stale_data"
    assert stale["predicted_value_percent"] is None


def test_invalid_and_missing_samples_are_excluded() -> None:
    timestamps, latest = hourly_series([40, 41, 42, 43, 44, 45, 46, 47])
    values: list[float | None] = [40, None, 42, math.nan, 44, 45, 46, 47]

    result = forecast_capacity(
        timestamps,
        values,
        min_samples=6,
        now_timestamp=latest,
    )

    assert result["status"] == "forecast_available"
    assert result["sample_count"] == 6
    assert result["trend_percent_per_hour"] == pytest.approx(1.0)


def test_forecast_api_groups_prometheus_series_by_target(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_query(
        expression: str, *, start: float, end: float, step_seconds: int
    ) -> list[dict]:
        assert start < end
        assert step_seconds == main.CAPACITY_FORECAST_STEP_SECONDS
        base = 40 if "node_memory" in expression else 50
        values = [
            [end - (19 - index) * step_seconds, str(base + index * 0.1)]
            for index in range(20)
        ]
        return [{"metric": {"instance": "node-a", "job": "node-exporter"}, "values": values}]

    monkeypatch.setattr(main, "prometheus_range_query", fake_query)

    response = client.get("/api/aiops/forecasts/capacity")

    assert response.status_code == 200
    result = response.json()
    assert result["lookback_hours"] == 24
    assert result["horizon_hours"] == 6
    assert result["model"] == "simple_linear_trend"
    assert len(result["series"]) == 3
    assert {item["target"] for item in result["series"]} == {"node-a"}
    assert all(item["forecast"]["status"] == "forecast_available" for item in result["series"])
    assert all(item["forecast"]["backtest"]["actual_samples"] == 4 for item in result["series"])


def test_forecast_api_reports_prometheus_unavailable(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(
        expression: str, *, start: float, end: float, step_seconds: int
    ) -> list[dict]:
        assert expression
        assert start < end
        assert step_seconds > 0
        raise main.PrometheusUnavailable("Prometheus is unavailable.")

    monkeypatch.setattr(main, "prometheus_range_query", unavailable)

    response = client.get("/api/aiops/forecasts/capacity")

    assert response.status_code == 503
    assert response.json()["detail"] == "Prometheus is unavailable."


def test_capacity_warning_events_are_optional_and_deduplicated(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_query(
        expression: str, *, start: float, end: float, step_seconds: int
    ) -> list[dict]:
        assert start < end
        values = [
            [
                end - (19 - index) * step_seconds,
                str((60 + index) if "node_cpu_seconds_total" in expression else 40),
            ]
            for index in range(20)
        ]
        return [{"metric": {"instance": "node-a"}, "values": values}]

    monkeypatch.setattr(main, "prometheus_range_query", fake_query)
    response = client.post("/api/aiops/forecasts/capacity/warnings")
    assert response.status_code == 409

    monkeypatch.setattr(
        main,
        "settings",
        replace(main.settings, capacity_forecast_warnings_enabled=True),
    )
    first = client.post("/api/aiops/forecasts/capacity/warnings")
    second = client.post("/api/aiops/forecasts/capacity/warnings")

    assert first.status_code == second.status_code == 200
    assert first.json()["created_count"] == 1
    assert second.json()["created_count"] == 0
    assert second.json()["duplicate_count"] == 1
    with main.SessionLocal() as session:
        events = session.scalars(
            select(AnomalyEvent).where(AnomalyEvent.detector == "capacity_forecast")
        ).all()
    assert len(events) == 1
    assert events[0].severity == "warning"
    assert events[0].target == "node-a"
