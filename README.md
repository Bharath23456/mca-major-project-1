# CloudNetOps-AI

CloudNetOps-AI is a local-first, student-scale infrastructure and network
monitoring demonstration. It combines FastAPI, Prometheus, Node Exporter,
Blackbox Exporter, Grafana, Alertmanager, SQLite, and an Isolation Forest with
transparent threshold rules. The system reports signals for investigation; it
does not claim to diagnose every root cause or automatically change
infrastructure.

## Start the complete local stack

The easiest reproducible setup is Docker Desktop with Docker Compose. First
startup downloads the application and monitoring images. Allow about 2 GB of
available memory for the stack; actual usage depends on the host and Docker.
No GCP resources or paid services are used by these local commands.

### Windows PowerShell

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
New-Item -ItemType Directory -Force .\secrets | Out-Null
if (-not (Test-Path .\secrets\alertmanager-webhook-token)) {
  $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
  $bytes = New-Object byte[] 32
  $rng.GetBytes($bytes)
  [System.IO.File]::WriteAllText(
    (Join-Path (Get-Location) 'secrets\alertmanager-webhook-token'),
    [Convert]::ToBase64String($bytes)
  )
}
docker compose up --build -d --wait --wait-timeout 180
curl.exe --fail http://127.0.0.1:8000/health/ready
docker compose exec app python -m app.auth_setup
```

Set `GRAFANA_ADMIN_PASSWORD` to a unique password in `.env`; Compose refuses
to start Grafana when this value is missing. The commands create a random
Alertmanager webhook token in the ignored `secrets/` directory; do not commit
or share it. Both `.env` and `secrets/` are ignored by Git. Open:

- Dashboard: <http://127.0.0.1:8000/>
- FastAPI documentation: <http://127.0.0.1:8000/docs>
- Grafana: <http://127.0.0.1:3000/>
- Prometheus: <http://127.0.0.1:9090/>
- Alertmanager: <http://127.0.0.1:9093/>

All published ports bind to `127.0.0.1`; they are not published on every
network interface. Grafana uses the username and password from `.env`.
Prometheus and Alertmanager have no application-level login in this local
configuration, so keep them private. On first setup, the final command above
prompts for the first administrator's username, email, and password. It
creates no default credentials and refuses to run once an administrator exists.
Sign in at <http://127.0.0.1:8000/login>.
The sign-in page also offers self-registration for read-only `VIEWER` accounts;
register with a username, email, and password of at least 12 characters, then
sign in with either your username or email. Use the first-admin setup command
above to create an administrator; public registration cannot grant elevated
roles. The copied local `.env.example` selects `CAPTCHA_MODE=test` for
loopback-only development. Before exposing the app beyond local development,
configure Google reCAPTCHA v2 using `CAPTCHA_MODE=recaptcha`,
`RECAPTCHA_SITE_KEY`, and `RECAPTCHA_SECRET_KEY`. Never use test mode on a
shared or public deployment.

### Ubuntu/Linux

Install Docker Engine and the Docker Compose plugin, then run:

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
${EDITOR:-nano} .env
install -d -m 700 secrets
if [ ! -f secrets/alertmanager-webhook-token ]; then
  umask 077
  openssl rand -base64 32 > secrets/alertmanager-webhook-token
fi
sudo chown root:10001 secrets/alertmanager-webhook-token
sudo chmod 0440 secrets/alertmanager-webhook-token
docker compose up --build -d --wait --wait-timeout 180
curl --fail http://127.0.0.1:8000/health/ready
docker compose exec app python -m app.auth_setup
```

### Stop and preserve data

```powershell
docker compose down
```

The named volumes preserve Prometheus history, Grafana state, SQLite events,
and the trained demo model. `docker compose down -v` deletes these volumes and
their data; use that only when you intentionally want a clean reset.

## What is implemented

- FastAPI liveness endpoint, OpenAPI documentation, configuration validation,
  Prometheus text metrics, read-only current and historical metric APIs.
- Prometheus collection of app and Linux host metrics, plus configurable
  Blackbox HTTP/HTTPS probes.
- Grafana dashboard provisioned with CPU, memory, disk, endpoint, and network
  panels, active Prometheus alerts, and app anomaly counters; alert rules are
  routed through Alertmanager to local SQLite history.
- Threshold-based anomaly detection and Isolation Forest scoring. The
  container trains a deterministic demo model only when its persistent model
  file is absent. Its training and evaluation data are synthetic and clearly
  labelled as such.
- Argon2id-backed authentication, expiring server-side sessions, CSRF
  protection, login throttling, backend-verified Google reCAPTCHA v2 (with an
  explicit local-only test mode), and ADMIN/OPERATOR/VIEWER backend permissions.
- Responsive, role-aware dashboard for real Prometheus metrics, targets, alerts,
  anomaly findings, diagnostics, read-only runtime settings, model status,
  incidents, user administration, and audit history. Unavailable telemetry
  remains unknown/unavailable, never zero.
- Hybrid threshold and Isolation Forest event history, rule-based alert
  correlation, evidence-backed diagnostic suggestions, and incident workflows
  with assignment, notes, acknowledgement, resolution, and audit history.
- Explainable per-target CPU, memory, and disk forecasts based on a simple
  linear trend over recent Prometheus data, including chronological holdout
  error and a six-hour horizon. Warning-event generation is opt-in and
  requires an ADMIN or OPERATOR action.
- Alembic migrations preserve existing alert/anomaly data while adding
  authentication and incident tables.
- Automated tests and GitHub Actions CI. Optional GCP instructions are
  provided, but no cloud resources are created or claimed as deployed.

See [docs/architecture.md](docs/architecture.md),
[docs/grafana-setup.md](docs/grafana-setup.md),
[docs/database.md](docs/database.md),
[docs/api.md](docs/api.md), [docs/ml-design.md](docs/ml-design.md),
[docs/setup.md](docs/setup.md), [docs/testing.md](docs/testing.md),
[docs/security.md](docs/security.md), [docs/runbook.md](docs/runbook.md),
[docs/known-limitations.md](docs/known-limitations.md),
[docs/deployment-gcp.md](docs/deployment-gcp.md),
[docs/deployment.md](docs/deployment.md),
[docs/report_outline.md](docs/report_outline.md),
[docs/report_draft.md](docs/report_draft.md),
[docs/presentation_outline.md](docs/presentation_outline.md), and
[docs/demo_script.md](docs/demo_script.md).

## Host metrics and endpoint configuration

Node Exporter reports Linux host metrics. With Docker Desktop on Windows, the
exporter sees the Docker Linux environment, not all native Windows host
measurements. For meaningful host CPU, memory, disk, network, and uptime
metrics, run the stack on a Linux host or Linux VM.

The initial Blackbox target is `https://example.com`. Edit
`monitoring/prometheus/blackbox_targets.json` to add only endpoints you own or
are authorized to monitor. Prometheus discovers file changes automatically;
allow up to 30 seconds for the target list to refresh. Probes are ordinary
HTTP GET checks and do not scan networks.

## API examples

```text
GET  /health
GET  /health/live
GET  /health/ready
GET  /api/v1/overview
GET  /api/v1/metrics
GET  /api/v1/targets
GET  /api/v1/config/validate
GET  /api/v1/monitoring/summary
GET  /api/v1/monitoring/history?metric=cpu_percent&hours=6
GET  /api/v1/alerts
GET  /api/v1/anomalies
GET  /api/v1/anomalies/status
POST /api/v1/anomalies/scan
POST /api/v1/anomalies/score
GET  /api/v1/anomaly-detection/status
POST /api/v1/anomaly-detection/run
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
GET  /api/aiops/overview
GET  /api/aiops/anomalies
GET  /api/aiops/correlations
GET  /api/aiops/diagnostics
GET  /api/aiops/model-status
GET  /api/aiops/history
GET  /api/incidents
GET  /api/incidents/{id}
POST /api/incidents/{id}/acknowledge
POST /api/incidents/{id}/notes
POST /api/incidents/{id}/resolve
PATCH /api/incidents/{id}/assign
GET  /api/users                 (ADMIN)
POST /api/users                 (ADMIN)
PATCH /api/users/{id}           (ADMIN)
PATCH /api/users/{id}/role      (ADMIN)
GET  /api/audit-logs            (ADMIN)
```

All application APIs except the explicitly documented health/scrape routes
require an authenticated session. The private Alertmanager integration route
instead requires its dedicated bearer-token secret. Use the first-admin
bootstrap procedure above; there is no seeded account.
See [docs/api.md](docs/api.md) for role requirements, CSRF use, and filters.

`/api/v1/anomalies/scan` reads the latest complete metric sample from
Prometheus; it returns an explicit error when any required sample is absent or
stale. `/api/v1/anomalies/score` accepts a validated metric sample. Training
does not have an HTTP endpoint. To deliberately retrain the demo model in the
running app container:

```powershell
docker compose exec app python -m app.anomaly_detection.train
```

```bash
docker compose exec app python -m app.anomaly_detection.train
```

This command uses deterministic labelled synthetic data, stores the model in
the application data volume, and prints measured precision, recall, F1, and
confusion-matrix results for that synthetic test split. Do not present those
metrics as accuracy on live infrastructure.

## Native development and tests

Python 3.12 is the documented development baseline. In a virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m app.auth_setup
python -m uvicorn app.main:app --reload
```

The local dashboard uses an HttpOnly session cookie. `SESSION_COOKIE_SECURE`
is `false` for loopback HTTP; set it to `true` when serving behind HTTPS.
Admin setup is an interactive local command, not an HTTP endpoint.

On Ubuntu/Linux, use `python3.12 -m venv .venv` and
`source .venv/bin/activate` instead. For native development without Compose,
Prometheus-backed pages need a separately running Prometheus instance. The
health endpoint and rule-based sample scoring remain available without it.

## Limitations

- Local SQLite is appropriate for a student demonstration, not concurrent
  high-volume production workloads.
- Synthetic data is provided for repeatable model demonstrations. Replace it
  with sufficient labelled historical metrics before drawing conclusions
  about a real environment.
- Isolation Forest provides a sample-level score, not causal explanations.
- Linux host measurements are not native Windows measurements under Docker
  Desktop.
- Alertmanager's webhook requires a private Compose secret and is intended
  only for the private Compose network. Do not expose it through an
  internet-facing reverse proxy.
- GCP setup is optional and has not been run as part of this local workflow.
