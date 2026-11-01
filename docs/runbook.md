# Local runbook

This runbook is for the local Compose demonstration. It is not a production
incident-response procedure.

## Start, verify, and stop

1. Copy `.env.example` to `.env` and set a unique Grafana password. Generate
   the ignored `secrets/alertmanager-webhook-token` as described in
   [setup.md](setup.md); Compose will not start without it.
2. Start the stack and wait for health checks:

   ```powershell
   docker compose up --build -d --wait --wait-timeout 180
   docker compose ps --all
   ```

3. Bootstrap the initial app administrator if this is a new installation:

   ```powershell
   docker compose exec app python -m app.auth_setup
   ```

4. Check health and telemetry:

   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/health/live
   Invoke-RestMethod http://127.0.0.1:8000/health/ready
   Invoke-RestMethod http://127.0.0.1:8000/api/v1/overview
   Invoke-RestMethod http://127.0.0.1:8000/api/v1/targets
   ```

5. Open the dashboard `http://127.0.0.1:8000/`, Grafana
   `http://127.0.0.1:3000/`, Prometheus `http://127.0.0.1:9090/`, or
   Alertmanager `http://127.0.0.1:9093/`. All are loopback-only.
6. Stop without deleting history:

   ```powershell
   docker compose down
   ```

## Common conditions

### Readiness is degraded

`/health/live` checks only the API process. `/health/ready` also checks the
database and Prometheus query API. Review service state and logs:

```powershell
docker compose ps --all
docker compose logs --tail 100 app prometheus
```

Do not treat liveness alone as evidence that metrics are available.

### A Prometheus target is down

Open Prometheus **Status → Targets** and inspect the target error. Confirm
that the relevant container is running and that the configured service name
and port match `monitoring/prometheus/prometheus.yml`. For the Blackbox
target, also inspect `docker compose logs --tail 100 blackbox-exporter` and
verify that the explicitly configured endpoint is authorized and reachable.

### Anomaly scan returns HTTP 503

The live scanner needs a fresh sample for all five documented features.
Check the `reason` and `stale` fields in `/api/v1/overview`, then confirm the
Node Exporter scrape target is up. Do not replace missing values with demo
numbers. If data are unavailable, use `/api/v1/anomalies/score` only for an
explicitly labeled sample demonstration.

### Review alert or anomaly history

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/alerts?limit=50&offset=0'
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/anomalies?limit=50&offset=0'
```

Prometheus alert rules have sustained `for` durations to reduce noise.
Alertmanager groups and deduplicates by alert name and instance and forwards
both firing and resolved states to the private API webhook. The webhook must
not be exposed through an internet-facing reverse proxy.

## Backup and restore

SQLite events and the model share the `app-data` named volume; Prometheus,
Grafana, and Alertmanager each use their own named volume. Stop the stack
before making a consistent backup. List actual volume names before copying:

```powershell
docker compose down
docker volume ls
```

Use an approved local archive tool or a trusted temporary container to archive
each named volume to a protected backup directory. Protect the archives: they
contain monitoring history and the model artifact. To restore, stop Compose,
verify the chosen backup and destination volume, restore only into the
intended named volume, and then start the stack and check health and stored
data. Test this procedure on a separate demo copy first.

`docker compose down -v` permanently removes the named data volumes. Do not
use it as a normal stop, restart, or rollback command.

## Demo-safe model exercise

The live scan reads real Prometheus data and can persist a finding. To train
and evaluate the deterministic synthetic model separately, run:

```powershell
docker compose exec app python -m app.anomaly_detection.train
```

Clearly identify all generated training/evaluation samples as synthetic in a
presentation. No infrastructure changes are performed by the detector.

## Alert runbooks

### Monitoring target unavailable

1. Check whether the named Compose service is running.
2. Inspect its logs and Prometheus **Status → Targets**.
3. Check service DNS/network configuration and exporter listening port.
4. Restore the service only after correcting the observed cause; this project
   does not automatically restart external infrastructure.

### Anomaly finding

1. Read the detector name, severity, score, timestamp, and observed features.
2. Confirm that the data are current and that the score is not a probability.
3. Compare with Prometheus history and the threshold rules.
4. Treat the result as a prompt for investigation, not a confirmed incident.
