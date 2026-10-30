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
