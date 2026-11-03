# API reference

The local API is served at `http://127.0.0.1:8000`. Sign in at `/login` before
using application APIs or the interactive OpenAPI docs. The `/health*` and
Prometheus `/metrics` scrape endpoints remain public for local orchestration.
The Alertmanager webhook is reserved for the private Compose network and
requires the dedicated bearer-token secret.
List endpoints accept bounded `limit` and `offset` parameters.

## Authentication

| Method and path | Purpose | Responses |
|---|---|---|
| `GET /api/auth/captcha-config` | Return the CAPTCHA mode and public reCAPTCHA site key, if configured. | `200`; `503` if reCAPTCHA mode is missing required configuration. |
| `POST /api/auth/register` | Public registration with username, email, password, and confirmation; creates an active `VIEWER` account only. | `201`; validation failures return `422`, duplicate account identifiers return `409`, throttled attempts return `429`. |
| `POST /api/auth/login` | Sign in with `username` (username or email), `password`, and the CAPTCHA response token; sets session and CSRF cookies only after server-side CAPTCHA verification. | `200`; invalid credentials return a generic `401`, failed CAPTCHA returns `400`, provider/configuration failure returns `503`, throttled attempts return `429`. |
| `POST /api/auth/logout` | Revoke the current session and clear cookies. | Requires `X-CSRF-Token`; `200` after sign out. |
| `GET /api/auth/me` | Return the authenticated user's identity and role. | `401` without a valid session. |

The session cookie is opaque, HttpOnly, SameSite=Strict, and backed by a
server-side expiring session record; the database stores only its SHA-256
digest. Mutating requests require the matching `cloudnetops_csrf` cookie and
`X-CSRF-Token` header. The CSRF cookie is not an authentication credential.
No wildcard CORS policy is enabled.

Create the first administrator locally with `python -m app.auth_setup` (or
`docker compose exec app python -m app.auth_setup`). This prompts for
credentials and refuses setup if an administrator already exists. There is
no default account or built-in password. Self-registration is open, but can
only create read-only `VIEWER` accounts; an administrator must create or
promote accounts to `OPERATOR` or `ADMIN`.

The local `.env.example` explicitly uses `CAPTCHA_MODE=test`, which accepts
only the application's documented local test token and does not contact
Google. This mode is for loopback development only. For a real deployment,
set `CAPTCHA_MODE=recaptcha` and configure the Google reCAPTCHA v2 checkbox
site key and secret using `RECAPTCHA_SITE_KEY` and `RECAPTCHA_SECRET_KEY`.
Only the public site key is returned to the browser. The backend verifies each
login response with Google's siteverify endpoint; verification failures are
rate-limited and audited without recording the token or secret.

## Health and metrics

| Method and path | Purpose | Responses |
|---|---|---|
| `GET /health/live` | Process liveness; does not depend on other services. | `200` with `{"status":"live"}` |
| `GET /health/ready` | Checks the database and Prometheus query API. | `200` when both respond; `503` with per-dependency `ok`/`unavailable` states otherwise. |
| `GET /health` | Backwards-compatible liveness route. | `200` with `{"status":"ok"}` |
| `GET /metrics` | Prometheus text-format application counters and process status. | `200`; this endpoint does not imply host telemetry is available. |
| `GET /api/v1/overview` | Combines Prometheus summary, anomaly detector state, and recent persisted events. | `200` with `status=healthy` or `degraded`; missing telemetry is `null`, not synthesized. 
| `GET /api/v1/metrics` | Current Prometheus measurements with timestamps, units, and stale flags. | `200` when Prometheus answers; `503` when it is unavailable. |
| `GET /api/v1/targets` | Prometheus scrape-target status. | `200` with `healthy`, `degraded`, or `unavailable`; unavailable target data is an empty list plus a reason. |
| `GET /api/v1/monitoring/history?metric=cpu_percent&hours=6` | Bounded time-series query; `hours` is 1–24. | `200` with samples or an empty series; `503` if Prometheus is unavailable. |

## Capacity forecasting

| Method and path | Access | Purpose and responses |
|---|---|---|
| `GET /api/aiops/forecasts/capacity` | Any authenticated role | Per-target CPU, memory, and disk linear forecasts from up to 24 hours of Prometheus samples; includes six-hour estimates, stale/insufficient-data states, and a chronological holdout error when enough history exists. Returns `503` if Prometheus is unavailable. |
| `POST /api/aiops/forecasts/capacity/warnings` | ADMIN, OPERATOR | Explicitly evaluates configured forecast thresholds and stores deduplicated warning anomaly events. Returns `409` unless `CAPACITY_FORECAST_WARNINGS_ENABLED=true`; `503` if Prometheus is unavailable. |

Warning generation is disabled by default and is an explicit action, not an
automatic background process. The trend and historical holdout error are not
production accuracy guarantees. Forecast events do not automatically create
incidents or trigger remediation.

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

$login = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/auth/login `
  -ContentType "application/json" `
  -Body (@{
    username = "YOUR_USERNAME"
    password = "YOUR_PASSWORD"
    captcha_token = "cloudnetops-local-captcha-test-token"
  } | ConvertTo-Json) `
  -SessionVariable cloudnetopsSession
$csrf = $login.csrf_token

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/anomalies/score `
  -WebSession $cloudnetopsSession `
  -Headers @{ "X-CSRF-Token" = $csrf } `
  -ContentType "application/json" -Body $sample
```

The sample login token above works only when `CAPTCHA_MODE=test`; never use
that token with `CAPTCHA_MODE=recaptcha`. Only `/api/v1/anomalies/score` uses
the caller-provided sample; it does not represent live monitoring. The live
scan route reads real Prometheus data and returns an explicit unavailable
error when it cannot.

## Roles and administration

| Role | Allowed operations |
|---|---|
| `ADMIN` | Read all monitoring and incident data; manage users and roles; view audit history; manage incidents. |
| `OPERATOR` | Read monitoring, anomalies, and incidents; acknowledge/resolve incidents, assign operators, and add notes. |
| `VIEWER` | Read-only monitoring, anomaly, and incident access. |

Roles are checked on the backend. UI navigation is not an authorization
boundary. Mutating requests use the session-bound CSRF cookie/header described
above.

| Method and path | Access | Purpose |
|---|---|---|
| `GET /api/users?limit=50&offset=0` | ADMIN | List user metadata; password hashes are never serialized. |
| `POST /api/users` | ADMIN | Create an active account with a validated username, email, password, and role. |
| `PATCH /api/users/{id}` | ADMIN | Activate/deactivate; deactivation revokes sessions. |
| `PATCH /api/users/{id}/role` | ADMIN | Change role; the last active admin cannot be demoted/deactivated. |
| `GET /api/users/{id}/activity` | ADMIN | Review activity for a user. |
| `GET /api/audit-logs?action=...&resource_type=...` | ADMIN | Filter and page audit records. |

## AIOps and incidents

| Method and path | Access | Purpose |
|---|---|---|
| `GET /api/aiops/overview` | Any authenticated role | Monitoring summary, active/critical alert counts, anomaly counts, latest findings, and model status. |
| `GET /api/aiops/anomalies?severity=warning&source=rule&target=...` | Any authenticated role | Filter persisted findings; `limit` is 1–500 and `offset` is 0–10,000. |
| `GET /api/aiops/correlations?limit=50` | Any authenticated role | Incident groupings and per-event correlation reasons; limit is 1–200. |
| `GET /api/aiops/diagnostics` | Any authenticated role | Rule-based, target-grouped report with current metric, alert, and anomaly evidence; stored events remain available if Prometheus is down. Logs are explicitly marked unconfigured. |
| `GET /api/aiops/model-status` | Any authenticated role | Model availability, type/version/schema, training metadata when present, and last inference status. |
| `GET /api/aiops/history?days=30` | Any authenticated role | Stored anomaly counts/distribution and incident timeline; days is 1–365. |
| `GET /api/incidents?status=OPEN&severity=critical&target=...&query=...` | Any authenticated role | Filter incident list; `limit` is 1–200 and `offset` is 0–10,000. |
| `GET /api/incidents/{id}` | Any authenticated role | Incident, related events/evidence, notes, and audit history. |
| `GET /api/incidents/operators` | ADMIN, OPERATOR | List active operators assignable to an incident. |
| `PATCH /api/incidents/{id}/assign` | ADMIN, OPERATOR | Assign an active operator or send `{"operator_id":null}` to unassign. |
| `POST /api/incidents/{id}/acknowledge` | ADMIN, OPERATOR | Change `OPEN` to `ACKNOWLEDGED`; resolved incidents return `409`. |
| `POST /api/incidents/{id}/notes` | ADMIN, OPERATOR | Add a non-empty note (maximum 4,000 characters). |
| `POST /api/incidents/{id}/resolve` | ADMIN, OPERATOR | Set incident state to `RESOLVED`. |

Incident states are `OPEN`, `ACKNOWLEDGED`, and `RESOLVED`. Alert fingerprints
are linked only once, preventing duplicate event relationships. Correlation is
rule-based and uses target, metric family, timestamps, severity, and a
configurable time window; it is not a definitive root-cause analysis.
Each incident exposes linked-event evidence, a correlation reason, and a
heuristic priority score using severity as an impact proxy, event frequency,
and same-target recurrence. Configurable repeat-count rules raise severity at
the configured warning and critical counts. The priority score is not a
business-impact estimate. Anomaly scores are not probabilities. Diagnostic
reports distinguish evidence from possible contributing factors and never
claim a confirmed root cause or trigger automatic remediation.

Audit records describe actions and results without storing passwords, session
tokens, CSRF tokens, or the body of incident notes.
11111