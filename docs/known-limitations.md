# Known limitations

- The project is a student-scale local monitoring demonstration, not an
  enterprise-availability or security-certified product.
- Docker Desktop on Windows exposes a Linux VM environment. Node Exporter
  does not measure native Windows host CPU, memory, disk, or network state.
- Endpoint probes use an explicitly configured file-SD list. Only add
  endpoints you are authorized to monitor. There is no API for arbitrary
  target creation; target-file changes require local operator access.
- The default endpoint, `https://example.com`, is an external connectivity
  check. A successful response depends on DNS and outbound network access.
- The FastAPI app, Prometheus, and Alertmanager do not provide user login.
  Compose binds their published ports to loopback; protect all routes with an
  authenticated proxy/IAP/VPN before any remote exposure. Grafana has local
  admin authentication.
- The Alertmanager webhook trusts the private Compose network and has no
  request authentication; never expose it publicly.
- Isolation Forest is trained on synthetic demonstration data unless an
  operator supplies a suitable real baseline. Scores are not probabilities,
  model explanations are sample-level, and results do not prove root cause.
- Missing and stale metrics are not imputed. Live anomaly scans return an
  explicit unavailable response when required measurements are missing.
- The optional GCP deployment guide is documentation only. No GCP resources
  have been provisioned or verified.
- SQLite and a single host are suitable for coursework and local demos, not
  high-volume multi-user workloads or high availability.
