# Security notes

## Implemented safeguards

- `.env` and local data files are excluded by `.gitignore`; `.env.example`
  contains non-secret placeholders only.
- App, Prometheus, Grafana, and Alertmanager host ports bind to loopback in
  Compose. Exporters are not published on the host.
- The application container runs as a non-root user and has a health check.
- The app container has a read-only root filesystem, a bounded `/tmp`,
  dropped Linux capabilities, and `no-new-privileges`; Node Exporter and
  Blackbox Exporter also run read-only without added capabilities.
- Prometheus is read-only from the application: metric APIs issue queries, not
  configuration changes.
- Metric request values are validated with Pydantic. Training is a local CLI
  operation; there is no public training or configuration-mutation endpoint.
- Ruff's Bandit-derived security rules are part of the Python lint set, and
  CI runs `pip-audit` against runtime and development dependencies.
- Probe targets are an operator-managed file-SD allowlist. The API does not
  accept arbitrary probe URLs. Probes use ordinary HTTP GET requests and do
  not scan arbitrary networks.
- Runtime and development direct dependencies are pinned to versions tested
  by the project. Container images use explicit version tags.
- Application dependency-error logs use JSON records and report exception
  types, not raw Prometheus URLs or credentials.
- GCP is optional; no credentials or cloud resource operations are included
  in the local setup.

## Deployment constraints

- The Alertmanager webhook does not include authentication and is intended
  only for the private Compose network. Do not forward
  `/api/v1/alerts/webhook` through an internet-facing reverse proxy.
- The application has no built-in user login. If the dashboard/API is
  reachable beyond a trusted local machine, protect it with IAP, VPN, or an
  authenticated HTTPS reverse proxy before exposing it.
- Prometheus and Alertmanager have no login configured here. Keep their web
  interfaces private; access remote administration through a VPN, IAP, or SSH
  tunnel.
- Compose requires `GRAFANA_ADMIN_PASSWORD`; use a unique value in the
  untracked `.env`. Do not reuse a school, personal, or cloud password.
- Node Exporter requires read-only host filesystem mounts and host PID
  visibility for full Linux host telemetry. Do not publish its port publicly.
- SQLite persistence and one VM are not high-availability or production-grade
  controls. Back up the Compose volumes before upgrades or experiments.
- For GCP, permit only required ingress, restrict SSH to an administrator IP
  or use IAP, configure HTTPS, and grant least-privilege IAM. Follow
  [deployment.md](deployment.md); cloud commands there are examples and have
  not been executed.

## Safe scope

The system detects and records signals; it has no autonomous infrastructure
write access and does not attempt self-healing. An anomaly is not proof of an
attack, outage, or root cause.

## Threat model and remaining controls

| Threat | Current mitigation | Remaining limitation |
|---|---|---|
| Exposed dashboards and metrics | Published management ports bind to loopback; Grafana requires a configured password. | FastAPI, Prometheus, and Alertmanager have no built-in authentication. Put every remotely reachable route behind authenticated access control. |
| Secret leakage | `.env` is ignored; the example file contains placeholders; CI has no cloud keys. | Local backups and shell history must still be protected by the operator. |
| Malicious probe target | Only operator-edited file-SD targets are probed; scheme and embedded credentials are validated; no target-mutation API exists. | The operator must authorize targets and avoid internal metadata/private endpoints. DNS-resolved address ranges are not dynamically allowlisted. |
| Dependency compromise | Direct dependencies are pinned and CI runs Ruff security rules and `pip-audit`. | Review and update pinned dependencies regularly; an audit is not a security certification. |
| Unauthenticated webhook | Alertmanager webhook is only on the private Compose network, not published as a host port. | Do not expose the route through a public reverse proxy or shared untrusted network. |
| Untrusted model artifact | Loader validates artifact version, feature schema, and scikit-learn major version. | `joblib` is pickle-based; only load artifacts created by a trusted training process. |
