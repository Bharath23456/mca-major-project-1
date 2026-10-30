# Demonstration script

## Before the presentation

1. Use a Linux host or VM for representative Node Exporter metrics. On
   Windows Docker Desktop, explain that the exporter sees the Docker Linux
   environment, not the native Windows host.
2. Copy `.env.example` to `.env`, set a unique Grafana password, and start the
   stack with the commands below. The first launch requires Docker Hub image
   downloads.
3. Confirm the application health endpoint and Prometheus targets. Do not
   claim live metrics or alerts unless those checks succeed.

## Start the application

Windows PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
curl.exe --fail http://127.0.0.1:8000/health
```

Ubuntu/Linux:

```bash
if [ ! -f .env ]; then cp .env.example .env; fi
nano .env
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
curl --fail http://127.0.0.1:8000/health
```

Expected health response:

```json
{"status":"ok"}
```

## Explain and demonstrate

1. Open the dashboard and point out telemetry status, units, timestamps,
   endpoint status, target status, alert history, and anomaly history.
2. Open Prometheus **Status → Targets** and verify configured targets are
   `UP`. If a target is missing or stale, explain that it is displayed as
   such rather than replaced with fake measurements.
3. Open Grafana and select **CloudNetOps-AI Infrastructure**.
4. Open `/docs` and explain the read-only monitoring summary/history APIs and
   input-validated anomaly score API.
5. Use **Analyze current metrics** only after fresh Prometheus host samples are
   available. The operation reads current metrics and stores an event only
   when the configured rules or trained model flag the sample.
6. To demonstrate the model process separately, run
   `python -m app.anomaly_detection.train` from the repository root and show
   the generated evaluation metrics. State that the data and metrics are
   synthetic.
7. Show the GitHub Actions CI and explain that GCP deployment is manual,
   separately protected, and not configured until the required Workload
   Identity values are supplied.

## End the demonstration

Stop containers while preserving local history:

```powershell
docker compose down
```

`docker compose down -v` deletes persistent local state and should not be used
unless a deliberate clean reset is part of the demo.

In the current development environment, the standalone API container, health
route, configuration validation, and model startup were verified. Integrated
monitoring services were not started because Docker could not resolve the
Docker Hub CDN hostname; present that as an environment limitation, not as a
successful integration test.
