# Presentation slide outline

The outline is factual to the current implementation and can be copied into
the college's presentation template.

The supplied `Contents.pptx` describes report contents rather than a branded
presentation theme. Student/guide details and verified literature
references remain placeholders. The eight provided titles are not sufficient
to support final scholarly citations.

## Slide 1 — Title

- CloudNetOps-AI
- An Intelligent Cloud Infrastructure and Network Monitoring System with
  Automated CI/CD and Anomaly Detection
- K R Bharath — 4UB25MC047
- MCA, UBDT College of Engineering
- Project guide: Srinivasulu M
- Academic year: 2026-27

## Slide 2 — Problem and motivation

- Host metrics, endpoint status, alert state, and unusual patterns are often
  reviewed in separate tools.
- Students need a low-cost local environment to demonstrate a complete
  observability workflow.
- The project reports signals for investigation; it does not promise automatic
  root-cause analysis.

## Slide 3 — Objectives and scope

- Collect available Linux host and authorized HTTP/HTTPS endpoint metrics.
- Visualize current status and historical trends.
- Configure alert rules and persist alert history.
- Compare explicit thresholds with Isolation Forest scoring.
- Run tests and CI without requiring paid AI services.

## Slide 4 — Architecture

- Include the Mermaid diagram from `architecture.md`.
- Describe the data flow from exporters to Prometheus, Grafana, Alertmanager,
  FastAPI, and SQLite.

## Slide 5 — Technology choices

- FastAPI and Pydantic for validated application APIs.
- Prometheus and exporters for metrics; Grafana for infrastructure panels.
- Alertmanager for notification routing.
- SQLAlchemy/SQLite for local event persistence.
- pandas, NumPy, and scikit-learn for reproducible model training/evaluation.
- HTML/CSS/JavaScript dashboard to avoid an unnecessary frontend framework.

## Slide 6 — Monitoring and dashboard

- Show the actual running dashboard and Grafana dashboard when available.
- Explain CPU, memory, disk, network, uptime, endpoint, and target status
  panels.
- Explain timestamps, units, and stale/missing data states.

## Slide 7 — Alerting and event history

- Summarize CPU, memory, disk, availability, latency, and target-unavailable
  rules.
- Explain their `for` durations and severity labels.
- Explain the private Alertmanager webhook and SQLite history.

## Slide 8 — Anomaly detection

- Show five input features and input validation.
- Explain the threshold baseline and Isolation Forest sample-level score.
- State that Isolation Forest does not provide per-feature attribution.
- Explain that anomalies are investigation signals, not confirmed incidents.

## Slide 9 — CI/CD and deployment

- CI checks lint, tests, Compose configuration, Prometheus rules, JSON, and
  Docker build.
- Optional manual GCP deployment uses Workload Identity Federation and an
  existing VM.
- No production deployment or cloud resource creation has been performed.

## Slide 10 — Test results

- 18 unit/API tests passed; the run reported one Starlette/httpx deprecation
  warning.
- App image built and its container reached Docker health `healthy`.
- Synthetic test split: precision 0.8475, recall 1.0000, F1 0.9174,
  confusion matrix `[[382, 18], [0, 100]]`.
- Label this model evaluation as synthetic-only.

## Slide 11 — Limitations and future work

- Monitoring stack integration needs a successful image pull and Linux-host
  validation.
- Docker Desktop on Windows does not provide native Windows host telemetry.
- Synthetic data does not establish real-world model quality.
- Add user authentication and operational backups before any public deployment.
- Integrate real labelled samples and supplied literature after review.

## Slide 12 — Demonstration and conclusion

- Follow `demo_script.md`.
- Distinguish implemented, locally tested, blocked, and optional features.
- Close with the verified project limitations and next steps.

## Slide 13 — References and acknowledgements

- Add only sources whose authorship, publication details, and stable links
  have been verified.
- Use the numbered citation style from the supplied VTU-formatting notes,
  after verifying its details against the current circular.
- The eight currently supplied literature entries are title-and-topic notes,
  not complete references.
