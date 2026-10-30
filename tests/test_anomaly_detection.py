import numpy as np
import pytest

from app.anomaly_detection.core import (
    FEATURES,
    detect_metrics,
    evaluate_model,
    load_model,
    make_synthetic_data,
    save_model,
    train_model,
)


def test_training_rejects_small_dataset() -> None:
    samples, _ = make_synthetic_data(normal_count=49, anomaly_count=0)

    with pytest.raises(ValueError, match="At least 50"):
        train_model(samples)


def test_training_rejects_non_finite_samples() -> None:
    samples, _ = make_synthetic_data(normal_count=60, anomaly_count=0)
    samples.loc[0, "cpu_percent"] = np.nan

    with pytest.raises(ValueError, match="finite numeric"):
        train_model(samples)


def test_model_artifact_round_trips_with_feature_schema(tmp_path) -> None:
    training, _ = make_synthetic_data(normal_count=60, anomaly_count=0)
    model_path = tmp_path / "model.joblib"

    save_model(train_model(training), model_path)
    loaded = load_model(model_path)

    assert loaded is not None
    assert list(loaded.feature_names_in_) == list(FEATURES)


def test_model_loader_rejects_corrupted_artifact(tmp_path) -> None:
    model_path = tmp_path / "model.joblib"
    model_path.write_bytes(b"not a valid joblib artifact")

    with pytest.raises((ValueError, EOFError)):
        load_model(model_path)


def test_model_evaluation_returns_measured_classification_results() -> None:
    training, _ = make_synthetic_data(normal_count=500, anomaly_count=0, seed=13)
    evaluation, labels = make_synthetic_data(normal_count=200, anomaly_count=50, seed=99)

    results = evaluate_model(train_model(training), evaluation, labels)

    assert 0 <= results["precision"] <= 1
    assert 0 <= results["recall"] <= 1
    assert 0 <= results["f1_score"] <= 1
    assert sum(map(sum, results["confusion_matrix"])) == len(labels)
    assert results["sample_count"] == 250


def test_rule_detection_explains_threshold_measurements() -> None:
    normal = dict(zip(FEATURES, [40, 50, 60, 1000, 1000], strict=True))
    normal["cpu_percent"] = 96

    result = detect_metrics(normal)

    assert result.is_anomaly
    assert result.detector == "rule"
    assert result.severity == "critical"
    assert "CPU usage is 96.0%" in result.explanation


def test_detection_rejects_out_of_range_percentages() -> None:
    invalid = dict(zip(FEATURES, [101, 50, 60, 1000, 1000], strict=True))

    with pytest.raises(ValueError, match="between 0 and 100"):
        detect_metrics(invalid)
