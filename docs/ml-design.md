# Anomaly detection design

## Two independent detectors

1. **Threshold rules** compare CPU, memory, and disk percentages against the
   configured limits. They provide a direct explanation such as
   “CPU usage is 96.0%”. Threshold rules continue to work if the model has
   not been trained or cannot be loaded.
2. **Isolation Forest** evaluates the joint five-feature sample against its
   training baseline. It returns an uncalibrated decision score and a
   sample-level outlier classification. The score is **not a probability**,
   and the model does not provide causal or per-feature attribution.

The `detector` value identifies which detector raised a finding. If both a
threshold and the model flag a sample, the threshold explanation is used as
the reported detector and the model score is still included.

## Feature schema and validation

| Feature | Unit | Validation |
|---|---|---|
| `cpu_percent` | percent | finite numeric value from 0 to 100 |
| `memory_percent` | percent | finite numeric value from 0 to 100 |
| `disk_percent` | percent | finite numeric value from 0 to 100 |
| `network_receive_bytes_per_second` | bytes/second | finite numeric value greater than or equal to zero |
| `network_transmit_bytes_per_second` | bytes/second | finite numeric value greater than or equal to zero |

The order in `app/anomaly_detection/core.py` is the model feature schema.
Missing, nonnumeric, NaN, or infinite fields are rejected; the service does
not impute missing live metrics. The live scan endpoint additionally requires
a fresh Prometheus sample for every feature.

## Training, cold start, and artifacts

The trainer requires at least 50 rows, uses 200 Isolation Forest estimators,
contamination `0.05`, random seed `42`, and one worker. The repeatable demo
command creates 1,200 synthetic normal training rows and a separate
synthetic evaluation split. Do not treat its metrics as real-host performance.

```powershell
python -m app.anomaly_detection.train
```

In the Compose app, startup bootstraps the demo model only if the persistent
model artifact is absent. If the file is absent in a native run, status is
`not_trained`, live scans still run threshold rules, and model scores are
omitted. A corrupt or incompatible artifact is reported as unavailable;
threshold rules continue to operate and the API logs a sanitized error type.

Saved artifacts contain an artifact version, exact feature names, scikit-learn
major version, and model object. The loader validates these metadata before
inference. It also accepts legacy Isolation Forest artifacts only when their
feature count and, when available, feature names match the current schema.
`joblib` uses pickle-based serialization: load only artifacts created by a
trusted training process and protect the data volume from untrusted writes.

## Evaluation limits

Synthetic normal/anomaly rows are created by construction, so precision,
recall, F1, and confusion-matrix results only describe that generated split.
No real labeled incident dataset or production baseline has been supplied.

## Resource capacity forecasting

The Infrastructure dashboard's capacity table uses a dependency-free,
ordinary least-squares linear trend for per-target CPU, memory, and disk
utilization. Prometheus range queries collect up to 24 hours of data at
two-minute steps. The model requires at least eight finite, in-range samples
and rejects a latest sample older than ten minutes. Missing values are skipped;
the endpoint reports insufficient or stale data rather than filling gaps.
Forecasts cover six hours and show the observed current value, trend per hour,
an estimate at the horizon, and time to 100% only if the positive trend reaches
that level within the forecast horizon.

When at least ten samples are available, a chronological holdout backtest fits
on the first 80% (at least eight samples) and compares predictions against the
remaining observed samples using mean absolute error. This is a lightweight
historical comparison, not a validation of future or production accuracy. The
model assumes recent linear behavior continues and does not model seasonality,
scheduled jobs, changing workloads, or filesystem changes.

Proactive events are disabled by default. Set
`CAPACITY_FORECAST_WARNINGS_ENABLED=true` to enable the
`POST /api/aiops/forecasts/capacity/warnings` action for ADMIN and OPERATOR
roles. It records a warning anomaly only when the current value is below the
configured threshold and the six-hour estimate reaches or exceeds it. Duplicate
target/metric warnings are suppressed for 24 hours. Forecasting does not
automatically create an incident or perform remediation. Synthetic forecast
tests are separate from evaluation on collected Prometheus metrics; actual
host accuracy has not yet been established.
