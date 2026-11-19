"""Agregado WorkspaceSettings: configuración por workspace (US07 RAG, US08 reglas de negocio).

Un workspace tiene como máximo una fila en iam_workspace_settings. Las columnas son nullable:
None significa que ese parámetro hereda el valor por defecto de la aplicación.
"""
import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.iam.domain.events import ConfigurationChanged
from app.iam.domain.exceptions import InvalidWorkspaceSettingsError
from app.shared.domain.aggregate_root import AggregateRoot

MIN_SIMILARITY_THRESHOLD = 0.50
MAX_SIMILARITY_THRESHOLD = 0.95
SIMILARITY_WARNING_BELOW = 0.65
MAX_SELF_SERVICE_THRESHOLD = 0.99
MIN_RETRIEVAL_TOP_K = 1
MAX_RETRIEVAL_TOP_K = 10

_MIN_SIMILARITY_DEC = Decimal("0.50")
_MAX_SIMILARITY_DEC = Decimal("0.95")
_MAX_SELF_SERVICE_DEC = Decimal("0.99")
_RAG_FIELDS = ("similarity_threshold", "self_service_threshold", "retrieval_top_k", "strict_grounding")


def _parse_threshold(value: object, *, field_name: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise InvalidWorkspaceSettingsError(f"{field_name} debe ser un número decimal.")
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidWorkspaceSettingsError(f"{field_name} debe ser un número finito.")
    try:
        dec = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise InvalidWorkspaceSettingsError(f"{field_name} no es un número decimal válido.") from exc
    if not dec.is_finite():
        raise InvalidWorkspaceSettingsError(f"{field_name} debe ser un número finito.")
    exponent = dec.normalize().as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise InvalidWorkspaceSettingsError(f"{field_name} admite como máximo 2 decimales.")
    return dec


def _validate_similarity(value: object) -> Decimal:
    dec = _parse_threshold(value, field_name="similarity_threshold")
    if not (_MIN_SIMILARITY_DEC <= dec <= _MAX_SIMILARITY_DEC):
        raise InvalidWorkspaceSettingsError(
            f"similarity_threshold debe estar entre {MIN_SIMILARITY_THRESHOLD:.2f} y {MAX_SIMILARITY_THRESHOLD:.2f}."
        )
    return dec


def _validate_self_service(value: object, *, similarity: Decimal | None = None) -> Decimal:
    dec = _parse_threshold(value, field_name="self_service_threshold")
    if dec > _MAX_SELF_SERVICE_DEC:
        raise InvalidWorkspaceSettingsError(
            f"self_service_threshold no puede superar {MAX_SELF_SERVICE_THRESHOLD:.2f}."
        )
    if similarity is not None and dec < similarity:
        raise InvalidWorkspaceSettingsError(
            f"self_service_threshold debe ser mayor o igual que similarity_threshold ({similarity:.2f})."
        )
    if similarity is None and dec < _MIN_SIMILARITY_DEC:
        raise InvalidWorkspaceSettingsError(
            f"self_service_threshold debe ser mayor o igual que {MIN_SIMILARITY_THRESHOLD:.2f}."
        )
    return dec


def _validate_top_k(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidWorkspaceSettingsError("retrieval_top_k debe ser un número entero.")
    if not (MIN_RETRIEVAL_TOP_K <= value <= MAX_RETRIEVAL_TOP_K):
        raise InvalidWorkspaceSettingsError(
            f"retrieval_top_k debe estar entre {MIN_RETRIEVAL_TOP_K} y {MAX_RETRIEVAL_TOP_K}."
        )
    return value


def _validate_strict_grounding(value: object) -> bool:
    if not isinstance(value, bool):
        raise InvalidWorkspaceSettingsError("strict_grounding debe ser verdadero o falso.")
    return value


@dataclass(frozen=True)
class RagSettings:
    """Parámetros del motor RAG válidos para un workspace (US07)."""

    similarity_threshold: float
    self_service_threshold: float
    retrieval_top_k: int
    strict_grounding: bool = True

    def __post_init__(self) -> None:
        sim = _validate_similarity(self.similarity_threshold)
        ss = _validate_self_service(self.self_service_threshold, similarity=sim)
        top_k = _validate_top_k(self.retrieval_top_k)
        strict = _validate_strict_grounding(self.strict_grounding)
        object.__setattr__(self, "similarity_threshold", float(sim))
        object.__setattr__(self, "self_service_threshold", float(ss))
        object.__setattr__(self, "retrieval_top_k", top_k)
        object.__setattr__(self, "strict_grounding", strict)


@dataclass(eq=False)
class WorkspaceSettings(AggregateRoot):
    """Raíz de agregado con la configuración editable de un workspace."""

    workspace_id: uuid.UUID
    similarity_threshold: float | None = None
    self_service_threshold: float | None = None
    retrieval_top_k: int | None = None
    strict_grounding: bool | None = None
    updated_at: datetime | None = None
    updated_by: uuid.UUID | None = None

    def __post_init__(self) -> None:
        AggregateRoot.__init__(self)
        sim_dec: Decimal | None = None
        if self.similarity_threshold is not None:
            sim_dec = _validate_similarity(self.similarity_threshold)
            self.similarity_threshold = float(sim_dec)
        if self.self_service_threshold is not None:
            ss_dec = _validate_self_service(self.self_service_threshold, similarity=sim_dec)
            self.self_service_threshold = float(ss_dec)
        if self.retrieval_top_k is not None:
            self.retrieval_top_k = _validate_top_k(self.retrieval_top_k)
        if self.strict_grounding is not None:
            self.strict_grounding = _validate_strict_grounding(self.strict_grounding)

    @classmethod
    def empty(cls, workspace_id: uuid.UUID) -> "WorkspaceSettings":
        """Representa un workspace sin fila guardada: todos los parámetros usan el valor por defecto."""
        return cls(workspace_id=workspace_id)

    @property
    def is_rag_default(self) -> bool:
        """True si las 4 columnas RAG son None (nunca se guardó configuración RAG)."""
        return (
            self.similarity_threshold is None
            and self.self_service_threshold is None
            and self.retrieval_top_k is None
            and self.strict_grounding is None
        )

    def effective_rag(self, defaults: RagSettings) -> RagSettings:
        """Devuelve la configuración RAG efectiva rellenando cualquier None con `defaults`."""
        if self.is_rag_default:
            return defaults
        return RagSettings(
            similarity_threshold=(
                self.similarity_threshold if self.similarity_threshold is not None else defaults.similarity_threshold
            ),
            self_service_threshold=(
                self.self_service_threshold
                if self.self_service_threshold is not None
                else defaults.self_service_threshold
            ),
            retrieval_top_k=(
                self.retrieval_top_k if self.retrieval_top_k is not None else defaults.retrieval_top_k
            ),
            strict_grounding=(
                self.strict_grounding if self.strict_grounding is not None else defaults.strict_grounding
            ),
        )

    def update_rag(
        self,
        new_rag: RagSettings,
        *,
        changed_by: uuid.UUID,
        defaults: RagSettings,
    ) -> bool:
        """Actualiza los parámetros RAG y registra ConfigurationChanged solo si hubo cambios efectivos.

        Devuelve True si cambió al menos un valor efectivo; False si es un guardado sin cambios.
        """
        if not isinstance(new_rag, RagSettings):
            raise InvalidWorkspaceSettingsError("Se esperaba un objeto RagSettings válido.")
        validated = RagSettings(
            similarity_threshold=new_rag.similarity_threshold,
            self_service_threshold=new_rag.self_service_threshold,
            retrieval_top_k=new_rag.retrieval_top_k,
            strict_grounding=new_rag.strict_grounding,
        )
        previous = self.effective_rag(defaults)
        changes: dict[str, dict[str, Any]] = {}
        for field_name in _RAG_FIELDS:
            old_val = getattr(previous, field_name)
            new_val = getattr(validated, field_name)
            if old_val != new_val:
                changes[field_name] = {"old": old_val, "new": new_val}

        if not changes:
            return False

        self.similarity_threshold = validated.similarity_threshold
        self.self_service_threshold = validated.self_service_threshold
        self.retrieval_top_k = validated.retrieval_top_k
        self.strict_grounding = validated.strict_grounding
        self.updated_at = datetime.now(UTC)
        self.updated_by = changed_by
        self.record_event(
            ConfigurationChanged(
                workspace_id=self.workspace_id,
                changed_by=changed_by,
                section="rag",
                changes=changes,
            )
        )
        return True
