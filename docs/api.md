# API reference

The local API is served at `http://127.0.0.1:8000`. Interactive OpenAPI docs
are at `/docs`; the machine-readable specification is at `/openapi.json`.
List endpoints accept bounded `limit` and `offset` parameters.

## Health and metrics

| Method and path | Purpose | Responses |
|---|---|---|
| `GET /health/live` | Process liveness; does not depend on other services. | `200` with `{"status":"live"}` |
| `GET /health/ready` | Checks the database and Prometheus query API. | `200` when both respond; `503` with per-dependency `ok`/`unavailable` states otherwise. |
| `GET /health` | Backwards-compatible liveness route. | `200` with `{"status":"ok"}` |
| `GET /metrics` | Prometheus text-format application counters and process status. | `200`; this endpoint does not imply host telemetry is available. |
| `GET /api/v1/overview` | Combines Prometheus summary, anomaly detector state, and recent persisted events. | `200` with `status=healthy` or `degraded`; missing telemetry is `null`, not synthesized. |
| `GET /api/v1/metrics` | Current Prometheus measurements with timestamps, units, and stale flags. | `200` when Prometheus answers; `503` when it is unavailable. |
| `GET /api/v1/targets` | Prometheus scrape-target status. | `200` with `healthy`, `degraded`, or `unavailable`; unavailable target data is an empty list plus a reason. |
| `GET /api/v1/monitoring/history?metric=cpu_percent&hours=6` | Bounded time-series query; `hours` is 1–24. | `200` with samples or an empty series; `503` if Prometheus is unavailable. |

`/api/v1/overview` communicates a degraded dependency as a successful response
because it is specifically an operator overview. `/health/ready` and
`/api/v1/metrics` use `503` when their dependency requirements are not met.

## Anomalies and alerts

| Method and path | Purpose | Responses |
|---|---|---|
| `GET /api/v1/anomalies` | Lists persisted anomaly findings. | `200`; `limit` is 1–500 and `offset` is 0–10,000. |
| `GET /api/v1/alerts` | Lists persisted Alertmanager alert states. | `200`; `limit` is 1–500 and `offset` is 0–10,000. |
| `GET /api/v1/anomaly-detection/status` | Describes threshold and model availability. | `200`; a missing or invalid model is reported without disabling threshold rules. |
| `POST /api/v1/anomaly-detection/run` | Reads the latest complete, fresh sample from Prometheus and scores it. | `200` with detector, score, timestamp, and observed features; `503` if any required Prometheus sample is unavailable/stale. |
| `POST /api/v1/anomalies/score` | Scores a caller-provided feature sample. | `200`; invalid values return `422`. |

Scores are not probabilities. An anomaly is an investigation signal, not a
confirmed incident or a root-cause diagnosis. The ML score and threshold
finding are reported separately through the `detector` field and explanatory
text.

Example PowerShell request using a clearly synthetic sample:

```powershell
$sample = @{
  cpu_percent = 96
  memory_percent = 94
  disk_percent = 70
  network_receive_bytes_per_second = 1200
  network_transmit_bytes_per_second = 800
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/anomalies/score `
  -ContentType "application/json" -Body $sample
```

Only `/api/v1/anomalies/score` in this example uses the provided sample. It
does not represent live monitoring. The live scan route reads real
Prometheus data and returns an explicit unavailable error when it cannot.
