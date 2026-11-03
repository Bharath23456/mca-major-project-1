from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any


def _fit_linear_trend(
    timestamps: Sequence[float], values: Sequence[float]
) -> tuple[float, float]:
    reference = timestamps[-1]
    hours = [(timestamp - reference) / 3600 for timestamp in timestamps]
    mean_hours = sum(hours) / len(hours)
    mean_values = sum(values) / len(values)
    variance = sum((hour - mean_hours) ** 2 for hour in hours)
    if variance == 0:
        return mean_values, 0.0
    slope = sum(
        (hour - mean_hours) * (value - mean_values)
        for hour, value in zip(hours, values, strict=True)
    ) / variance
    return mean_values - slope * mean_hours, slope


def _holdout_backtest(
    timestamps: Sequence[float], values: Sequence[float], min_samples: int
) -> dict[str, Any] | None:
    holdout_count = max(1, math.ceil(len(values) * 0.2))
    split = len(values) - holdout_count
    if split < min_samples:
        return None

    train_timestamps = timestamps[:split]
    train_values = values[:split]
    intercept, slope = _fit_linear_trend(train_timestamps, train_values)
    reference = train_timestamps[-1]
    errors = [
        abs(
            (intercept + slope * ((timestamp - reference) / 3600))
            - actual
        )
        for timestamp, actual in zip(
            timestamps[split:], values[split:], strict=True
        )
    ]
    return {
        "method": "chronological_holdout",
        "training_samples": split,
        "actual_samples": holdout_count,
        "mean_absolute_error_percent": round(sum(errors) / len(errors), 3),
    }


def forecast_capacity(
    timestamps: Sequence[float],
    values: Sequence[float | None],
    *,
    horizon_hours: float = 6,
    min_samples: int = 8,
    max_sample_age_seconds: int = 600,
    now_timestamp: float | None = None,
    warning_threshold_percent: float = 90,
) -> dict[str, Any]:
    if len(timestamps) != len(values):
        raise ValueError("Timestamps and values must have the same number of items.")
    if horizon_hours <= 0 or not math.isfinite(horizon_hours):
        raise ValueError("Forecast horizon must be a positive finite number.")
    if min_samples < 2:
        raise ValueError("At least two samples must be required.")
    if max_sample_age_seconds < 1:
        raise ValueError("Maximum sample age must be positive.")
    if not 0 <= warning_threshold_percent <= 100:
        raise ValueError("Warning threshold must be between 0 and 100.")

    latest_by_timestamp: dict[float, float] = {}
    for timestamp, value in zip(timestamps, values, strict=True):
        if value is None:
            continue
        if not math.isfinite(timestamp) or not math.isfinite(value):
            continue
        if not 0 <= value <= 100:
            continue
        latest_by_timestamp[timestamp] = value
    observations = sorted(latest_by_timestamp.items())
    valid_timestamps = [timestamp for timestamp, _ in observations]
    valid_values = [value for _, value in observations]
    latest_timestamp = valid_timestamps[-1] if valid_timestamps else None
    latest_value = valid_values[-1] if valid_values else None

    result: dict[str, Any] = {
        "status": "insufficient_data",
        "sample_count": len(observations),
        "last_sample_at": (
            datetime.fromtimestamp(latest_timestamp, UTC).isoformat()
            if latest_timestamp is not None
            else None
        ),
        "horizon_hours": horizon_hours,
        "warning_threshold_percent": warning_threshold_percent,
        "current_value_percent": latest_value,
        "trend_percent_per_hour": None,
        "predicted_value_percent": None,
        "time_to_exhaustion_hours": None,
        "backtest": None,
        "limitations": (
            "Linear extrapolation assumes the recent trend continues; it does not "
            "model workload schedules, seasonality, or future changes."
        ),
    }
    if len(observations) < min_samples:
        result["message"] = f"At least {min_samples} valid samples are required."
        return result

    current_time = (
        now_timestamp if now_timestamp is not None else datetime.now(UTC).timestamp()
    )
    if latest_timestamp is None or current_time - latest_timestamp > max_sample_age_seconds:
        result["status"] = "stale_data"
        result["message"] = "The most recent Prometheus sample is too old to forecast."
        return result

    intercept, slope = _fit_linear_trend(valid_timestamps, valid_values)
    predicted_value = intercept + slope * horizon_hours
    exhaustion_hours = (
        max(0.0, (100 - latest_value) / slope)
        if slope > 0 and latest_value is not None
        else None
    )
    if exhaustion_hours is not None and exhaustion_hours > horizon_hours:
        exhaustion_hours = None

    result.update(
        {
            "status": "forecast_available",
            "trend_percent_per_hour": round(slope, 4),
            "predicted_value_percent": round(predicted_value, 3),
            "time_to_exhaustion_hours": (
                round(exhaustion_hours, 3) if exhaustion_hours is not None else None
            ),
            "backtest": _holdout_backtest(
                valid_timestamps, valid_values, min_samples
            ),
            "message": "Estimate based on a linear trend over recent observations.",
        }
    )
    return result
