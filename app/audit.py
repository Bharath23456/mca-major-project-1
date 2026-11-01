import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def record_audit(
    session: Session,
    *,
    user_id: int | None,
    action: str,
    resource_type: str,
    result: str,
    resource_id: str | None = None,
    incident_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        incident_id=incident_id,
        result=result,
        details_json=json.dumps(details or {}, sort_keys=True),
    )
    session.add(entry)
    return entry
