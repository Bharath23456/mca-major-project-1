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

The example `.env` uses `CAPTCHA_MODE=test` for a loopback-only demo. For an
externally reachable deployment, change it to `CAPTCHA_MODE=recaptcha` and
provide a Google reCAPTCHA v2 checkbox `RECAPTCHA_SITE_KEY` and
`RECAPTCHA_SECRET_KEY`. The login endpoint rejects missing/invalid tokens and
returns a service error if verification cannot be configured or reached. Do
not use test mode outside local development.

When upgrading an existing deployment, add `CAPTCHA_MODE` to its existing
`.env` before restarting. Use `test` only for local loopback demonstrations;
otherwise configure `recaptcha` and both keys. The Compose default is
`recaptcha`, and the app fails startup when the required keys are absent.

Windows PowerShell:

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
docker compose ps
curl.exe --fail http://127.0.0.1:8000/health/live
curl.exe --fail http://127.0.0.1:8000/health/ready
```

Ubuntu/Linux:

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
nano .env
install -d -m 700 secrets
if [ ! -f secrets/alertmanager-webhook-token ]; then
  umask 077
  openssl rand -base64 32 > secrets/alertmanager-webhook-token
fi
sudo chown root:10001 secrets/alertmanager-webhook-token
sudo chmod 0440 secrets/alertmanager-webhook-token
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
curl --fail http://127.0.0.1:8000/health/live
curl --fail http://127.0.0.1:8000/health/ready
```

The random webhook token is shared with the app and Alertmanager through a
local Docker secret. Keep `secrets/` private; it is ignored by Git. Bootstrap
the first application administrator after the stack is ready:

```powershell
docker compose exec app python -m app.auth_setup
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
`SESSION_COOKIE_SECURE=true` enables the Secure cookie attribute and is the
Compose default. The copied `.env.example` sets `false` only for the local
loopback HTTP demo; set it to `true` for HTTPS.

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
$env:CAPTCHA_MODE = "test"
$env:SESSION_COOKIE_SECURE = "false"
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m uvicorn app.main:app --reload
```

On Ubuntu/Linux replace the venv creation with
`python3.12 -m venv .venv`, activate using `source .venv/bin/activate`, and
set `export CAPTCHA_MODE=test` and `export SESSION_COOKIE_SECURE=false` for
local development.
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
