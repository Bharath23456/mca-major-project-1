import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.models import AlertEvent, AnomalyEvent, Incident, IncidentEvent
from app.settings import settings

SEVERITY_RANK = {"critical": 4, "warning": 3, "info": 2, "unknown": 1}
RELATED_FAMILY_PAIRS = {
    frozenset(("cpu", "response_time")),
    frozenset(("endpoint", "response_time")),
}


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _alert_detected_at(alert: AlertEvent) -> datetime:
    if alert.starts_at:
        try:
            return _utc(datetime.fromisoformat(alert.starts_at.replace("Z", "+00:00")))
        except ValueError:
            pass
    return _utc(alert.updated_at)


def _normalized_severity(value: str) -> str:
    return value if value in SEVERITY_RANK else "unknown"


def _alert_family(alert: AlertEvent) -> str:
    name = alert.alertname.casefold()
    if "cpu" in name:
        return "cpu"
    if "latency" in name or "response" in name:
        return "response_time"
    if "memory" in name:
        return "memory"
    if "disk" in name:
        return "disk"
    if "endpointunavailable" in name or "probe" in name:
        return "endpoint"
    if "monitoringtarget" in name or "targetunavailable" in name:
        return "target_availability"
    return name or "unknown"


def _anomaly_family(event: AnomalyEvent) -> str:
    explanation = event.explanation.casefold()
    if "cpu" in explanation:
        return "cpu"
    if "memory" in explanation:
        return "memory"
    if "disk" in explanation:
        return "disk"
    if event.detector == "isolation_forest":
        return "anomaly"
    return "resource_pressure"


def _incident_families(session: Session, incident_id: int) -> set[str]:
    relationships = session.scalars(
        select(IncidentEvent).where(IncidentEvent.incident_id == incident_id)
    ).all()
    families: set[str] = set()
    for relationship in relationships:
        if relationship.alert_event_id is not None:
            alert = session.get(AlertEvent, relationship.alert_event_id)
            if alert is not None:
                families.add(_alert_family(alert))
        elif relationship.anomaly_event_id is not None:
            event = session.get(AnomalyEvent, relationship.anomaly_event_id)
            if event is not None:
                families.add(_anomaly_family(event))
    return families


def _related_incident(
    session: Session,
    *,
    target: str,
    family: str,
    detected_at: datetime,
    event_metrics: str | None = None,
) -> tuple[Incident | None, str | None]:
    cutoff = _utc(detected_at) - timedelta(seconds=settings.alert_correlation_window_seconds)
    candidates = session.scalars(
        select(Incident)
        .where(
            Incident.status != "RESOLVED",
            Incident.affected_target == target,
            Incident.last_updated_at >= cutoff,
        )
        .order_by(Incident.last_updated_at.desc(), Incident.id.desc())
        .limit(100)
    ).all()
    for incident in candidates:
        families = _incident_families(session, incident.id)
        if not target:
            if event_metrics is None:
                continue
            for relationship in session.scalars(
                select(IncidentEvent).where(IncidentEvent.incident_id == incident.id)
            ):
                if relationship.anomaly_event_id is None:
                    continue
                prior = session.get(AnomalyEvent, relationship.anomaly_event_id)
                if (
                    prior is not None
                    and prior.metrics_json == event_metrics
                    and abs((_utc(prior.created_at) - _utc(detected_at)).total_seconds()) <= 10
                ):
                    return incident, "Same metric evidence from adjacent detectors in one sample."
            continue
        if family in families:
            return (
                incident,
                f"Same target and metric family '{family}' "
                "within the correlation window.",
            )
        if any(frozenset((family, prior)) in RELATED_FAMILY_PAIRS for prior in families):
            return (
                incident,
                f"Same target; related metric families {', '.join(sorted(families | {family}))} "
                f"occurred within {settings.alert_correlation_window_seconds} seconds.",
            )
        if event_metrics is not None:
            for relationship in session.scalars(
                select(IncidentEvent).where(IncidentEvent.incident_id == incident.id)
            ):
                if relationship.anomaly_event_id is None:
                    continue
                prior = session.get(AnomalyEvent, relationship.anomaly_event_id)
                if (
                    prior is not None
                    and prior.metrics_json == event_metrics
                    and abs((_utc(prior.created_at) - _utc(detected_at)).total_seconds()) <= 10
                ):
                    return incident, "Same target and metric evidence from one inference sample."
    return None, None


def _raise_severity(incident: Incident, severity: str) -> None:
    if SEVERITY_RANK[severity] > SEVERITY_RANK.get(incident.severity, 0):
        incident.severity = severity


def correlate_alert_event(
    session: Session,
    alert: AlertEvent,
    *,
    previous_status: str | None,
) -> Incident | None:
    if alert.status != "firing":
        return None

    existing_link = session.scalar(
        select(IncidentEvent).where(IncidentEvent.alert_event_id == alert.id)
    )
    now = datetime.now(UTC)
    if existing_link is not None:
        incident = session.get(Incident, existing_link.incident_id)
        if incident is None:
            return None
        if incident.status == "RESOLVED" and previous_status == "resolved":
            incident.status = "OPEN"
            record_audit(
                session,
                user_id=None,
                action="incident_reopened",
                resource_type="incident",
                resource_id=str(incident.id),
                incident_id=incident.id,
                result="success",
                details={"source": "alert"},
            )
        incident.last_updated_at = now
        incident.updated_at = now
        _raise_severity(incident, _normalized_severity(alert.severity))
        return incident

    target = alert.instance.strip()
    family = _alert_family(alert)
    detected_at = _alert_detected_at(alert)
    incident, reason = _related_incident(
        session,
        target=target,
        family=family,
        detected_at=detected_at,
    )
    created = incident is None
    if incident is None:
        severity = _normalized_severity(alert.severity)
        incident = Incident(
            title=(alert.summary or alert.alertname or "Monitoring alert")[:256],
            severity=severity,
            status="OPEN",
            affected_target=target,
            first_detected_at=detected_at,
            last_updated_at=detected_at,
            created_at=now,
            updated_at=now,
        )
        session.add(incident)
        session.flush()
        reason = "Incident created from firing Alertmanager event."
    else:
        incident.last_updated_at = detected_at
        incident.updated_at = now
        _raise_severity(incident, _normalized_severity(alert.severity))

    session.add(
        IncidentEvent(
            incident_id=incident.id,
            alert_event_id=alert.id,
            correlation_reason=reason or "Related Alertmanager event.",
            created_at=now,
        )
    )
    session.flush()
    record_audit(
        session,
        user_id=None,
        action="incident_created" if created else "incident_correlated",
        resource_type="incident",
        resource_id=str(incident.id),
        incident_id=incident.id,
        result="success",
        details={"source": "alert", "event_id": alert.id, "metric_family": family},
    )
    return incident


def create_incident_from_anomaly(session: Session, event: AnomalyEvent) -> Incident:
    session.flush()
    existing_link = session.scalar(
        select(IncidentEvent).where(IncidentEvent.anomaly_event_id == event.id)
    )
    if existing_link is not None:
        incident = session.get(Incident, existing_link.incident_id)
        if incident is not None:
            return incident

    metrics = json.dumps(json.loads(event.metrics_json), sort_keys=True)
    target = event.target.strip()
    family = _anomaly_family(event)
    incident, reason = _related_incident(
        session,
        target=target,
        family=family,
        detected_at=_utc(event.created_at),
        event_metrics=metrics,
    )
    created = incident is None
    now = datetime.now(UTC)
    if incident is None:
        incident = Incident(
            title=f"{event.detector.replace('_', ' ').title()} anomaly: {event.explanation}"[:256],
            severity=_normalized_severity(event.severity),
            status="OPEN",
            affected_target=target,
            first_detected_at=_utc(event.created_at),
            last_updated_at=_utc(event.created_at),
            created_at=now,
            updated_at=now,
        )
        session.add(incident)
        session.flush()
        reason = "Incident created from persisted anomaly finding."
    else:
        incident.last_updated_at = _utc(event.created_at)
        incident.updated_at = now
        _raise_severity(incident, _normalized_severity(event.severity))

    session.add(
        IncidentEvent(
            incident_id=incident.id,
            anomaly_event_id=event.id,
            correlation_reason=reason or "Related anomaly finding.",
            created_at=now,
        )
    )
    session.flush()
    record_audit(
        session,
        user_id=None,
        action="incident_created" if created else "incident_correlated",
        resource_type="incident",
        resource_id=str(incident.id),
        incident_id=incident.id,
        result="success",
        details={"source": "anomaly", "event_id": event.id, "metric_family": family},
    )
    return incident
