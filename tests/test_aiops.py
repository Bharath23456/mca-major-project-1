from datetime import UTC, datetime, timedelta

from app.aiops import (
    build_diagnostic_report,
    build_diagnostics,
    build_historical_analysis,
    build_overview,
)


def test_overview_preserves_unknown_metrics_instead_of_showing_zero() -> None:
    result = build_overview(
        None,
        active_alerts=0,
        critical_alerts=0,
        anomaly_count=0,
        anomaly_severity_counts={},
        cpu_threshold=85,
        memory_threshold=90,
        disk_threshold=90,
    )

    assert result["infrastructure_health"]["status"] == "unknown"
    assert result["metrics"]["cpu_percent"]["value"] is None
    assert result["metrics"]["cpu_percent"]["status"] == "unknown"
    assert result["targets"]["healthy"] == 0


def test_diagnostics_include_metric_evidence_for_each_suggestion() -> None:
    monitoring = {
        "metrics": {
            "cpu_percent": [{"value": 93.0, "stale": False, "timestamp": "now"}],
            "memory_percent": [{"value": 42.0, "stale": False}],
            "disk_percent": [{"value": 50.0, "stale": False}],
        },
        "endpoints": [
            {
                "endpoint": "service-a",
                "success": {"value": 0.0, "stale": False},
                "latency_seconds": {"value": 3.2, "stale": False},
            }
        ],
    }

    suggestions = build_diagnostics(
        monitoring,
        [],
        [],
        cpu_threshold=85,
        memory_threshold=90,
        disk_threshold=90,
    )

    assert {item["type"] for item in suggestions} == {"resource_pressure", "connectivity"}
    assert all(item["evidence"] for item in suggestions)
    assert any(
        item["title"] == "Possible CPU resource pressure"
        and {entry["metric"] for entry in item["evidence"]}
        == {"cpu_percent", "probe_duration_seconds"}
        for item in suggestions
    )


def test_diagnostic_report_groups_evidence_and_does_not_invent_logs() -> None:
    now = datetime.now(UTC)
    timestamp = now.isoformat()
    monitoring = {
        "metrics": {
            "cpu_percent": [
                {
                    "value": 96.0,
                    "unit": "percent",
                    "timestamp": timestamp,
                    "stale": False,
                    "labels": {"instance": "api-1"},
                }
            ]
        },
        "endpoints": [
            {
                "endpoint": "api-1",
                "success": {"value": 0, "timestamp": timestamp, "stale": False},
            }
        ],
        "targets": [
            {
                "instance": "api-1",
                "job": "app",
                "up": {"value": 0, "timestamp": timestamp, "stale": False},
            }
        ],
    }

    report = build_diagnostic_report(
        monitoring,
        [
            {
                "alertname": "HighCPUUsage",
                "severity": "critical",
                "status": "firing",
                "instance": "api-1",
                "summary": "CPU threshold exceeded",
                "starts_at": timestamp,
            }
        ],
        [
            {
                "id": 7,
                "detector": "rule",
                "severity": "critical",
                "explanation": "CPU exceeded its configured threshold.",
                "target": "api-1",
                "metrics": {"cpu_percent": 96},
                "timestamp": timestamp,
            }
        ],
        cpu_threshold=85,
        memory_threshold=90,
        disk_threshold=90,
        window_seconds=600,
        generated_at=now,
    )

    incident = next(item for item in report["incidents"] if item["affected_target"] == "api-1")
    assert report["status"] == "evidence_available"
    assert incident["severity"] == "critical"
    assert incident["related_metrics"][0]["value"] == 96.0
    assert incident["related_alerts"][0]["name"] == "HighCPUUsage"
    assert incident["related_anomalies"][0]["id"] == 7
    assert incident["evidence_level"] == "multiple_sources"
    assert incident["confidence"]["basis"].endswith("not a probability.")
    assert incident["log_events"] == []
    assert report["logs"] == {
        "configured": False,
        "source": None,
        "events": [],
        "note": "No log source is configured; log analysis is not active.",
    }


def test_diagnostic_report_excludes_old_events_and_preserves_unavailable_sources() -> None:
    now = datetime.now(UTC)
    old_timestamp = (now - timedelta(hours=1)).isoformat()
    report = build_diagnostic_report(
        None,
        [
            {
                "alertname": "OldAlert",
                "severity": "critical",
                "status": "resolved",
                "instance": "api-1",
                "updated_at": old_timestamp,
            }
        ],
        [],
        cpu_threshold=85,
        memory_threshold=90,
        disk_threshold=90,
        window_seconds=600,
        generated_at=now,
    )

    assert report["status"] == "no_evidence"
    assert report["prometheus_available"] is False
    assert report["incidents"] == []


def test_history_reports_daily_counts_and_repeated_targets() -> None:
    now = datetime.now(UTC)
    events = [
        {
            "timestamp": (now - timedelta(hours=1)).isoformat(),
            "severity": "warning",
            "target": "node-a",
        },
        {
            "timestamp": (now - timedelta(minutes=10)).isoformat(),
            "severity": "critical",
            "target": "node-a",
        },
    ]

    result = build_historical_analysis(events, 7, now)

    assert result["total"] == 2
    assert result["severity_distribution"] == {"warning": 1, "critical": 1}
    assert result["repeated_targets"] == [{"target": "node-a", "count": 2}]
    assert len(result["daily_counts"]) == 7
