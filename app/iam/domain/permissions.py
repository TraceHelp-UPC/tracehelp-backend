"""Matriz RBAC de TraceHelp (Capítulo V, contexto IAM)."""
from dataclasses import dataclass
from enum import StrEnum

from app.iam.domain.enums import RoleName


class Permission(StrEnum):
    TICKETS_CREATE = "tickets:create"
    TICKETS_READ_OWN = "tickets:read_own"
    TICKETS_MANAGE = "tickets:manage"
    TICKETS_ESCALATE = "tickets:escalate"
    TICKETS_RESOLVE_ESCALATED = "tickets:resolve_escalated"
    TRIAGE_VALIDATE_HITL = "triage:validate_hitl"
    KB_WRITE = "kb:write"
    CONFIG_WRITE = "config:write"
    IAM_ADMIN = "iam:admin"
    ANALYTICS_READ = "analytics:read"
    AUDIT_READ = "audit:read"


_BASE = {Permission.TICKETS_CREATE, Permission.TICKETS_READ_OWN}

_MATRIX: dict[RoleName, frozenset[Permission]] = {
    RoleName.COLLABORATOR: frozenset(_BASE),
    RoleName.ANALYST_L1: frozenset(
        _BASE | {Permission.TICKETS_MANAGE, Permission.TRIAGE_VALIDATE_HITL, Permission.TICKETS_ESCALATE}
    ),
    RoleName.SPECIALIST_L2: frozenset(
        _BASE | {Permission.TICKETS_MANAGE, Permission.TRIAGE_VALIDATE_HITL, Permission.TICKETS_RESOLVE_ESCALATED}
    ),
    RoleName.IT_LEADER: frozenset(
        _BASE
        | {
            Permission.KB_WRITE,
            Permission.CONFIG_WRITE,
            Permission.IAM_ADMIN,
            Permission.ANALYTICS_READ,
            Permission.AUDIT_READ,
        }
    ),
}


@dataclass(frozen=True)
class RolePermission:
    """Value object que asocia un rol con su conjunto inmutable de permisos."""

    role: RoleName
    permissions: frozenset[Permission]

    @classmethod
    def for_role(cls, role: RoleName) -> "RolePermission":
        return cls(role=role, permissions=_MATRIX[role])

    def allows(self, permission: Permission) -> bool:
        return permission in self.permissions
