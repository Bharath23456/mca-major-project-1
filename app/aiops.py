import math
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


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def build_diagnostic_report(
    monitoring: dict[str, Any] | None,
    alerts: list[dict[str, Any]],
    anomalies: list[dict[str, Any]],
    *,
    cpu_threshold: float,
    memory_threshold: float,
    disk_threshold: float,
    window_seconds: int,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    now = generated_at or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    now = now.astimezone(UTC)
    window_start = now - timedelta(seconds=window_seconds)
    report_groups: dict[str, dict[str, Any]] = {}

    def group_for(target: str | None) -> dict[str, Any]:
        target_name = target or "aggregate (target unavailable)"
        return report_groups.setdefault(
            target_name,
            {
                "target": target_name,
                "metrics": [],
                "alerts": [],
                "anomalies": [],
                "factors": [],
                "sources": set(),
                "metric_factors": set(),
            },
        )

    def is_recent(value: Any) -> bool:
        timestamp = _parse_timestamp(value)
        return timestamp is None or timestamp >= window_start

    telemetry = monitoring or {}
    diagnostic_metrics = telemetry.get("diagnostic_metrics") or {}
    metric_thresholds = {
        "cpu_percent": cpu_threshold,
        "memory_percent": memory_threshold,
        "disk_percent": disk_threshold,
    }
    critical_thresholds = {
        "cpu_percent": 95.0,
        "memory_percent": 97.0,
        "disk_percent": 97.0,
    }
    for metric, samples in (telemetry.get("metrics") or {}).items():
        samples = diagnostic_metrics.get(metric) or samples
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict) or sample.get("stale", True):
                continue
            value = sample.get("value")
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            timestamp = sample.get("timestamp")
            if timestamp and not is_recent(timestamp):
                continue
            labels = sample.get("labels") or {}
            target = labels.get("instance") or sample.get("target")
            evidence = {
                "metric": metric,
                "value": value,
                "unit": sample.get("unit"),
                "timestamp": timestamp,
                "labels": labels,
            }
            group = group_for(target)
            group["metrics"].append(evidence)
            group["sources"].add("Prometheus metrics")
            threshold = metric_thresholds.get(metric)
            if threshold is not None and value >= threshold:
                severity = (
                    "critical"
                    if value >= critical_thresholds[metric]
                    else "warning"
                )
                group["factors"].append(
                    {
                        "type": "resource_threshold",
                        "metric": metric,
                        "description": (
                            f"{metric} reached {value:.1f}, at or above the configured "
                            f"{threshold:.1f} threshold."
                        ),
                        "severity": severity,
                        "evidence": [evidence],
                    }
                )
                group["metric_factors"].add(metric)

    for endpoint in telemetry.get("endpoints") or []:
        target = endpoint.get("endpoint")
        for key, metric in (
            ("success", "probe_success"),
            ("latency_seconds", "probe_duration_seconds"),
            ("http_status_code", "probe_http_status_code"),
        ):
            sample = endpoint.get(key) or {}
            value = sample.get("value")
            if (
                sample.get("stale", True)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or (sample.get("timestamp") and not is_recent(sample["timestamp"]))
            ):
                continue
            evidence = {
                "metric": metric,
                "value": value,
                "unit": sample.get("unit"),
                "timestamp": sample.get("timestamp"),
                "target": target,
            }
            group = group_for(target)
            group["metrics"].append(evidence)
            group["sources"].add("Prometheus probes")
            if key == "success" and value == 0:
                group["factors"].append(
                    {
                        "type": "endpoint_unavailable",
                        "description": "The current endpoint probe reports failure.",
                        "severity": "critical",
                        "evidence": [evidence],
                    }
                )

    for target_status in telemetry.get("targets") or []:
        sample = target_status.get("up") or {}
        if sample.get("stale", True) or sample.get("value") != 0:
            continue
        target = target_status.get("instance")
        evidence = {
            "metric": "up",
            "value": sample.get("value"),
            "timestamp": sample.get("timestamp"),
            "job": target_status.get("job"),
            "target": target,
        }
        group = group_for(target)
        group["sources"].add("Prometheus target health")
        group["factors"].append(
            {
                "type": "target_unavailable",
                "description": "Prometheus reports this scrape target as unavailable.",
                "severity": "critical",
                "evidence": [evidence],
            }
        )

    for alert in alerts:
        alert_timestamp = alert.get("starts_at") or alert.get("updated_at")
        if alert.get("status") != "firing" and not is_recent(alert_timestamp):
            continue
        target = alert.get("instance")
        group = group_for(target)
        group["alerts"].append(
            {
                "name": alert.get("alertname"),
                "severity": alert.get("severity", "unknown"),
                "status": alert.get("status"),
                "summary": alert.get("summary"),
                "timestamp": alert_timestamp,
            }
        )
        group["sources"].add("Alertmanager")
        if alert.get("status") == "firing":
            group["factors"].append(
                {
                    "type": "firing_alert",
                    "description": "Alertmanager has a currently firing alert for this target.",
                    "severity": alert.get("severity", "unknown"),
                    "evidence": [
                        {
                            "alert": alert.get("alertname"),
                            "severity": alert.get("severity", "unknown"),
                            "status": alert.get("status"),
                            "summary": alert.get("summary"),
                            "timestamp": alert_timestamp,
                        }
                    ],
                }
            )

    for anomaly in anomalies:
        timestamp = anomaly.get("timestamp")
        if timestamp and not is_recent(timestamp):
            continue
        target = anomaly.get("target")
        group = group_for(target)
        group["anomalies"].append(
            {
                "id": anomaly.get("id"),
                "detector": anomaly.get("detector"),
                "severity": anomaly.get("severity", "unknown"),
                "explanation": anomaly.get("explanation"),
                "metrics": anomaly.get("metrics", {}),
                "timestamp": timestamp,
            }
        )
        group["sources"].add("Stored anomaly events")
        group["factors"].append(
            {
                "type": "recorded_anomaly",
                "description": (
                    "A stored anomaly overlaps this diagnostic window; it is a signal "
                    "for investigation, not a confirmed cause."
                ),
                "severity": anomaly.get("severity", "unknown"),
                "evidence": [
                    {
                        "detector": anomaly.get("detector"),
                        "severity": anomaly.get("severity", "unknown"),
                        "metrics": anomaly.get("metrics", {}),
                        "timestamp": timestamp,
                    }
                ],
            }
        )

    severity_rank = {"critical": 4, "warning": 3, "info": 2, "unknown": 1}
    reports = []
    for group in report_groups.values():
        grouped_factors: dict[tuple[str, str], dict[str, Any]] = {}
        for factor in group["factors"]:
            factor_type = factor["type"]
            key = (
                factor_type,
                factor.get("metric", "") if factor_type == "resource_threshold" else "",
            )
            existing_factor = grouped_factors.get(key)
            if existing_factor is None:
                grouped_factors[key] = {**factor, "evidence": list(factor["evidence"])}
                continue
            existing_factor["evidence"].extend(factor["evidence"])
            if severity_rank.get(factor.get("severity"), 1) > severity_rank.get(
                existing_factor.get("severity"), 1
            ):
                existing_factor["severity"] = factor["severity"]
            if factor_type == "resource_threshold" and (
                factor["evidence"][0]["value"] > existing_factor["evidence"][0]["value"]
            ):
                existing_factor["description"] = factor["description"]
        factors = list(grouped_factors.values())
        if not factors:
            continue
        severities = [
            factor.get("severity", "unknown")
            for factor in factors
        ]
        severity = max(severities, key=lambda value: severity_rank.get(value, 1))
        source_count = len(group["sources"])
        evidence_level = (
            "multiple_sources"
            if source_count >= 3
            else "correlated_sources"
            if source_count == 2
            else "single_source"
        )
        metric_names = sorted(
            {
                item["metric"]
                for item in group["metrics"]
                if item["metric"] in group["metric_factors"]
            }
        )
        recommendations = [
            "Compare the observed signals with the same target's recent metric history.",
            "Check recent deployments, configuration changes, and workload changes.",
            "Confirm service impact with the service owner before taking corrective action.",
        ]
        if "endpoint_unavailable" in {factor["type"] for factor in group["factors"]}:
            recommendations.insert(
                0, "Verify DNS, TLS, endpoint health, and the network path from the probe."
            )
        if metric_names:
            recommendations.insert(
                0, f"Inspect the affected resource metrics: {', '.join(metric_names)}."
            )
        reports.append(
            {
                "incident_summary": (
                    f"Observed {len(group['factors'])} diagnostic signal(s) for "
                    f"{group['target']}; these observations do not confirm root cause."
                ),
                "affected_target": group["target"],
                "severity": severity,
                "related_metrics": group["metrics"],
                "related_alerts": group["alerts"],
                "related_anomalies": group["anomalies"],
                "possible_contributing_factors": factors,
                "recommended_investigation_steps": recommendations,
                "log_events": [],
                "evidence_level": evidence_level,
                "confidence": {
                    "level": evidence_level,
                    "basis": f"{source_count} observed source type(s); not a probability.",
                },
                "timestamp": now.isoformat(),
            }
        )

    reports.sort(
        key=lambda item: severity_rank.get(item["severity"], 1),
        reverse=True,
    )
    return {
        "status": "evidence_available" if reports else "no_evidence",
        "timestamp": now.isoformat(),
        "window": {
            "start": window_start.isoformat(),
            "end": now.isoformat(),
            "seconds": window_seconds,
        },
        "prometheus_available": monitoring is not None,
        "logs": {
            "configured": False,
            "source": None,
            "events": [],
            "note": "No log source is configured; log analysis is not active.",
        },
        "incidents": reports,
        "notice": (
            "Reports summarize observed evidence and correlations only. They are not "
            "confirmed root causes or forecasts."
        ),
    }


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
