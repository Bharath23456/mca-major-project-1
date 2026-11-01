from datetime import UTC, datetime, timedelta

from app.aiops import build_diagnostics, build_historical_analysis, build_overview


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
