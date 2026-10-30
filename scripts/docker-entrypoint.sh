#!/bin/sh
set -eu

if [ ! -s "${MODEL_PATH:-data/isolation_forest.joblib}" ]; then
    python -m app.anomaly_detection.train
fi

exec "$@"
