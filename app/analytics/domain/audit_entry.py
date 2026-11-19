"""Agregado de entrada de bitácora de auditoría inmutable y verificación criptográfica (US15, T36; US21, T96)."""
import hashlib
import json
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
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
    previous_hash: str | None = None,
) -> str:
    """Calcula el sello SHA-256 determinístico de una entrada de auditoría (9 campos encadenados)."""
    normalized_ts = occurred_at.astimezone(UTC) if occurred_at.tzinfo is not None else occurred_at
    canonical_detail = json.dumps(detail, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    payload = "|".join(
        [
            event_type,
            str(workspace_id),
            str(actor_id) if actor_id else "",
            entity_type,
            str(entity_id) if entity_id else "",
            str(ticket_id) if ticket_id else "",
            normalized_ts.isoformat(),
            canonical_detail,
            previous_hash or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuditIntegrityStatus(StrEnum):
    """Resultado de la verificación de integridad criptográfica de una entrada."""

    VALID = "VALID"
    TAMPERED = "TAMPERED"
    CHAIN_BROKEN = "CHAIN_BROKEN"


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
    previous_hash: str | None = None
    seq: int | None = None

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
        previous_hash: str | None = None,
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
            previous_hash=previous_hash,
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
            previous_hash=previous_hash,
        )

    def computed_integrity_hash(self) -> str:
        """Recalcula el hash SHA-256 esperado con los campos actuales de la entrada."""
        return compute_integrity_hash(
            event_type=self.event_type,
            workspace_id=self.workspace_id,
            actor_id=self.actor_id,
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            ticket_id=self.ticket_id,
            occurred_at=self.occurred_at,
            detail=self.detail,
            previous_hash=self.previous_hash,
        )

    def verify_integrity(self) -> bool:
        """Comprueba que ningún campo del registro haya sido alterado."""
        return self.integrity_hash == self.computed_integrity_hash()

    def chained_to(self, previous_hash: str | None) -> "AuditEntry":
        """Devuelve una copia encadenada a previous_hash con su integrity_hash recalculado."""
        recalculated = compute_integrity_hash(
            event_type=self.event_type,
            workspace_id=self.workspace_id,
            actor_id=self.actor_id,
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            ticket_id=self.ticket_id,
            occurred_at=self.occurred_at,
            detail=self.detail,
            previous_hash=previous_hash,
        )
        return replace(self, previous_hash=previous_hash, integrity_hash=recalculated)


@dataclass(frozen=True)
class AuditIntegrityReport:
    """Resultado de verificar el hash propio y el encadenamiento de una entrada de bitácora."""

    entry_id: uuid.UUID
    seq: int | None
    valid: bool
    status: AuditIntegrityStatus
    hash_valid: bool
    chain_valid: bool
    stored_hash: str
    computed_hash: str
    previous_entry_id: uuid.UUID | None
    stored_previous_hash: str | None
    expected_previous_hash: str | None
    verified_at: datetime
    message: str

    @classmethod
    def evaluate(
        cls,
        entry: AuditEntry,
        previous: AuditEntry | None,
        *,
        verified_at: datetime | None = None,
    ) -> "AuditIntegrityReport":
        computed_hash = entry.computed_integrity_hash()
        hash_valid = entry.integrity_hash == computed_hash

        if previous is None:
            previous_entry_id = None
            expected_previous_hash = None
            chain_valid = entry.previous_hash is None
        else:
            previous_entry_id = previous.id
            expected_previous_hash = previous.integrity_hash
            chain_valid = (entry.previous_hash == previous.integrity_hash) and previous.verify_integrity()

        valid = hash_valid and chain_valid
        if valid:
            status = AuditIntegrityStatus.VALID
            message = "Registro íntegro: el hash SHA-256 y el encadenamiento con el registro anterior coinciden."
        elif not hash_valid:
            status = AuditIntegrityStatus.TAMPERED
            message = "Alerta de integridad: el contenido del registro no coincide con su sello SHA-256 almacenado."
        else:
            status = AuditIntegrityStatus.CHAIN_BROKEN
            message = (
                "Alerta de encadenamiento: el enlace criptográfico con el registro anterior está roto "
                "o el registro anterior fue alterado."
            )

        return cls(
            entry_id=entry.id,
            seq=entry.seq,
            valid=valid,
            status=status,
            hash_valid=hash_valid,
            chain_valid=chain_valid,
            stored_hash=entry.integrity_hash,
            computed_hash=computed_hash,
            previous_entry_id=previous_entry_id,
            stored_previous_hash=entry.previous_hash,
            expected_previous_hash=expected_previous_hash,
            verified_at=verified_at or _now(),
            message=message,
        )
