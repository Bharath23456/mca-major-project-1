from datetime import UTC, datetime

from sqlalchemy import create_engine, inspect, select

from app.database_migrations import migrate_database
from app.models import AlertEvent, AnomalyEvent


def test_upgrade_and_rollback_preserve_existing_monitoring_data(tmp_path) -> None:
    database_path = (tmp_path / "existing.db").as_posix()
    database_url = f"sqlite:///{database_path}"
    engine = create_engine(database_url)
    AlertEvent.__table__.create(engine)
    AnomalyEvent.__table__.create(engine)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        connection.execute(
            AlertEvent.__table__.insert().values(
                fingerprint="legacy-alert",
                alertname="LegacyAlert",
                status="firing",
                severity="warning",
                instance="node-a",
                summary="preserve this alert",
                description="",
                starts_at=now.isoformat(),
                ends_at="",
                labels_json="{}",
                updated_at=now,
            )
        )
        connection.execute(
            AnomalyEvent.__table__.insert().values(
                created_at=now,
                detector="rule",
                severity="warning",
                score=None,
                explanation="preserve this anomaly",
                metrics_json="{}",
            )
        )

    migrate_database(database_url)
    assert "users" in inspect(engine).get_table_names()
    assert "incident_events" in inspect(engine).get_table_names()

    migrate_database(database_url, revision="base")
    with engine.connect() as connection:
        assert connection.scalar(
            select(AlertEvent.id).where(AlertEvent.fingerprint == "legacy-alert")
        ) is not None
        assert connection.scalar(
            select(AnomalyEvent.id).where(AnomalyEvent.explanation == "preserve this anomaly")
        ) is not None

    migrate_database(database_url)
    assert "users" in inspect(engine).get_table_names()
    engine.dispose()
