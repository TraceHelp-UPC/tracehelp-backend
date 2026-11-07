"""Pruebas unitarias de GroundingEvaluationDomainService (T30, US11)."""
import uuid

import pytest

from app.smart_triage.domain.grounding import (
    ConfidenceLevel,
    EvidenceCitation,
    EvidenceFragment,
    GroundingEvaluationDomainService,
    GroundingThresholds,
    InvalidGroundingConfigurationError,
)

THRESHOLDS = GroundingThresholds(similarity=0.70, self_service=0.85)


def fragment(score: float, section: str = "Error 809") -> EvidenceFragment:
    return EvidenceFragment(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="guia-vpn",
        content="Abre los puertos UDP 500 y 4500.",
        citation=EvidenceCitation(source_file="guia-vpn.md", paragraph_number=1, section_title=section),
        similarity=score,
    )


def evaluate(*scores: float):
    return GroundingEvaluationDomainService().evaluate([fragment(s) for s in scores], THRESHOLDS)


def test_strong_evidence_allows_self_service():
    result = evaluate(0.91, 0.72, 0.40)
    assert result.level is ConfidenceLevel.SELF_SERVICE
    assert result.allows_self_service and result.is_grounded and not result.requires_low_confidence_alert
    assert [f.similarity for f in result.supporting] == [0.91, 0.72]


def test_evidence_between_thresholds_is_grounded_but_needs_an_analyst():
    result = evaluate(0.78, 0.65)
    assert result.level is ConfidenceLevel.GROUNDED
    assert result.is_grounded and not result.allows_self_service
    assert len(result.supporting) == 1


def test_no_fragment_over_the_threshold_raises_low_confidence():
    result = evaluate(0.69, 0.50)
    assert result.level is ConfidenceLevel.LOW_CONFIDENCE
    assert result.requires_low_confidence_alert and result.supporting == ()
    assert result.best_score == 0.69


def test_no_fragments_at_all_is_low_confidence():
    result = evaluate()
    assert result.level is ConfidenceLevel.LOW_CONFIDENCE and result.best_score == 0.0


@pytest.mark.parametrize(("score", "level"), [(0.70, ConfidenceLevel.GROUNDED), (0.85, ConfidenceLevel.SELF_SERVICE)])
def test_thresholds_are_inclusive(score, level):
    assert evaluate(score).level is level


def test_fragments_are_sorted_by_similarity():
    result = evaluate(0.2, 0.9, 0.5)
    assert [f.similarity for f in result.retrieved] == [0.9, 0.5, 0.2]


@pytest.mark.parametrize(("similarity", "self_service"), [(0, 0.85), (0.70, 1.2), (0.90, 0.80)])
def test_incoherent_thresholds_are_rejected(similarity, self_service):
    with pytest.raises(InvalidGroundingConfigurationError):
        GroundingThresholds(similarity=similarity, self_service=self_service)


@pytest.mark.parametrize(
    ("citation", "label"),
    [
        (EvidenceCitation("Manual_VPN.pdf", 3, page_number=12), "Manual_VPN.pdf, pág. 12, párr. 3"),
        (EvidenceCitation("guia-vpn.md", 1, section_title="Error 809"), "guia-vpn.md, sección «Error 809», párr. 1"),
        (EvidenceCitation("notas.md", 2), "notas.md, párr. 2"),
    ],
)
def test_citation_label(citation, label):
    assert citation.label == label
