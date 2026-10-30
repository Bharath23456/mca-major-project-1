from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

from app.settings import settings

FEATURES = (
    "cpu_percent",
    "memory_percent",
    "disk_percent",
    "network_receive_bytes_per_second",
    "network_transmit_bytes_per_second",
)
MODEL_ARTIFACT_VERSION = 1


@dataclass(frozen=True)
class Detection:
    is_anomaly: bool
    detector: str
    severity: str
    score: float | None
    explanation: str
    metrics: dict[str, float]


def _validate_frame(samples: pd.DataFrame) -> pd.DataFrame:
    missing = [feature for feature in FEATURES if feature not in samples.columns]
    if missing:
        raise ValueError(f"Missing required metric features: {', '.join(missing)}")
    frame = samples.loc[:, FEATURES].copy()
    if frame.empty:
        raise ValueError("At least one metric sample is required.")
    frame = frame.apply(pd.to_numeric, errors="coerce")
    if frame.isna().any().any() or not np.isfinite(frame.to_numpy()).all():
        raise ValueError("Metric samples must contain finite numeric values.")
    for feature in FEATURES[:3]:
        if ((frame[feature] < 0) | (frame[feature] > 100)).any():
            raise ValueError(f"{feature} must be between 0 and 100.")
    if (frame.loc[:, FEATURES[3:]] < 0).any().any():
        raise ValueError("Network rates cannot be negative.")
    return frame


def make_synthetic_data(
    normal_count: int = 1000, anomaly_count: int = 250, seed: int = 42
) -> tuple[pd.DataFrame, np.ndarray]:
    """Create deterministic labelled data for repeatable evaluation only."""
    rng = np.random.default_rng(seed)

    def normal_rows(count: int) -> np.ndarray:
        cpu = rng.normal(32, 12, count).clip(1, 75)
        memory = rng.normal(48, 14, count).clip(10, 82)
        disk = rng.normal(55, 12, count).clip(15, 85)
        receive = rng.lognormal(13.2, 0.8, count).clip(1_000, 2_000_000)
        transmit = rng.lognormal(12.8, 0.8, count).clip(1_000, 2_000_000)
        return np.column_stack((cpu, memory, disk, receive, transmit))

    normal = normal_rows(normal_count)
    if anomaly_count:
        anomaly = normal_rows(anomaly_count)
        anomaly[:, 0] = rng.uniform(88, 100, anomaly_count)
        anomaly[:, 1] = rng.uniform(91, 100, anomaly_count)
        anomaly[:, 3:] *= rng.uniform(5, 15, (anomaly_count, 2))
        combined = np.vstack((normal, anomaly))
        labels = np.concatenate(
            (np.zeros(normal_count, dtype=int), np.ones(anomaly_count, dtype=int))
        )
    else:
        combined = normal
        labels = np.zeros(normal_count, dtype=int)
    frame = pd.DataFrame(combined, columns=FEATURES)
    return frame, labels


def train_model(samples: pd.DataFrame, contamination: float = 0.05) -> IsolationForest:
    frame = _validate_frame(samples)
    if len(frame) < 50:
        raise ValueError("At least 50 historical normal samples are required to train the model.")
    if not 0 < contamination <= 0.5:
        raise ValueError("contamination must be greater than 0 and at most 0.5.")
    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=42,
        n_jobs=1,
    )
    model.fit(frame)
    return model


def save_model(model: IsolationForest, path: str | Path = settings.model_path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_suffix(destination.suffix + ".tmp")
    joblib.dump(
        {
            "artifact_version": MODEL_ARTIFACT_VERSION,
            "feature_schema": list(FEATURES),
            "scikit_learn_version": sklearn.__version__,
            "model": model,
        },
        temporary_path,
    )
    temporary_path.replace(destination)


def load_model(path: str | Path = settings.model_path) -> IsolationForest | None:
    model_path = Path(path)
    if not model_path.is_file():
        return None
    try:
        artifact: Any = joblib.load(model_path)
    except (
        OSError,
        EOFError,
        ValueError,
        pickle.UnpicklingError,
        ImportError,
        AttributeError,
        KeyError,
    ) as error:
        raise ValueError("Model artifact is corrupted or unreadable.") from error
    if isinstance(artifact, IsolationForest):
        feature_names = getattr(artifact, "feature_names_in_", None)
        if feature_names is not None and list(feature_names) != list(FEATURES):
            raise ValueError(
                "Legacy model feature schema does not match the current feature schema."
            )
        if getattr(artifact, "n_features_in_", None) != len(FEATURES):
            raise ValueError(
                "Legacy model feature count does not match the current feature schema."
            )
        return artifact

    if not isinstance(artifact, dict):
        raise ValueError(f"Model file {model_path} does not contain a supported model artifact.")
    if artifact.get("artifact_version") != MODEL_ARTIFACT_VERSION:
        raise ValueError("Model artifact version is not supported.")
    if artifact.get("feature_schema") != list(FEATURES):
        raise ValueError("Model artifact feature schema does not match the current schema.")
    artifact_sklearn_version = artifact.get("scikit_learn_version")
    if (
        not isinstance(artifact_sklearn_version, str)
        or artifact_sklearn_version.split(".", maxsplit=1)[0]
        != sklearn.__version__.split(".", maxsplit=1)[0]
    ):
        raise ValueError("Model artifact was created with an incompatible scikit-learn version.")
    model = artifact.get("model")
    if not isinstance(model, IsolationForest):
        raise ValueError("Model artifact does not contain an IsolationForest model.")
    return model


def evaluate_model(
    model: IsolationForest, samples: pd.DataFrame, labels: np.ndarray
) -> dict[str, Any]:
    frame = _validate_frame(samples)
    if len(frame) != len(labels):
        raise ValueError("Each evaluation sample must have exactly one label.")
    predictions = model.predict(frame)
    predicted_labels = (predictions == -1).astype(int)
    return {
        "precision": float(precision_score(labels, predicted_labels, zero_division=0)),
        "recall": float(recall_score(labels, predicted_labels, zero_division=0)),
        "f1_score": float(f1_score(labels, predicted_labels, zero_division=0)),
        "confusion_matrix": confusion_matrix(labels, predicted_labels, labels=[0, 1]).tolist(),
        "sample_count": len(frame),
    }


def detect_metrics(metrics: dict[str, float], model: IsolationForest | None = None) -> Detection:
    frame = _validate_frame(pd.DataFrame([metrics]))
    values = {feature: float(frame.iloc[0][feature]) for feature in FEATURES}
    rule_reasons: list[str] = []
    if values["cpu_percent"] >= settings.cpu_threshold_percent:
        rule_reasons.append(f"CPU usage is {values['cpu_percent']:.1f}%")
    if values["memory_percent"] >= settings.memory_threshold_percent:
        rule_reasons.append(f"memory usage is {values['memory_percent']:.1f}%")
    if values["disk_percent"] >= settings.disk_threshold_percent:
        rule_reasons.append(f"disk usage is {values['disk_percent']:.1f}%")

    score: float | None = None
    model_anomaly = False
    if model is not None:
        score = float(-model.decision_function(frame)[0])
        model_anomaly = int(model.predict(frame)[0]) == -1

    if rule_reasons:
        detector = "rule"
        severity = (
            "critical"
            if any(
                "CPU" in reason
                and values["cpu_percent"] >= 95
                or "memory" in reason
                and values["memory_percent"] >= 97
                or "disk" in reason
                and values["disk_percent"] >= 97
                for reason in rule_reasons
            )
            else "warning"
        )
        explanation = "Threshold exceeded: " + "; ".join(rule_reasons) + "."
    elif model_anomaly:
        detector = "isolation_forest"
        severity = "warning"
        explanation = (
            "The joint metric pattern differs from the training baseline. "
            "Isolation Forest scores the sample as a whole and does not provide "
            "per-feature attribution."
        )
    else:
        detector = "none"
        severity = "info"
        explanation = "No configured rule threshold or model anomaly was detected."

    return Detection(
        is_anomaly=bool(rule_reasons or model_anomaly),
        detector=detector,
        severity=severity,
        score=score,
        explanation=explanation,
        metrics=values,
    )
