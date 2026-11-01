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
4. Bootstrap the initial administrator with the local prompt. Do not use a
   default/demo password.

## Start the application

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
curl.exe --fail http://127.0.0.1:8000/health
docker compose exec app python -m app.auth_setup
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
curl --fail http://127.0.0.1:8000/health
docker compose exec app python -m app.auth_setup
```

Expected health response:

```json
{"status":"ok"}
```

## Explain and demonstrate

1. Sign in as the bootstrapped administrator. Explain that sessions are
   server-side and role checks are enforced by the API. The login page also
   offers public self-registration, which creates VIEWER accounts only.
2. From **User management**, create an OPERATOR account. To demonstrate
   registration, sign out, create a separate account using **Create a viewer
   account**, then sign in with its username/email and chosen password. Compare
   the operator and viewer permissions.
3. As an authenticated user, point out telemetry status, units, timestamps,
   endpoint status, target status, alert history, and anomaly history.
4. Open Prometheus **Status → Targets** and verify configured targets are
   `UP`. If a target is missing or stale, explain that it is displayed as
   such rather than replaced with fake measurements.
5. Open **AI anomalies** and explain the separate threshold/Isolation Forest
   findings, model status, and evidence-backed suggestions. Anomaly scores are
   not probabilities and suggestions are not confirmed causes.
6. Open **Incidents** to show alert/anomaly correlation. As an operator,
   assign an active operator, add a note, acknowledge an open incident, and
   resolve it. Explain that these actions are audited and never restart or
   repair infrastructure.
7. As an administrator, inspect **Audit history** and the database/API docs.
8. Open Grafana and select **CloudNetOps-AI Infrastructure**.
9. Open `/docs` and explain the role-protected APIs and CSRF requirements.
10. Use **Analyze current metrics** only after fresh Prometheus host samples are
   available. The operation reads current metrics and stores an event only
   when the configured rules or trained model flag the sample.
11. To demonstrate the model process separately, run
   `python -m app.anomaly_detection.train` from the repository root and show
   the generated evaluation metrics. State that the data and metrics are
   synthetic.
12. Show the GitHub Actions CI and explain that GCP deployment is manual,
   separately protected, and not configured until the required Workload
   Identity values are supplied.

## End the demonstration

Stop containers while preserving local history:

```powershell
docker compose down
```

`docker compose down -v` deletes persistent local state and should not be used
unless a deliberate clean reset is part of the demo.

Report the actual checks performed for the current build. Do not reuse
historical screenshots, metrics, or integration results as if captured from
the current run. If Compose services could not start, state the specific
environment limitation rather than presenting an integration test as passed.
