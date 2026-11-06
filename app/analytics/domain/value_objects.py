"""Value Objects del Bounded Context Analytics."""
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from app.analytics.domain.enums import AuditActionType
from app.analytics.domain.exceptions import InvalidAuditLogDataError


def _normalize_timestamp(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    else:
        dt = dt.astimezone(UTC)
    return dt.isoformat(timespec="microseconds")


@dataclass(frozen=True)
class IntegrityHash:
    """Firma criptográfica SHA-256 que garantiza la inmutabilidad del registro de auditoría (US15, US21)."""

    value: str

    def __post_init__(self) -> None:
        normalized = (self.value or "").strip().lower()
        if len(normalized) != 64 or any(c not in "0123456789abcdef" for c in normalized):
            raise InvalidAuditLogDataError("El hash de integridad debe ser un SHA-256 hexadecimal válido de 64 caracteres.")
        object.__setattr__(self, "value", normalized)

    @classmethod
    def compute(
        cls,
        *,
        workspace_id: uuid.UUID,
        ticket_id: uuid.UUID,
        action_type: AuditActionType | str,
        consulted_sources: list[dict] | tuple[dict, ...],
        validator_analyst_id: uuid.UUID | None,
        occurred_at: datetime,
        details: str | None = None,
    ) -> "IntegrityHash":
        action_str = action_type.value if isinstance(action_type, AuditActionType) else str(action_type)
        canonical_payload = json.dumps(
            {
                "workspace_id": str(workspace_id),
                "ticket_id": str(ticket_id),
                "action_type": action_str,
                "consulted_sources": list(consulted_sources or []),
                "validator_analyst_id": str(validator_analyst_id) if validator_analyst_id else None,
                "occurred_at": _normalize_timestamp(occurred_at),
                "details": details or "",
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        return cls(value=digest)
