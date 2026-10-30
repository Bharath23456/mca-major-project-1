import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    prometheus_url: str = os.getenv("PROMETHEUS_URL", "http://127.0.0.1:9090").rstrip("/")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./cloudnetops.db")
    model_path: str = os.getenv("MODEL_PATH", "data/isolation_forest.joblib")
    blackbox_targets_path: str = os.getenv(
        "BLACKBOX_TARGETS_PATH", "monitoring/prometheus/blackbox_targets.json"
    )
    cpu_threshold_percent: float = float(os.getenv("CPU_THRESHOLD_PERCENT", "85"))
    memory_threshold_percent: float = float(os.getenv("MEMORY_THRESHOLD_PERCENT", "90"))
    disk_threshold_percent: float = float(os.getenv("DISK_THRESHOLD_PERCENT", "90"))


settings = Settings()
