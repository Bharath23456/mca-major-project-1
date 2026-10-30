# Local setup and operations

## Requirements

- Windows 10/11 with Docker Desktop, or Ubuntu with Docker Engine and the
  Compose plugin.
- About 2 GB of available memory for all Compose services. Docker image and
  time-series storage use additional disk space.
- Optional native development: Python 3.12 and pip.

## Start

If `.env` does not already exist, copy `.env.example` to create it. Set a
strong `GRAFANA_ADMIN_PASSWORD` before using Grafana. Do not overwrite an
existing `.env`; it may contain local credentials. Do not commit `.env`; it
is ignored by Git.

Windows PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
curl.exe --fail http://127.0.0.1:8000/health/live
curl.exe --fail http://127.0.0.1:8000/health/ready
```

Ubuntu/Linux:

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
nano .env
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

Dashboard and interfaces:

- Application dashboard: <http://127.0.0.1:8000/>
- API docs: <http://127.0.0.1:8000/docs>
- Grafana: <http://127.0.0.1:3000/>
- Prometheus: <http://127.0.0.1:9090/>
- Alertmanager: <http://127.0.0.1:9093/>

## Configure probes and thresholds

Edit `monitoring/prometheus/blackbox_targets.json` and list only endpoints
that you are permitted to monitor. Example:

```json
[
  {
    "targets": ["https://service.example.org/health"],
    "labels": {
      "service": "my-service",
      "environment": "staging"
    }
  }
]
```

Prometheus reloads this file approximately every 30 seconds. Alert thresholds
and evaluation durations are in `monitoring/prometheus/alert_rules.yml`. The
API anomaly-rule thresholds are configured by the `CPU_THRESHOLD_PERCENT`,
`MEMORY_THRESHOLD_PERCENT`, and `DISK_THRESHOLD_PERCENT` environment
variables. Change them in `docker-compose.yml` or add them to `.env` and
recreate the app container with `docker compose up -d --force-recreate app`.

## Useful operational commands

```powershell
docker compose ps
docker compose logs --tail 100 app prometheus alertmanager
docker compose restart app
docker compose down
```

Linux uses the same Compose commands. `docker compose down` stops and removes
containers but keeps persistent volumes. The destructive reset command
`docker compose down -v` removes the local DB, model, dashboards state, and
Prometheus history.

## Native Python run

Python 3.12 is the supported/documented local development version:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m uvicorn app.main:app --reload
```

On Ubuntu/Linux replace the venv creation with
`python3.12 -m venv .venv` and activate using `source .venv/bin/activate`.
Without a separately running Prometheus service, monitoring queries return an
explicit unavailable/degraded state rather than simulated live values.

## Troubleshooting

- `docker compose ps` shows each service and its health state.
- `docker compose logs <service>` shows startup/configuration errors.
- In Prometheus, open **Status → Targets** and verify targets are `UP`.
- Node Exporter host data requires Linux. Docker Desktop on Windows reports
  data from its Linux environment and should not be described as native
  Windows host telemetry.
- If an endpoint is stale, verify DNS/reachability from the Blackbox
  Exporter container and inspect its target in Prometheus.
