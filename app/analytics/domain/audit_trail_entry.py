"""Agregado raíz inmutable AuditTrailEntry (US15, US21, TS06)."""
import uuid
from datetime import UTC, datetime

from app.analytics.domain.enums import AuditActionType
from app.analytics.domain.value_objects import IntegrityHash
from app.shared.domain.aggregate_root import AggregateRoot


def _now() -> datetime:
    return datetime.now(UTC)


class AuditTrailEntry(AggregateRoot):
    """Bitácora inmutable que almacena cada operación de IA, fuentes RAG citadas y analista validador (US15, US21).

    No expone métodos de mutación ni borrado (append-only) y calcula al instanciarse un IntegrityHash (SHA-256).
    """

    def __init__(
        self,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        ticket_id: uuid.UUID,
        action_type: AuditActionType,
        consulted_sources: list[dict] | tuple[dict, ...] | None = None,
        validator_analyst_id: uuid.UUID | None = None,
        confidence_score: float | None = None,
        details: str | None = None,
        occurred_at: datetime | None = None,
        integrity_hash: IntegrityHash | None = None,
    ) -> None:
        super().__init__()
        occurred = occurred_at or _now()
        sources = tuple(dict(s) for s in (consulted_sources or []))
        cleaned_details = (details or "").strip() or None
        computed_hash = integrity_hash or IntegrityHash.compute(
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            action_type=action_type,
            consulted_sources=sources,
            validator_analyst_id=validator_analyst_id,
            occurred_at=occurred,
            details=cleaned_details,
        )

        self._id = id
        self._workspace_id = workspace_id
        self._ticket_id = ticket_id
        self._action_type = action_type
        self._consulted_sources = sources
        self._validator_analyst_id = validator_analyst_id
        self._confidence_score = confidence_score
        self._details = cleaned_details
        self._occurred_at = occurred
        self._integrity_hash = computed_hash

    @classmethod
    def record(
        cls,
        *,
        workspace_id: uuid.UUID,
        ticket_id: uuid.UUID,
        action_type: AuditActionType,
        consulted_sources: list[dict] | None = None,
        validator_analyst_id: uuid.UUID | None = None,
        confidence_score: float | None = None,
        details: str | None = None,
        occurred_at: datetime | None = None,
    ) -> "AuditTrailEntry":
        return cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            ticket_id=ticket_id,
            action_type=action_type,
            consulted_sources=consulted_sources,
            validator_analyst_id=validator_analyst_id,
            confidence_score=confidence_score,
            details=details,
            occurred_at=occurred_at,
        )

    @property
    def id(self) -> uuid.UUID:
        return self._id

    @property
    def workspace_id(self) -> uuid.UUID:
        return self._workspace_id

    @property
    def ticket_id(self) -> uuid.UUID:
        return self._ticket_id

    @property
    def action_type(self) -> AuditActionType:
        return self._action_type

    @property
    def consulted_sources(self) -> tuple[dict, ...]:
        return self._consulted_sources

    @property
    def validator_analyst_id(self) -> uuid.UUID | None:
        return self._validator_analyst_id

    @property
    def confidence_score(self) -> float | None:
        return self._confidence_score

    @property
    def details(self) -> str | None:
        return self._details

    @property
    def occurred_at(self) -> datetime:
        return self._occurred_at

    @property
    def integrity_hash(self) -> IntegrityHash:
        return self._integrity_hash

    @property
    def integrity_hash_sha256(self) -> str:
        return self._integrity_hash.value

    def verify_integrity(self) -> bool:
        """Recalcula el hash SHA-256 y comprueba que el registro no ha sido alterado (US21 Escenario 3)."""
        expected = IntegrityHash.compute(
            workspace_id=self._workspace_id,
            ticket_id=self._ticket_id,
            action_type=self._action_type,
            consulted_sources=self._consulted_sources,
            validator_analyst_id=self._validator_analyst_id,
            occurred_at=self._occurred_at,
            details=self._details,
        )
        return self._integrity_hash == expected
