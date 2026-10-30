import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def validate_probe_targets(path: str | Path) -> tuple[int, list[str]]:
    config_path = Path(path)
    try:
        targets_config: Any = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return 0, [f"Endpoint target file not found: {config_path}."]
    except json.JSONDecodeError as error:
        return 0, [f"Endpoint target file contains invalid JSON at line {error.lineno}."]

    if not isinstance(targets_config, list):
        return 0, ["Endpoint target configuration must be a JSON array."]

    endpoint_count = 0
    errors: list[str] = []
    for group_index, group in enumerate(targets_config):
        if not isinstance(group, dict) or not isinstance(group.get("targets"), list):
            errors.append(f"Target group {group_index + 1} must contain a targets array.")
            continue
        if not group["targets"]:
            errors.append(f"Target group {group_index + 1} has no endpoints.")
        for target in group["targets"]:
            endpoint_count += 1
            if not isinstance(target, str):
                errors.append(f"Endpoint {endpoint_count} must be a string URL.")
                continue
            parsed = urlsplit(target)
            try:
                _ = parsed.port
            except ValueError:
                errors.append(f"Endpoint {endpoint_count} has an invalid port.")
                continue
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                errors.append(
                    f"Endpoint {endpoint_count} must be an HTTP or HTTPS URL with a host."
                )
            elif parsed.username is not None or parsed.password is not None:
                errors.append(f"Endpoint {endpoint_count} must not contain embedded credentials.")

        labels = group.get("labels", {})
        if not isinstance(labels, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in labels.items()
        ):
            errors.append(f"Target group {group_index + 1} labels must be string pairs.")

    return endpoint_count, errors
