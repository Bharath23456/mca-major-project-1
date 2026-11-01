import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.auth import (
    hash_password,
    require_roles,
    validate_email,
    validate_password,
    validate_username,
)
from app.database import get_session
from app.models import AuditLog, User, UserSession

router = APIRouter(tags=["user management", "audit"])
RoleName = Literal["ADMIN", "OPERATOR", "VIEWER"]


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=12, max_length=128)
    role: RoleName

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        return validate_username(value)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return validate_email(value)

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, value: str) -> str:
        return validate_password(value)


class UserStatusRequest(BaseModel):
    is_active: bool


class UserRoleRequest(BaseModel):
    role: RoleName


def _serialize_user(user: User) -> dict[str, object]:
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": _utc_iso(user.created_at),
        "updated_at": _utc_iso(user.updated_at),
    }


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _serialize_audit(entry: AuditLog) -> dict[str, object]:
    return {
        "id": entry.id,
        "user_id": entry.user_id,
        "action": entry.action,
        "resource_type": entry.resource_type,
        "resource_id": entry.resource_id,
        "incident_id": entry.incident_id,
        "result": entry.result,
        "details": json.loads(entry.details_json),
        "timestamp": _utc_iso(entry.created_at),
    }


@router.get("/api/users")
def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    session: Session = Depends(get_session),
    _: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, object]]:
    users = session.scalars(
        select(User).order_by(User.username).offset(offset).limit(limit)
    ).all()
    return [_serialize_user(user) for user in users]


@router.post("/api/users", status_code=201)
def create_user(
    payload: UserCreateRequest,
    session: Session = Depends(get_session),
    actor: User = Depends(require_roles("ADMIN")),
) -> dict[str, object]:
    duplicate = session.scalar(
        select(User.id).where(or_(User.username == payload.username, User.email == payload.email))
    )
    if duplicate is not None:
        record_audit(
            session,
            user_id=actor.id,
            action="user_create",
            resource_type="user",
            result="failure",
            details={"reason": "username_or_email_exists"},
        )
        session.commit()
        raise HTTPException(
            status_code=409,
            detail="A user already exists with that username or email.",
        )

    user = User(
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    session.add(user)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409,
            detail="A user already exists with that username or email.",
        ) from None
    record_audit(
        session,
        user_id=actor.id,
        action="user_create",
        resource_type="user",
        resource_id=str(user.id),
        result="success",
        details={"role": user.role},
    )
    session.commit()
    session.refresh(user)
    return _serialize_user(user)


@router.patch("/api/users/{user_id}")
def update_user_status(
    user_id: int,
    payload: UserStatusRequest,
    session: Session = Depends(get_session),
    actor: User = Depends(require_roles("ADMIN")),
) -> dict[str, object]:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.is_active and not payload.is_active and user.role == "ADMIN":
        active_admins = session.scalar(
            select(func.count(User.id)).where(User.role == "ADMIN", User.is_active.is_(True))
        )
        if active_admins is not None and active_admins <= 1:
            record_audit(
                session,
                user_id=actor.id,
                action="user_status_update",
                resource_type="user",
                resource_id=str(user.id),
                result="denied",
                details={"reason": "last_active_admin"},
            )
            session.commit()
            raise HTTPException(
                status_code=409,
                detail="The last active administrator cannot be deactivated.",
            )

    user.is_active = payload.is_active
    if not payload.is_active:
        session.execute(delete(UserSession).where(UserSession.user_id == user.id))
    record_audit(
        session,
        user_id=actor.id,
        action="user_status_update",
        resource_type="user",
        resource_id=str(user.id),
        result="success",
        details={"is_active": user.is_active},
    )
    session.commit()
    session.refresh(user)
    return _serialize_user(user)


@router.patch("/api/users/{user_id}/role")
def update_user_role(
    user_id: int,
    payload: UserRoleRequest,
    session: Session = Depends(get_session),
    actor: User = Depends(require_roles("ADMIN")),
) -> dict[str, object]:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    if user.role == "ADMIN" and user.is_active and payload.role != "ADMIN":
        active_admins = session.scalar(
            select(func.count(User.id)).where(User.role == "ADMIN", User.is_active.is_(True))
        )
        if active_admins is not None and active_admins <= 1:
            record_audit(
                session,
                user_id=actor.id,
                action="user_role_update",
                resource_type="user",
                resource_id=str(user.id),
                result="denied",
                details={"reason": "last_active_admin"},
            )
            session.commit()
            raise HTTPException(
                status_code=409,
                detail="The last active administrator cannot be demoted.",
            )

    previous_role = user.role
    user.role = payload.role
    record_audit(
        session,
        user_id=actor.id,
        action="user_role_update",
        resource_type="user",
        resource_id=str(user.id),
        result="success",
        details={"previous_role": previous_role, "role": user.role},
    )
    session.commit()
    session.refresh(user)
    return _serialize_user(user)


@router.get("/api/users/{user_id}/activity")
def list_user_activity(
    user_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    session: Session = Depends(get_session),
    _: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, object]]:
    if session.get(User, user_id) is None:
        raise HTTPException(status_code=404, detail="User not found.")
    entries = session.scalars(
        select(AuditLog)
        .where(
            or_(
                AuditLog.user_id == user_id,
                (AuditLog.resource_type == "user") & (AuditLog.resource_id == str(user_id)),
            )
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [_serialize_audit(entry) for entry in entries]


@router.get("/api/audit-logs")
def list_audit_logs(
    action: str | None = Query(default=None, max_length=64),
    resource_type: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    session: Session = Depends(get_session),
    _: User = Depends(require_roles("ADMIN")),
) -> list[dict[str, object]]:
    statement = select(AuditLog)
    if action:
        statement = statement.where(AuditLog.action == action)
    if resource_type:
        statement = statement.where(AuditLog.resource_type == resource_type)
    entries = session.scalars(
        statement.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [_serialize_audit(entry) for entry in entries]
