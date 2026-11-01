from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any


def _fresh_values(samples: list[dict[str, Any]]) -> list[float]:
    return [
        float(sample["value"])
        for sample in samples
        if sample
        and not sample.get("stale", True)
        and isinstance(sample.get("value"), (int, float))
    ]


def _metric_card(
    samples: list[dict[str, Any]],
    *,
    threshold: float | None = None,
    critical_threshold: float | None = None,
) -> dict[str, Any]:
    values = _fresh_values(samples)
    if not values:
        return {
            "value": None,
            "status": "stale" if samples else "unknown",
            "sample_count": 0,
            "latest_timestamp": None,
        }

    value = max(values)
    timestamps = [
        sample.get("timestamp")
        for sample in samples
        if not sample.get("stale", True) and sample.get("timestamp")
    ]
    latest = max(timestamps) if timestamps else None
    status = "healthy"
    if threshold is not None and value >= threshold:
        status = (
            "critical"
            if critical_threshold is not None and value >= critical_threshold
            else "warning"
        )
    if len(values) != len(samples):
        status = "stale"
    return {
        "value": value,
        "status": status,
        "sample_count": len(values),
        "latest_timestamp": latest,
    }


def build_overview(
    monitoring: dict[str, Any] | None,
    *,
    active_alerts: int,
    critical_alerts: int,
    anomaly_count: int,
    anomaly_severity_counts: dict[str, int],
    cpu_threshold: float,
    memory_threshold: float,
    disk_threshold: float,
    reason: str | None = None,
) -> dict[str, Any]:
    telemetry = monitoring or {}
    metric_data = telemetry.get("metrics") or {}
    cards = {
        "cpu_percent": _metric_card(
            metric_data.get("cpu_percent", []),
            threshold=cpu_threshold,
            critical_threshold=95,
        ),
        "memory_percent": _metric_card(
            metric_data.get("memory_percent", []),
            threshold=memory_threshold,
            critical_threshold=97,
        ),
        "disk_percent": _metric_card(
            metric_data.get("disk_percent", []),
            threshold=disk_threshold,
            critical_threshold=97,
        ),
        "network_receive_bytes_per_second": _metric_card(
            metric_data.get("network_receive_bytes_per_second", [])
        ),
        "network_transmit_bytes_per_second": _metric_card(
            metric_data.get("network_transmit_bytes_per_second", [])
        ),
    }
    targets = telemetry.get("targets") or []
    healthy_targets = sum(
        1
        for target in targets
        if not target.get("up", {}).get("stale")
        and target.get("up", {}).get("value") == 1
    )
    unavailable_targets = sum(
        1
        for target in targets
        if not target.get("up", {}).get("stale")
        and target.get("up", {}).get("value") == 0
    )
    stale_targets = sum(1 for target in targets if target.get("up", {}).get("stale"))
    unknown_targets = len(targets) - healthy_targets - unavailable_targets - stale_targets

    states = [card["status"] for card in cards.values()]
    if monitoring is None:
        health = "unknown"
    elif "critical" in states:
        health = "critical"
    elif unavailable_targets:
        health = "unavailable"
    elif "warning" in states:
        health = "warning"
    elif "stale" in states or stale_targets:
        health = "stale"
    elif "unknown" in states or unknown_targets:
        health = "unknown"
    else:
        health = "healthy"

    return {
        "infrastructure_health": {
            "status": health,
            "reason": reason,
            "collected_at": telemetry.get("collected_at"),
        },
        "metrics": cards,
        "alerts": {
            "active": active_alerts,
            "critical": critical_alerts,
        },
        "anomalies": {
            "total": anomaly_count,
            "severity_distribution": anomaly_severity_counts,
        },
        "targets": {
            "healthy": healthy_targets,
            "unavailable": unavailable_targets,
            "stale": stale_targets,
            "unknown": unknown_targets,
            "unknown_or_stale": unknown_targets + stale_targets,
        },
        "monitoring": monitoring,
    }


def build_diagnostics(
    monitoring: dict[str, Any],
    alerts: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
    *,
    cpu_threshold: float,
    memory_threshold: float,
    disk_threshold: float,
) -> list[dict[str, Any]]:
    metrics = monitoring.get("metrics") or {}
    endpoints = monitoring.get("endpoints") or []
    suggestions: list[dict[str, Any]] = []
    cpu_values = _fresh_values(metrics.get("cpu_percent", []))
    latencies = [
        (endpoint, endpoint.get("latency_seconds", {}))
        for endpoint in endpoints
        if endpoint.get("latency_seconds")
        and not endpoint["latency_seconds"].get("stale")
        and isinstance(endpoint["latency_seconds"].get("value"), (int, float))
    ]
    if cpu_values and latencies:
        high_cpu = max(cpu_values)
        slow_endpoint, latency = max(latencies, key=lambda item: item[1]["value"])
        if high_cpu >= cpu_threshold and latency["value"] >= 2:
            suggestions.append(
                {
                    "type": "resource_pressure",
                    "title": "Possible CPU resource pressure",
                    "suggestion": (
                        "CPU usage exceeded its configured threshold while endpoint response "
                        "time exceeded 2 seconds. Verify application workload and system processes."
                    ),
                    "evidence": [
                        {
                            "metric": "cpu_percent",
                            "value": high_cpu,
                            "threshold": cpu_threshold,
                        },
                        {
                            "metric": "probe_duration_seconds",
                            "value": latency["value"],
                            "target": slow_endpoint.get("endpoint"),
                            "threshold": 2,
                        },
                    ],
                }
            )

    for metric, threshold, label in (
        ("memory_percent", memory_threshold, "memory"),
        ("disk_percent", disk_threshold, "disk"),
    ):
        values = _fresh_values(metrics.get(metric, []))
        if values and max(values) >= threshold:
            suggestions.append(
                {
                    "type": "resource_pressure",
                    "title": f"Possible {label} resource pressure",
                    "suggestion": (
                        f"{label.capitalize()} utilization reached {max(values):.1f}%, "
                        f"above the configured {threshold:.1f}% threshold. Review the "
                        "affected host and recent workload."
                    ),
                    "evidence": [
                        {"metric": metric, "value": max(values), "threshold": threshold}
                    ],
                }
            )

    failed_endpoints = [
        endpoint
        for endpoint in endpoints
        if endpoint.get("success")
        and not endpoint["success"].get("stale")
        and endpoint["success"].get("value") == 0
    ]
    for endpoint in failed_endpoints:
        suggestions.append(
            {
                "type": "connectivity",
                "title": "Possible endpoint connectivity issue",
                "suggestion": (
                    "The HTTP probe failed. Check endpoint availability, DNS, TLS, and "
                    "network connectivity."
                ),
                "evidence": [
                    {
                        "metric": "probe_success",
                        "value": 0,
                        "target": endpoint.get("endpoint"),
                    }
                ],
            }
        )

    for alert in alerts:
        if (
            alert.get("status") == "firing"
            and alert.get("alertname") == "EndpointUnavailable"
            and not any(
                item["evidence"][0].get("target") == alert.get("instance")
                for item in suggestions
                if item["type"] == "connectivity"
            )
        ):
            suggestions.append(
                {
                    "type": "connectivity",
                    "title": "Possible endpoint connectivity issue",
                    "suggestion": (
                        "Alertmanager reports an endpoint probe failure. Check endpoint "
                        "availability and network connectivity."
                    ),
                    "evidence": [
                        {
                            "source": "Alertmanager",
                            "alert": alert.get("alertname"),
                            "status": alert.get("status"),
                            "target": alert.get("instance"),
                            "summary": alert.get("summary"),
                        }
                    ],
                }
            )

    if anomalies:
        latest = anomalies[0]
        suggestions.append(
            {
                "type": "anomaly_review",
                "title": "Recent anomaly requires investigation",
                "suggestion": (
                    "Review the recorded metric evidence and related alerts; this signal "
                    "does not establish a root cause."
                ),
                "evidence": [
                    {
                        "source": latest.get("detector"),
                        "severity": latest.get("severity"),
                        "timestamp": latest.get("timestamp"),
                        "target": latest.get("target"),
                        "metrics": latest.get("metrics"),
                    }
                ],
            }
        )
    return suggestions


def build_historical_analysis(
    events: list[dict[str, Any]], days: int, now: datetime | None = None
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    start_date = (current - timedelta(days=days - 1)).date()
    daily = {
        (start_date + timedelta(days=index)).isoformat(): 0
        for index in range(days)
    }
    severities: Counter[str] = Counter()
    targets: Counter[str] = Counter()
    for event in events:
        timestamp = datetime.fromisoformat(event["timestamp"])
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        day = timestamp.astimezone(UTC).date().isoformat()
        if day in daily:
            daily[day] += 1
        severities[event["severity"]] += 1
        target = event.get("target")
        if target:
            targets[target] += 1
    return {
        "days": days,
        "total": len(events),
        "daily_counts": [{"date": day, "count": count} for day, count in daily.items()],
        "severity_distribution": dict(severities),
        "repeated_targets": [
            {"target": target, "count": count}
            for target, count in targets.most_common()
            if count > 1
        ],
        "timeline": events,
    }
