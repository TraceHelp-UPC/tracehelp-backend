"""Pruebas unitarias de calibración de umbrales de similitud y evaluación de evidencia RAG (US11, T33)."""
import pytest

from app.core.config import Settings
from app.smart_triage.domain.enums import ConfidenceLevel
from app.smart_triage.domain.exceptions import InvalidConfidenceThresholdError
from app.smart_triage.domain.grounding_evaluation import GroundingEvaluationDomainService
from app.smart_triage.domain.value_objects import (
    DEFAULT_MIN_EVIDENCE_THRESHOLD,
    DEFAULT_SELF_SERVICE_THRESHOLD,
    ConfidenceScore,
    SimilarityThresholds,
    SourceCitation,
)


def test_default_calibrated_thresholds_are_070_and_085():
    settings = Settings()
    thresholds = SimilarityThresholds(
        min_evidence_threshold=settings.rag_min_evidence_threshold,
        self_service_threshold=settings.rag_self_service_threshold,
    )
    assert thresholds.min_evidence_threshold == 0.70 == DEFAULT_MIN_EVIDENCE_THRESHOLD
    assert thresholds.self_service_threshold == 0.85 == DEFAULT_SELF_SERVICE_THRESHOLD


def test_high_confidence_query_qualifies_for_self_service():
    service = GroundingEvaluationDomainService()
    citations = [
        SourceCitation(source_file="manual_vpn.pdf", page_number=4, paragraph_number=2, similarity_score=0.89),
        SourceCitation(source_file="manual_vpn.pdf", page_number=5, paragraph_number=1, similarity_score=0.76),
    ]

    result = service.evaluate(citations)

    assert result.has_sufficient_evidence is True
    assert result.is_low_confidence_alert is False
    assert result.can_propose_self_service is True
    assert result.confidence_level is ConfidenceLevel.HIGH_SELF_SERVICE
    assert len(result.qualified_citations) == 2


def test_medium_confidence_between_070_and_085_requires_analyst_assistance():
    service = GroundingEvaluationDomainService()
    citations = [
        SourceCitation(source_file="guia_sap.pdf", page_number=12, paragraph_number=3, similarity_score=0.78),
        SourceCitation(source_file="guia_sap.pdf", page_number=14, paragraph_number=1, similarity_score=0.52),
    ]

    result = service.evaluate(citations)

    assert result.has_sufficient_evidence is True
    assert result.is_low_confidence_alert is False
    assert result.can_propose_self_service is False
    assert result.confidence_level is ConfidenceLevel.MEDIUM_ASSISTED
    assert len(result.qualified_citations) == 1


def test_below_070_threshold_triggers_low_confidence_alert_and_blocks_llm():
    service = GroundingEvaluationDomainService()
    citations = [
        SourceCitation(source_file="manual_correo.pdf", page_number=2, paragraph_number=1, similarity_score=0.64),
    ]

    result = service.evaluate(citations)

    assert result.has_sufficient_evidence is False
    assert result.is_low_confidence_alert is True
    assert result.can_propose_self_service is False
    assert result.confidence_level is ConfidenceLevel.LOW_CONFIDENCE_ALERT
    assert result.qualified_citations == ()


def test_empty_sources_returns_insufficient_evidence():
    service = GroundingEvaluationDomainService()
    result = service.evaluate([])

    assert result.has_sufficient_evidence is False
    assert result.is_low_confidence_alert is True
    assert result.confidence_level is ConfidenceLevel.INSUFFICIENT_EVIDENCE
    assert result.confidence_score.value == 0.0


@pytest.mark.parametrize(
    ("min_ev", "self_srv"),
    [(-0.1, 0.85), (0.70, 1.2), (0.90, 0.80)],
)
def test_invalid_thresholds_raise_domain_error(min_ev, self_srv):
    with pytest.raises(InvalidConfidenceThresholdError):
        SimilarityThresholds(min_evidence_threshold=min_ev, self_service_threshold=self_srv)


def test_out_of_range_confidence_score_raises_domain_error():
    with pytest.raises(InvalidConfidenceThresholdError):
        ConfidenceScore(1.05)
