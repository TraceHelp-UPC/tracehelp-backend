"""Servicio de dominio de evaluación de fundamentación (grounding) y calibración de umbrales (US11, T30, T33)."""
from dataclasses import dataclass

from app.smart_triage.domain.enums import ConfidenceLevel
from app.smart_triage.domain.value_objects import ConfidenceScore, SimilarityThresholds, SourceCitation


@dataclass(frozen=True)
class GroundingEvaluationResult:
    """Resultado de evaluar los fragmentos recuperados contra los umbrales calibrados (0.70 y 0.85)."""

    confidence_score: ConfidenceScore
    confidence_level: ConfidenceLevel
    has_sufficient_evidence: bool
    is_low_confidence_alert: bool
    can_propose_self_service: bool
    qualified_citations: tuple[SourceCitation, ...]


class GroundingEvaluationDomainService:
    """Evalúa la evidencia recuperada contra los umbrales calibrados (0.70 y 0.85) para evitar alucinaciones."""

    def __init__(self, thresholds: SimilarityThresholds | None = None) -> None:
        self._thresholds = thresholds or SimilarityThresholds()

    @property
    def thresholds(self) -> SimilarityThresholds:
        return self._thresholds

    def evaluate(self, citations: list[SourceCitation] | tuple[SourceCitation, ...]) -> GroundingEvaluationResult:
        if not citations:
            return GroundingEvaluationResult(
                confidence_score=ConfidenceScore(0.0),
                confidence_level=ConfidenceLevel.INSUFFICIENT_EVIDENCE,
                has_sufficient_evidence=False,
                is_low_confidence_alert=True,
                can_propose_self_service=False,
                qualified_citations=(),
            )

        best_score = max(c.similarity_score for c in citations)
        qualified = tuple(c for c in citations if c.similarity_score >= self._thresholds.min_evidence_threshold)
        score = ConfidenceScore(best_score)
        level = score.classify(self._thresholds)
        sufficient = bool(qualified) and score.meets_minimum_evidence(self._thresholds)

        return GroundingEvaluationResult(
            confidence_score=score,
            confidence_level=level,
            has_sufficient_evidence=sufficient,
            is_low_confidence_alert=not sufficient,
            can_propose_self_service=sufficient and score.qualifies_for_self_service(self._thresholds),
            qualified_citations=qualified,
        )
