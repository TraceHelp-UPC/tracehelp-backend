"""Eventos de dominio del contexto IAM."""
import uuid
from dataclasses import dataclass

from app.iam.domain.enums import RoleName
from app.shared.domain.aggregate_root import DomainEvent


@dataclass(frozen=True, kw_only=True)
class UserRegistered(DomainEvent):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    role: RoleName
    specialist_group: str | None = None
    registered_by: uuid.UUID | None = None


@dataclass(frozen=True, kw_only=True)
class UserAuthenticated(DomainEvent):
    user_id: uuid.UUID
    workspace_id: uuid.UUID


@dataclass(frozen=True, kw_only=True)
class UserRoleChanged(DomainEvent):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    changed_by: uuid.UUID | None
    previous_role: RoleName
    new_role: RoleName


@dataclass(frozen=True, kw_only=True)
class UserProfileUpdated(DomainEvent):
    """Cambios de departamento o grupo. `changes` = {campo: {"from": ..., "to": ...}}. Sin datos personales."""

    user_id: uuid.UUID
    workspace_id: uuid.UUID
    changed_by: uuid.UUID | None
    changes: dict[str, dict[str, str | None]]


@dataclass(frozen=True, kw_only=True)
class UserDeactivated(DomainEvent):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    changed_by: uuid.UUID | None


@dataclass(frozen=True, kw_only=True)
class UserReactivated(DomainEvent):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    changed_by: uuid.UUID | None
