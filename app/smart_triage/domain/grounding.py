"""Evaluación de la evidencia recuperada antes de generar una respuesta (US11, T30).

GroundingEvaluationDomainService decide si los fragmentos de los manuales sostienen una respuesta:
- similitud >= umbral de evidencia (0.70 por defecto): el fragmento puede usarse como fuente;
- mejor similitud >= umbral de autoservicio (0.85 por defecto): se puede proponer la solución al colaborador;
- ningún fragmento sobre el umbral de evidencia: baja confianza, no se genera respuesta y decide un analista.
Los valores por defecto se calibran en T33.
"""
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.shared.domain.exceptions import DomainError

DEFAULT_SIMILARITY_THRESHOLD = 0.70
DEFAULT_SELF_SERVICE_THRESHOLD = 0.85


class InvalidGroundingConfigurationError(DomainError):
    """Los umbrales configurados no son coherentes."""


class ConfidenceLevel(StrEnum):
    SELF_SERVICE = "SELF_SERVICE"  # evidencia fuerte: se puede proponer la solución al colaborador
    GROUNDED = "GROUNDED"  # evidencia suficiente: la respuesta la valida un analista (HITL)
    LOW_CONFIDENCE = "LOW_CONFIDENCE"  # sin evidencia suficiente: no se genera respuesta


@dataclass(frozen=True)
class GroundingThresholds:
    similarity: float = DEFAULT_SIMILARITY_THRESHOLD
    self_service: float = DEFAULT_SELF_SERVICE_THRESHOLD

    def __post_init__(self) -> None:
        if not 0 < self.similarity <= 1 or not 0 < self.self_service <= 1:
            raise InvalidGroundingConfigurationError("Los umbrales de similitud deben estar entre 0 y 1.")
        if self.self_service < self.similarity:
            raise InvalidGroundingConfigurationError(
                "El umbral de autoservicio no puede ser menor que el umbral de evidencia."
            )


@dataclass(frozen=True)
class EvidenceCitation:
    """Dónde está el fragmento en el manual: archivo, página (solo PDF), sección y párrafo."""

    source_file: str
    paragraph_number: int
    page_number: int | None = None
    section_title: str | None = None

    @property
    def label(self) -> str:
        parts = [self.source_file]
        if self.page_number is not None:
            parts.append(f"pág. {self.page_number}")
        elif self.section_title:
            parts.append(f"sección «{self.section_title}»")
        parts.append(f"párr. {self.paragraph_number}")
        return ", ".join(parts)


@dataclass(frozen=True)
class EvidenceFragment:
    """Fragmento de un manual recuperado por similitud coseno con la consulta."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_title: str
    content: str
    citation: EvidenceCitation
    similarity: float

    def __post_init__(self) -> None:
        if not -1.0001 <= self.similarity <= 1.0001:
            raise ValueError(f"La similitud coseno debe estar entre -1 y 1 y es {self.similarity}.")


@dataclass(frozen=True)
class GroundingEvaluation:
    """Resultado de evaluar la evidencia. `supporting` son los fragmentos que pueden citarse en la respuesta."""

    level: ConfidenceLevel
    best_score: float
    thresholds: GroundingThresholds
    retrieved: tuple[EvidenceFragment, ...]
    supporting: tuple[EvidenceFragment, ...]

    @property
    def is_grounded(self) -> bool:
        return self.level is not ConfidenceLevel.LOW_CONFIDENCE

    @property
    def allows_self_service(self) -> bool:
        return self.level is ConfidenceLevel.SELF_SERVICE

    @property
    def requires_low_confidence_alert(self) -> bool:
        return self.level is ConfidenceLevel.LOW_CONFIDENCE


class GroundingEvaluationDomainService:
    """Clasifica la evidencia recuperada según los umbrales configurados."""

    def evaluate(self, fragments: Iterable[EvidenceFragment], thresholds: GroundingThresholds) -> GroundingEvaluation:
        retrieved = tuple(sorted(fragments, key=lambda f: f.similarity, reverse=True))
        supporting = tuple(f for f in retrieved if f.similarity >= thresholds.similarity)
        best = retrieved[0].similarity if retrieved else 0.0

        if not supporting:
            level = ConfidenceLevel.LOW_CONFIDENCE
        elif best >= thresholds.self_service:
            level = ConfidenceLevel.SELF_SERVICE
        else:
            level = ConfidenceLevel.GROUNDED
        return GroundingEvaluation(
            level=level, best_score=round(best, 4), thresholds=thresholds, retrieved=retrieved, supporting=supporting
        )
