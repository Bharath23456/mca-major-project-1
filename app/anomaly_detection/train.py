import json

from app.anomaly_detection.core import (
    evaluate_model,
    make_synthetic_data,
    save_model,
    train_model,
)
from app.settings import settings


def main() -> None:
    training_samples, _ = make_synthetic_data(normal_count=1200, anomaly_count=0, seed=17)
    model = train_model(training_samples, contamination=0.05)

    evaluation_samples, labels = make_synthetic_data(normal_count=400, anomaly_count=100, seed=73)
    evaluation = evaluate_model(model, evaluation_samples, labels)
    save_model(model)
    print(
        json.dumps(
            {
                "model_path": settings.model_path,
                "training_samples": len(training_samples),
                "evaluation": evaluation,
                "note": (
                    "Metrics are calculated on deterministic synthetic data, "
                    "not live infrastructure."
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
