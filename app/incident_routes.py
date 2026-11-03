import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.auth import require_roles
from app.database import get_session
from app.incidents import incident_priority_label, incident_priority_score
from app.models import (
    AlertEvent,
    AnomalyEvent,
    AuditLog,
    Incident,
    IncidentEvent,
    IncidentNote,
    User,
)
from app.settings import settings

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


class IncidentNoteRequest(BaseModel):
    note: str = Field(min_length=1, max_length=4000)

    @field_validator("note")
    @classmethod
    def reject_blank_notes(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Incident notes cannot be blank.")
        return normalized


class IncidentAssignmentRequest(BaseModel):
    operator_id: int | None


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _serialize_event(session: Session, link: IncidentEvent) -> dict[str, object]:
    if link.alert_event_id is not None:
        alert = session.get(AlertEvent, link.alert_event_id)
        return {
            "event_type": "alert",
            "event_id": link.alert_event_id,
            "name": alert.alertname if alert else None,
            "status": alert.status if alert else None,
            "severity": alert.severity if alert else None,
            "summary": alert.summary if alert else None,
            "description": alert.description if alert else None,
            "target": alert.instance if alert else None,
            "labels": json.loads(alert.labels_json) if alert else {},
            "correlation_reason": link.correlation_reason,
            "created_at": _utc_iso(link.created_at),
        }
    anomaly = session.get(AnomalyEvent, link.anomaly_event_id)
    return {
        "event_type": "anomaly",
        "event_id": link.anomaly_event_id,
        "name": anomaly.detector if anomaly else None,
        "severity": anomaly.severity if anomaly else None,
        "summary": anomaly.explanation if anomaly else None,
        "target": anomaly.target or None if anomaly else None,
        "score": anomaly.score if anomaly else None,
        "model_status": anomaly.model_status if anomaly else None,
        "metrics": json.loads(anomaly.metrics_json) if anomaly else {},
        "correlation_reason": link.correlation_reason,
        "created_at": _utc_iso(link.created_at),
    }


def _serialize_incident(
    session: Session,
    incident: Incident,
    *,
    details: bool = False,
) -> dict[str, object]:
    assigned = (
        session.get(User, incident.assigned_operator_id)
        if incident.assigned_operator_id is not None
        else None
    )
    links = session.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident.id)
        .order_by(IncidentEvent.created_at, IncidentEvent.id)
    ).all()
    recent_target_incident_count = 0
    if incident.affected_target:
        recent_target_incident_count = int(
            session.scalar(
                select(func.count(Incident.id)).where(
                    Incident.affected_target == incident.affected_target,
                    Incident.created_at
                    >= datetime.now(UTC)
                    - timedelta(hours=settings.incident_repeat_window_hours),
                )
            )
            or 0
        )
    priority_score = incident_priority_score(
        incident.severity,
        len(links),
        recent_target_incident_count,
    )
    result: dict[str, object] = {
        "id": incident.id,
        "title": incident.title,
        "severity": incident.severity,
        "status": incident.status,
        "affected_target": incident.affected_target,
        "priority": incident_priority_label(priority_score),
        "priority_score": priority_score,
        "related_event_count": len(links),
        "recent_target_incident_count": recent_target_incident_count,
        "recent_target_incident_window_hours": settings.incident_repeat_window_hours,
        "priority_rationale": (
            "Heuristic based on event severity as an impact proxy, linked-event frequency, "
            f"and {recent_target_incident_count} incident(s) for this target in the last "
            f"{settings.incident_repeat_window_hours}h. No service dependency or "
            "business-impact data is configured."
        ),
        "assigned_operator": (
            {"id": assigned.id, "username": assigned.username} if assigned else None
        ),
        "first_detected_at": _utc_iso(incident.first_detected_at),
        "last_updated_at": _utc_iso(incident.last_updated_at),
        "created_at": _utc_iso(incident.created_at),
        "updated_at": _utc_iso(incident.updated_at),
        "related_events": [_serialize_event(session, link) for link in links],
    }
    if details:
        notes = session.scalars(
            select(IncidentNote)
            .where(IncidentNote.incident_id == incident.id)
            .order_by(IncidentNote.created_at, IncidentNote.id)
        ).all()
        result["notes"] = [
            {
                "id": note.id,
                "author_user_id": note.author_user_id,
                "author_username": (
                    session.get(User, note.author_user_id).username
                    if session.get(User, note.author_user_id)
                    else "Former user"
                ),
                "note": note.note,
                "created_at": _utc_iso(note.created_at),
            }
            for note in notes
        ]
        history = session.scalars(
            select(AuditLog)
            .where(AuditLog.incident_id == incident.id)
            .order_by(AuditLog.created_at, AuditLog.id)
        ).all()
        result["history"] = [
            {
                "user_id": entry.user_id,
                "action": entry.action,
                "result": entry.result,
                "details": json.loads(entry.details_json),
                "timestamp": _utc_iso(entry.created_at),
            }
            for entry in history
        ]
    return result


def _get_incident(session: Session, incident_id: int) -> Incident:
    incident = session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found.")
    return incident


@router.get("/operators")
def list_assignable_operators(
    session: Session = Depends(get_session),
    _: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> list[dict[str, object]]:
    operators = session.scalars(
        select(User)
        .where(User.role == "OPERATOR", User.is_active.is_(True))
        .order_by(User.username)
    ).all()
    return [{"id": user.id, "username": user.username} for user in operators]


@router.get("")
def list_incidents(
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"] | None = None,
    severity: Literal["critical", "warning", "info", "unknown"] | None = None,
    target: str | None = Query(default=None, max_length=512),
    query: str | None = Query(default=None, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    session: Session = Depends(get_session),
) -> list[dict[str, object]]:
    statement = select(Incident)
    if status:
        statement = statement.where(Incident.status == status)
    if severity:
        statement = statement.where(Incident.severity == severity)
    if target:
        statement = statement.where(Incident.affected_target == target)
    if query:
        statement = statement.where(Incident.title.ilike(f"%{query}%"))
    incidents = session.scalars(
        statement.order_by(Incident.updated_at.desc(), Incident.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [_serialize_incident(session, incident) for incident in incidents]


@router.get("/{incident_id}")
def get_incident(
    incident_id: int,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    incident = _get_incident(session, incident_id)
    return _serialize_incident(session, incident, details=True)


@router.post("/{incident_id}/acknowledge")
def acknowledge_incident(
    incident_id: int,
    session: Session = Depends(get_session),
    actor: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict[str, object]:
    incident = _get_incident(session, incident_id)
    if incident.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="A resolved incident cannot be acknowledged.")
    if incident.status != "ACKNOWLEDGED":
        incident.status = "ACKNOWLEDGED"
        incident.last_updated_at = datetime.now(UTC)
        incident.updated_at = datetime.now(UTC)
        record_audit(
            session,
            user_id=actor.id,
            action="incident_acknowledged",
            resource_type="incident",
            resource_id=str(incident.id),
            incident_id=incident.id,
            result="success",
        )
        session.commit()
        session.refresh(incident)
    return _serialize_incident(session, incident)


@router.post("/{incident_id}/notes", status_code=201)
def add_incident_note(
    incident_id: int,
    payload: IncidentNoteRequest,
    session: Session = Depends(get_session),
    actor: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict[str, object]:
    incident = _get_incident(session, incident_id)
    now = datetime.now(UTC)
    note = IncidentNote(
        incident_id=incident.id,
        author_user_id=actor.id,
        note=payload.note,
        created_at=now,
    )
    session.add(note)
    incident.last_updated_at = now
    incident.updated_at = now
    session.flush()
    record_audit(
        session,
        user_id=actor.id,
        action="incident_note_added",
        resource_type="incident",
        resource_id=str(incident.id),
        incident_id=incident.id,
        result="success",
        details={"note_id": note.id, "note_length": len(payload.note)},
    )
    session.commit()
    return {
        "id": note.id,
        "incident_id": incident.id,
        "author_user_id": actor.id,
        "note": note.note,
        "created_at": _utc_iso(note.created_at),
    }


@router.post("/{incident_id}/resolve")
def resolve_incident(
    incident_id: int,
    session: Session = Depends(get_session),
    actor: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict[str, object]:
    incident = _get_incident(session, incident_id)
    if incident.status != "RESOLVED":
        incident.status = "RESOLVED"
        incident.last_updated_at = datetime.now(UTC)
        incident.updated_at = datetime.now(UTC)
        record_audit(
            session,
            user_id=actor.id,
            action="incident_resolved",
            resource_type="incident",
            resource_id=str(incident.id),
            incident_id=incident.id,
            result="success",
        )
        session.commit()
        session.refresh(incident)
    return _serialize_incident(session, incident)


@router.patch("/{incident_id}/assign")
def assign_incident(
    incident_id: int,
    payload: IncidentAssignmentRequest,
    session: Session = Depends(get_session),
    actor: User = Depends(require_roles("ADMIN", "OPERATOR")),
) -> dict[str, object]:
    incident = _get_incident(session, incident_id)
    operator = None
    if payload.operator_id is not None:
        operator = session.get(User, payload.operator_id)
        if operator is None or operator.role != "OPERATOR" or not operator.is_active:
            raise HTTPException(
                status_code=422,
                detail="Assigned user must be an active operator.",
            )
    previous_id = incident.assigned_operator_id
    incident.assigned_operator_id = operator.id if operator else None
    now = datetime.now(UTC)
    incident.last_updated_at = now
    incident.updated_at = now
    record_audit(
        session,
        user_id=actor.id,
        action="incident_assigned",
        resource_type="incident",
        resource_id=str(incident.id),
        incident_id=incident.id,
        result="success",
        details={
            "previous_operator_id": previous_id,
            "operator_id": incident.assigned_operator_id,
        },
    )
    session.commit()
    session.refresh(incident)
    return _serialize_incident(session, incident)
