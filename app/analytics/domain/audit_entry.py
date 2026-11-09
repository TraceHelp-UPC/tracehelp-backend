"""Agregado de entrada de bitácora de auditoría inmutable (US15, T36)."""
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def _now() -> datetime:
    return datetime.now(UTC)


def compute_integrity_hash(
    *,
    event_type: str,
    workspace_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    entity_type: str,
    entity_id: uuid.UUID | None,
    ticket_id: uuid.UUID | None,
    occurred_at: datetime,
    detail: dict[str, Any],
) -> str:
    """Calcula el sello SHA-256 determinístico de una entrada de auditoría."""
    canonical_detail = json.dumps(detail, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    payload = "|".join(
        [
            event_type,
            str(workspace_id),
            str(actor_id) if actor_id else "",
            entity_type,
            str(entity_id) if entity_id else "",
            str(ticket_id) if ticket_id else "",
            occurred_at.isoformat(),
            canonical_detail,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditEntry:
    """Registro inmutable de un evento de dominio relevante para auditoría."""

    id: uuid.UUID
    workspace_id: uuid.UUID
    event_type: str
    actor_id: uuid.UUID | None
    entity_type: str
    entity_id: uuid.UUID | None
    ticket_id: uuid.UUID | None
    detail: dict[str, Any]
    integrity_hash: str
    occurred_at: datetime = field(default_factory=_now)

    @classmethod
    def record(
        cls,
        *,
        workspace_id: uuid.UUID,
        event_type: str,
        entity_type: str,
        actor_id: uuid.UUID | None = None,
        entity_id: uuid.UUID | None = None,
        ticket_id: uuid.UUID | None = None,
        detail: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> "AuditEntry":
        timestamp = occurred_at or _now()
        clean_detail = dict(detail or {})
        integrity_hash = compute_integrity_hash(
            event_type=event_type,
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            ticket_id=ticket_id,
            occurred_at=timestamp,
            detail=clean_detail,
        )
        return cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            event_type=event_type,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            ticket_id=ticket_id,
            detail=clean_detail,
            integrity_hash=integrity_hash,
            occurred_at=timestamp,
        )

    def verify_integrity(self) -> bool:
        """Comprueba que ningún campo del registro haya sido alterado."""
        expected = compute_integrity_hash(
            event_type=self.event_type,
            workspace_id=self.workspace_id,
            actor_id=self.actor_id,
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            ticket_id=self.ticket_id,
            occurred_at=self.occurred_at,
            detail=self.detail,
        )
        return self.integrity_hash == expected
