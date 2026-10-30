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
docker compose up --build -d --wait --wait-timeout 180
curl.exe --fail http://127.0.0.1:8000/health/ready
```

Set `GRAFANA_ADMIN_PASSWORD` to a unique password in `.env`; Compose refuses
to start Grafana when this value is missing. `.env` is ignored by Git. Open:

- Dashboard: <http://127.0.0.1:8000/>
- FastAPI documentation: <http://127.0.0.1:8000/docs>
- Grafana: <http://127.0.0.1:3000/>
- Prometheus: <http://127.0.0.1:9090/>
- Alertmanager: <http://127.0.0.1:9093/>

All published ports bind to `127.0.0.1`; they are not published on every
network interface. Grafana uses the username and password from `.env`.
Prometheus and Alertmanager have no application-level login in this local
configuration, so keep them private.

### Ubuntu/Linux

Install Docker Engine and the Docker Compose plugin, then run:

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
${EDITOR:-nano} .env
docker compose up --build -d --wait --wait-timeout 180
curl --fail http://127.0.0.1:8000/health/ready
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
- Dashboard for metric summaries, time-series history, probe status, targets,
  received alerts, and anomaly events.
- Automated tests and GitHub Actions CI. Optional GCP instructions are
  provided, but no cloud resources are created or claimed as deployed.

See [docs/architecture.md](docs/architecture.md),
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
```

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
python -m uvicorn app.main:app --reload
```

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
- Alertmanager's webhook is intended for the private Compose network. Do not
  expose that route through an internet-facing reverse proxy.
- GCP setup is optional and has not been run as part of this local workflow.
