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


@dataclass(frozen=True, kw_only=True)
class UserAuthenticated(DomainEvent):
    user_id: uuid.UUID
    workspace_id: uuid.UUID
