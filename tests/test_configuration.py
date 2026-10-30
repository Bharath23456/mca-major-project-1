import json
from pathlib import Path

from app.configuration import validate_probe_targets


def test_probe_target_validation_accepts_http_and_https(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "targets.json"
    config_file.write_text(
        json.dumps(
            [
                {
                    "targets": [
                        "https://example.com/health",
                        "http://localhost:8000/health",
                    ],
                    "labels": {"environment": "test"},
                }
            ]
        ),
        encoding="utf-8",
    )

    count, errors = validate_probe_targets(config_file)

    assert count == 2
    assert errors == []


def test_probe_target_validation_rejects_embedded_credentials(
    tmp_path: Path,
) -> None:
    config_file = tmp_path / "targets.json"
    config_file.write_text(
        json.dumps([{"targets": ["https://user:password@example.com"]}]),
        encoding="utf-8",
    )

    count, errors = validate_probe_targets(config_file)

    assert count == 1
    assert any("embedded credentials" in error for error in errors)


def test_probe_target_validation_reports_invalid_json(tmp_path: Path) -> None:
    config_file = tmp_path / "targets.json"
    config_file.write_text("{", encoding="utf-8")

    count, errors = validate_probe_targets(config_file)

    assert count == 0
    assert any("invalid JSON" in error for error in errors)
