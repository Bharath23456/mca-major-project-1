import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.auth import hash_password
from app.database import SessionLocal
from app.incidents import correlate_alert_event, create_incident_from_anomaly
from app.main import app
from app.models import (
    AlertEvent,
    AnomalyEvent,
    AuditLog,
    Incident,
    IncidentEvent,
    IncidentNote,
    User,
    UserSession,
)


@contextmanager
def logged_in_user(role: str) -> Iterator[tuple[TestClient, int]]:
    client = TestClient(app)
    with client:
        suffix = uuid4().hex[:12]
        with SessionLocal() as session:
            user = User(
                username=f"incident-{suffix}",
                email=f"incident-{suffix}@example.test",
                password_hash=hash_password("incident-test-credential-2026"),
                role=role,
                is_active=True,
            )
            session.add(user)
            session.commit()
            user_id = user.id
            username = user.username

        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": "incident-test-credential-2026"},
        )
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield client, user_id

        with SessionLocal() as session:
            session.execute(delete(UserSession).where(UserSession.user_id == user_id))
            session.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


def _cleanup_incidents(
    incident_ids: list[int],
    alert_ids: list[int] | None = None,
    anomaly_ids: list[int] | None = None,
) -> None:
    with SessionLocal() as session:
        session.execute(delete(IncidentNote).where(IncidentNote.incident_id.in_(incident_ids)))
        session.execute(delete(IncidentEvent).where(IncidentEvent.incident_id.in_(incident_ids)))
        session.execute(delete(AuditLog).where(AuditLog.incident_id.in_(incident_ids)))
        session.execute(delete(Incident).where(Incident.id.in_(incident_ids)))
        if alert_ids:
            session.execute(delete(AlertEvent).where(AlertEvent.id.in_(alert_ids)))
        if anomaly_ids:
            session.execute(delete(AnomalyEvent).where(AnomalyEvent.id.in_(anomaly_ids)))
        session.commit()


def test_related_alerts_correlate_but_unrelated_targets_and_families_do_not() -> None:
    timestamp = datetime.now(UTC)
    alert_ids: list[int] = []
    incident_ids: list[int] = []
    with TestClient(app), SessionLocal() as session:
        cpu = AlertEvent(
            fingerprint=f"cpu-{uuid4().hex}",
            alertname="HighCPUUsage",
            status="firing",
            severity="critical",
            instance="api-1",
            summary="CPU is high",
            starts_at=timestamp.isoformat(),
            updated_at=timestamp,
        )
        latency = AlertEvent(
            fingerprint=f"latency-{uuid4().hex}",
            alertname="HighResponseLatency",
            status="firing",
            severity="warning",
            instance="api-1",
            summary="Response time increased",
            starts_at=(timestamp + timedelta(seconds=2)).isoformat(),
            updated_at=timestamp + timedelta(seconds=2),
        )
        unrelated_target = AlertEvent(
            fingerprint=f"cpu-other-{uuid4().hex}",
            alertname="HighCPUUsage",
            status="firing",
            severity="critical",
            instance="worker-2",
            summary="Worker CPU is high",
            starts_at=(timestamp + timedelta(seconds=3)).isoformat(),
            updated_at=timestamp + timedelta(seconds=3),
        )
        unrelated_family = AlertEvent(
            fingerprint=f"memory-{uuid4().hex}",
            alertname="HighMemoryUsage",
            status="firing",
            severity="warning",
            instance="api-1",
            summary="Memory is high",
            starts_at=(timestamp + timedelta(seconds=4)).isoformat(),
            updated_at=timestamp + timedelta(seconds=4),
        )
        session.add_all([cpu, latency, unrelated_target, unrelated_family])
        session.flush()
        alert_ids = [cpu.id, latency.id, unrelated_target.id, unrelated_family.id]
        first_incident = correlate_alert_event(session, cpu, previous_status=None)
        related_incident = correlate_alert_event(session, latency, previous_status=None)
        target_incident = correlate_alert_event(
            session, unrelated_target, previous_status=None
        )
        family_incident = correlate_alert_event(
            session, unrelated_family, previous_status=None
        )
        assert first_incident is not None
        assert related_incident is not None
        assert related_incident.id == first_incident.id
        assert target_incident is not None and target_incident.id != first_incident.id
        assert family_incident is not None and family_incident.id != first_incident.id
        correlate_alert_event(session, cpu, previous_status="firing")
        session.commit()
        incident_ids = [first_incident.id, target_incident.id, family_incident.id]
        link_count = session.scalar(
            select(func.count()).select_from(IncidentEvent).where(
                IncidentEvent.incident_id.in_(incident_ids)
            )
        )
        assert link_count == 4
    _cleanup_incidents(incident_ids, alert_ids)


def test_same_sample_anomalies_correlate_and_do_not_duplicate_event_links() -> None:
    timestamp = datetime.now(UTC)
    incident_ids: list[int] = []
    anomaly_ids: list[int] = []
    with TestClient(app), SessionLocal() as session:
        metrics = json.dumps({"cpu_percent": 96}, sort_keys=True)
        rule = AnomalyEvent(
            created_at=timestamp,
            detector="rule",
            severity="critical",
            explanation="CPU exceeded its configured threshold.",
            metrics_json=metrics,
            target="",
            model_status="available",
        )
        forest = AnomalyEvent(
            created_at=timestamp,
            detector="isolation_forest",
            severity="warning",
            explanation="Sample differs from the learned model.",
            metrics_json=metrics,
            target="",
            model_status="available",
        )
        session.add_all([rule, forest])
        session.flush()
        anomaly_ids = [rule.id, forest.id]
        first = create_incident_from_anomaly(session, rule)
        correlated = create_incident_from_anomaly(session, forest)
        duplicate = create_incident_from_anomaly(session, rule)
        session.commit()

        assert first.id == correlated.id == duplicate.id
        incident_ids = [first.id]
        link_count = session.scalar(
            select(func.count()).select_from(IncidentEvent).where(
                IncidentEvent.incident_id == first.id
            )
        )
        assert link_count == 2
    _cleanup_incidents(incident_ids, anomaly_ids=anomaly_ids)


def test_operator_incident_workflow_audits_actions_and_viewer_is_read_only() -> None:
    suffix = uuid4().hex[:12]
    with logged_in_user("OPERATOR") as (operator_client, _):
        with logged_in_user("VIEWER") as (viewer_client, _):
            with SessionLocal() as session:
                incident = Incident(
                    title="Incident workflow test",
                    severity="warning",
                    status="OPEN",
                    affected_target="api-test",
                    first_detected_at=datetime.now(UTC),
                    last_updated_at=datetime.now(UTC),
                )
                assignee = User(
                    username=f"assignee-{suffix}",
                    email=f"assignee-{suffix}@example.test",
                    password_hash=hash_password("incident-test-credential-2026"),
                    role="OPERATOR",
                    is_active=True,
                )
                session.add_all([incident, assignee])
                session.commit()
                incident_id = incident.id
                assignee_id = assignee.id

            try:
                assert viewer_client.get(f"/api/incidents/{incident_id}").status_code == 200
                forbidden = viewer_client.post(f"/api/incidents/{incident_id}/acknowledge")
                assert forbidden.status_code == 403

                assigned = operator_client.patch(
                    f"/api/incidents/{incident_id}/assign",
                    json={"operator_id": assignee_id},
                )
                noted = operator_client.post(
                    f"/api/incidents/{incident_id}/notes",
                    json={"note": "Checked service and host metrics."},
                )
                acknowledged = operator_client.post(
                    f"/api/incidents/{incident_id}/acknowledge"
                )
                resolved = operator_client.post(f"/api/incidents/{incident_id}/resolve")
                details = operator_client.get(f"/api/incidents/{incident_id}")

                assert assigned.status_code == 200
                assert assigned.json()["assigned_operator"]["id"] == assignee_id
                assert noted.status_code == 201
                assert acknowledged.json()["status"] == "ACKNOWLEDGED"
                assert resolved.json()["status"] == "RESOLVED"
                assert details.status_code == 200
                assert details.json()["notes"][0]["note"] == "Checked service and host metrics."
                actions = [item["action"] for item in details.json()["history"]]
                assert {
                    "incident_assigned",
                    "incident_note_added",
                    "incident_acknowledged",
                    "incident_resolved",
                }.issubset(actions)
            finally:
                _cleanup_incidents([incident_id])
                with SessionLocal() as session:
                    session.execute(delete(UserSession).where(UserSession.user_id == assignee_id))
                    session.execute(delete(User).where(User.id == assignee_id))
                    session.commit()
