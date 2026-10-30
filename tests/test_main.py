from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_is_independent_of_monitoring_dependencies(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_readiness_reports_unavailable_prometheus(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(_: str) -> list[dict]:
        raise main.PrometheusUnavailable("Prometheus is unavailable or the query timed out.")

    monkeypatch.setattr(main, "prometheus_query", unavailable)
    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "degraded",
        "checks": {"database": "ok", "prometheus": "unavailable"},
    }


def test_readiness_returns_ready_when_dependencies_respond(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def available(_: str) -> list[dict]:
        return []

    monkeypatch.setattr(main, "prometheus_query", available)
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "prometheus": "ok"},
    }


def test_openapi_documents_health_endpoint(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/api/v1/overview" in paths
    assert "/api/v1/metrics" in paths
    assert "/api/v1/targets" in paths
    assert "/api/v1/anomaly-detection/status" in paths
    assert "/api/v1/anomaly-detection/run" in paths


def test_metrics_endpoint_returns_prometheus_text(client: TestClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "cloudnetops_app_up 1.0" in response.text


def test_anomaly_score_records_threshold_event(client: TestClient) -> None:
    response = client.post(
        "/api/v1/anomalies/score",
        json={
            "cpu_percent": 96,
            "memory_percent": 95,
            "disk_percent": 75,
            "network_receive_bytes_per_second": 1200,
            "network_transmit_bytes_per_second": 800,
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["is_anomaly"] is True
    assert result["detector"] == "rule"
    assert result["event_id"] is not None
    assert "not a confirmed incident" in result["warning"]
    app_metrics = client.get("/metrics").text
    assert 'cloudnetops_anomaly_evaluations_total{detector="rule"}' in app_metrics
    assert 'cloudnetops_anomaly_findings_total{detector="rule",severity="critical"}' in app_metrics


def test_anomaly_score_validates_percentages(client: TestClient) -> None:
    response = client.post(
        "/api/v1/anomalies/score",
        json={
            "cpu_percent": 101,
            "memory_percent": 50,
            "disk_percent": 75,
            "network_receive_bytes_per_second": 0,
            "network_transmit_bytes_per_second": 0,
        },
    )

    assert response.status_code == 422


def test_config_validation_reports_thresholds(client: TestClient) -> None:
    response = client.get("/api/v1/config/validate")

    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_dashboard_and_stylesheet_are_served(client: TestClient) -> None:
    dashboard_response = client.get("/")
    stylesheet_response = client.get("/static/styles.css")

    assert dashboard_response.status_code == 200
    assert "System overview" in dashboard_response.text
    assert stylesheet_response.status_code == 200


def test_summary_marks_values_with_units_and_fresh_timestamps(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_query_many(queries: dict[str, str]) -> dict[str, list[dict]]:
        timestamp = datetime.now(UTC).timestamp()
        return {
            name: [{"metric": {"instance": "sample"}, "value": [timestamp, "42"]}]
            for name in queries
        }

    monkeypatch.setattr(main, "_query_many", fake_query_many)
    response = client.get("/api/v1/monitoring/summary")

    assert response.status_code == 200
    result = response.json()
    cpu = result["metrics"]["cpu_percent"][0]
    assert cpu["value"] == 42
    assert cpu["unit"] == "percent"
    assert cpu["stale"] is False
    assert result["targets"][0]["up"]["unit"] == "boolean"


def test_overview_reports_degraded_when_prometheus_is_unavailable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(_: dict[str, str]) -> dict[str, list[dict]]:
        raise main.PrometheusUnavailable("Prometheus is unavailable or the query timed out.")

    monkeypatch.setattr(main, "_query_many", unavailable)
    response = client.get("/api/v1/overview")

    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "degraded"
    assert result["monitoring"]["metrics"] is None
    assert result["monitoring"]["source"] == "Prometheus"
    assert result["reason"] == "Prometheus is unavailable or the query timed out."


def test_targets_reports_unavailable_when_prometheus_is_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unavailable(_: str) -> list[dict]:
        raise main.PrometheusUnavailable("Prometheus is unavailable or the query timed out.")

    monkeypatch.setattr(main, "prometheus_query", unavailable)
    response = client.get("/api/v1/targets")

    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["targets"] == []


def test_corrupt_model_is_reported_without_hiding_rule_detection(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def corrupt_model() -> None:
        raise ValueError("corrupt artifact")

    monkeypatch.setattr(main, "load_model", corrupt_model)
    status = client.get("/api/v1/anomaly-detection/status")
    score = client.post(
        "/api/v1/anomalies/score",
        json={
            "cpu_percent": 96,
            "memory_percent": 95,
            "disk_percent": 75,
            "network_receive_bytes_per_second": 1200,
            "network_transmit_bytes_per_second": 800,
        },
    )

    assert status.json()["isolation_forest"] == "unavailable"
    assert score.status_code == 200
    assert score.json()["detector"] == "rule"
    assert score.json()["model_status"] == "unavailable"
    assert score.json()["score_is_probability"] is False


def test_anomaly_scan_requires_fresh_prometheus_samples(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_samples(_: dict[str, str]) -> dict[str, list[dict]]:
        return {name: [] for name in main.SCAN_METRIC_NAMES}

    monkeypatch.setattr(main, "_query_many", no_samples)
    response = client.post("/api/v1/anomalies/scan")

    assert response.status_code == 503
    assert "No fresh Prometheus sample" in response.json()["detail"]


def test_alertmanager_webhook_stores_alert_history(client: TestClient) -> None:
    response = client.post(
        "/api/v1/alerts/webhook",
        json={
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "DemoAlert",
                        "severity": "warning",
                        "instance": "demo-target",
                    },
                    "annotations": {"summary": "A test alert"},
                    "startsAt": "2026-10-27T00:00:00Z",
                    "endsAt": "0001-01-01T00:00:00Z",
                    "fingerprint": "test-alert-fingerprint",
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {"received": 1}
    alerts = client.get("/api/v1/alerts").json()
    saved = next(alert for alert in alerts if alert["alertname"] == "DemoAlert")
    assert saved["status"] == "firing"
    assert saved["summary"] == "A test alert"
