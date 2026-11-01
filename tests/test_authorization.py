from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.auth import hash_password
from app.database import SessionLocal
from app.main import app
from app.models import AuditLog, User, UserSession


@contextmanager
def authenticated_client(role: str) -> Iterator[tuple[TestClient, int]]:
    client = TestClient(app)
    with client:
        suffix = uuid4().hex[:12]
        with SessionLocal() as session:
            user = User(
                username=f"role-{suffix}",
                email=f"role-{suffix}@example.test",
                password_hash=hash_password("test-role-credential-2026"),
                role=role,
                is_active=True,
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            user_id = user.id
            username = user.username

        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": "test-role-credential-2026"},
        )
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        yield client, user_id

        with SessionLocal() as session:
            session.execute(delete(UserSession).where(UserSession.user_id == user_id))
            session.execute(delete(AuditLog).where(AuditLog.user_id == user_id))
            session.execute(delete(User).where(User.id == user_id))
            session.commit()


def test_viewer_can_read_monitoring_but_cannot_mutate_or_administer() -> None:
    with authenticated_client("VIEWER") as (client, _):
        assert client.get("/api/v1/anomalies").status_code == 200
        assert client.get("/api/v1/alerts").status_code == 200
        assert client.get("/api/users").status_code == 403
        assert client.get("/api/audit-logs").status_code == 403
        assert client.post(
            "/api/v1/anomalies/scan",
            json={},
        ).status_code == 403
        assert client.post(
            "/api/v1/anomalies/score",
            json={
                "cpu_percent": 20,
                "memory_percent": 40,
                "disk_percent": 50,
                "network_receive_bytes_per_second": 100,
                "network_transmit_bytes_per_second": 100,
            },
        ).status_code == 403


def test_operator_can_score_metrics_but_cannot_manage_users() -> None:
    with authenticated_client("OPERATOR") as (client, _):
        response = client.post(
            "/api/v1/anomalies/score",
            json={
                "cpu_percent": 20,
                "memory_percent": 40,
                "disk_percent": 50,
                "network_receive_bytes_per_second": 100,
                "network_transmit_bytes_per_second": 100,
            },
        )

        assert response.status_code == 200
        assert client.get("/api/users").status_code == 403


def test_admin_can_create_update_and_review_users_with_audit_history() -> None:
    with authenticated_client("ADMIN") as (client, _):
        created_response = client.post(
            "/api/users",
            json={
                "username": "managed-operator",
                "email": "managed-operator@example.test",
                "password": "new-operator-credential-2026",
                "role": "VIEWER",
            },
        )
        assert created_response.status_code == 201
        created = created_response.json()
        user_id = created["id"]
        assert created["role"] == "VIEWER"
        assert "password_hash" not in created

        promoted = client.patch(
            f"/api/users/{user_id}/role",
            json={"role": "OPERATOR"},
        )
        deactivated = client.patch(
            f"/api/users/{user_id}",
            json={"is_active": False},
        )
        activity = client.get(f"/api/users/{user_id}/activity")
        audit = client.get("/api/audit-logs")

        assert promoted.status_code == 200
        assert promoted.json()["role"] == "OPERATOR"
        assert deactivated.status_code == 200
        assert deactivated.json()["is_active"] is False
        assert activity.status_code == audit.status_code == 200
        assert any(entry["action"] == "user_create" for entry in activity.json())
        assert any(entry["action"] == "user_role_update" for entry in audit.json())


def test_last_active_admin_cannot_be_demoted_or_deactivated() -> None:
    with authenticated_client("ADMIN") as (client, user_id):
        demoted = client.patch(f"/api/users/{user_id}/role", json={"role": "VIEWER"})
        deactivated = client.patch(f"/api/users/{user_id}", json={"is_active": False})

        assert demoted.status_code == 409
        assert deactivated.status_code == 409
        audit = client.get("/api/audit-logs").json()
        assert any(entry["result"] == "denied" for entry in audit)
