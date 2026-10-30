from typing import Any

import httpx

from app.logging_config import get_json_logger
from app.settings import settings

logger = get_json_logger("cloudnetops.prometheus")


class PrometheusUnavailable(RuntimeError):
    """Raised when a configured Prometheus service cannot answer a query."""


async def query(promql: str) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.prometheus_url}/api/v1/query",
                params={"query": promql},
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as error:
        logger.warning(
            "Prometheus query failed",
            extra={
                "event": "prometheus_query_failed",
                "operation": "instant_query",
                "error_type": type(error).__name__,
            },
        )
        raise PrometheusUnavailable("Prometheus is unavailable or the query timed out.") from error

    if payload.get("status") != "success":
        raise PrometheusUnavailable("Prometheus rejected the monitoring query.")
    return payload.get("data", {}).get("result", [])


async def query_range(
    promql: str, start: float, end: float, step_seconds: int
) -> list[dict[str, Any]]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{settings.prometheus_url}/api/v1/query_range",
                params={
                    "query": promql,
                    "start": start,
                    "end": end,
                    "step": f"{step_seconds}s",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as error:
        logger.warning(
            "Prometheus range query failed",
            extra={
                "event": "prometheus_query_failed",
                "operation": "range_query",
                "error_type": type(error).__name__,
            },
        )
        raise PrometheusUnavailable(
            "Prometheus is unavailable or the history query timed out."
        ) from error

    if payload.get("status") != "success":
        raise PrometheusUnavailable("Prometheus rejected the history query.")
    return payload.get("data", {}).get("result", [])
