"""Pruebas unitarias del análisis multimodal (T28) con OCR, búsqueda y generador simulados."""
import uuid

import pytest

from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.evidence_retrieval_service import EvidenceRetrievalService
from app.smart_triage.application.ports import IOcrExtractor
from app.smart_triage.application.triage_analysis_service import AnalyzeIncidentCommand, TriageAnalysisService
from app.smart_triage.domain.diagnosis import DiagnosisStatus
from app.smart_triage.domain.exceptions import IllegibleImageError, MissingIncidentDataError
from app.smart_triage.domain.grounding import GroundingThresholds
from app.smart_triage.domain.value_objects import OcrExtractionResult
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator
from tests.smart_triage.test_evidence_retrieval_service import FakeRetriever, masker

WORKSPACE = uuid.uuid4()
LEGIBLE = OcrExtractionResult.from_text(
    "VPN Error 809: no se pudo conectar al servidor", mean_confidence=90, confident_word_count=8
)
ILLEGIBLE = OcrExtractionResult.from_text("", mean_confidence=10, confident_word_count=0)


class FakeOcr(IOcrExtractor):
    def __init__(self, *results):
        self._results = list(results)

    def extract(self, content):
        return self._results.pop(0)


def build(ocr=None, scores=(0.80,), generator=None):
    retriever = FakeRetriever(*scores)
    generator = generator or FakeGenerator()
    service = TriageAnalysisService(
        ocr=ocr or FakeOcr(),
        retrieval=EvidenceRetrievalService(
            retriever=retriever, masker=masker, events=InMemoryEventBus(), thresholds=GroundingThresholds(0.70, 0.85)
        ),
        generation=DiagnosisGenerationService(generator=generator, masker=masker),
    )
    return service, retriever, generator


def test_screenshot_text_and_error_codes_enrich_the_search():
    service, retriever, _ = build(ocr=FakeOcr(LEGIBLE))
    analysis = service.analyze(
        AnalyzeIncidentCommand(WORKSPACE, "No puedo conectarme desde casa", title="VPN", screenshots=(b"png",))
    )
    query = retriever.calls[0][1].text
    assert "Asunto: VPN" in query and "Descripción: No puedo conectarme desde casa" in query
    assert "Texto de la captura: VPN Error 809" in query and "Códigos de error: Error 809" in query
    assert analysis.error_codes == ("Error 809",) and analysis.screenshots_legible
    assert analysis.outcome.status is DiagnosisStatus.ANSWERED


def test_text_only_incidents_are_analyzed():
    service, retriever, _ = build()
    analysis = service.analyze(AnalyzeIncidentCommand(WORKSPACE, "Outlook me pide la contraseña una y otra vez"))
    assert analysis.ocr_results == () and retriever.calls


def test_a_legible_screenshot_is_enough_without_description():
    service, _, _ = build(ocr=FakeOcr(LEGIBLE))
    analysis = service.analyze(AnalyzeIncidentCommand(WORKSPACE, None, screenshots=(b"png",)))
    assert analysis.outcome.status is DiagnosisStatus.ANSWERED


def test_illegible_screenshot_without_description_is_rejected():
    service, retriever, _ = build(ocr=FakeOcr(ILLEGIBLE))
    with pytest.raises(IllegibleImageError):
        service.analyze(AnalyzeIncidentCommand(WORKSPACE, "error", screenshots=(b"png",)))
    assert retriever.calls == []


def test_illegible_screenshot_with_a_good_description_continues():
    service, _, _ = build(ocr=FakeOcr(ILLEGIBLE))
    analysis = service.analyze(
        AnalyzeIncidentCommand(WORKSPACE, "La VPN no conecta desde mi casa", screenshots=(b"png",))
    )
    assert not analysis.screenshots_legible and "Texto de la captura" not in analysis.incident_text


@pytest.mark.parametrize("description", [None, "", "   "])
def test_missing_description_and_screenshot_is_rejected(description):
    service, _, _ = build()
    with pytest.raises(MissingIncidentDataError):
        service.analyze(AnalyzeIncidentCommand(WORKSPACE, description))


def test_too_short_description_is_rejected():
    service, _, _ = build()
    with pytest.raises(MissingIncidentDataError):
        service.analyze(AnalyzeIncidentCommand(WORKSPACE, "error"))


def test_low_confidence_does_not_call_the_model():
    service, _, generator = build(scores=(0.40,))
    analysis = service.analyze(AnalyzeIncidentCommand(WORKSPACE, "La silla de mi escritorio rechina"))
    assert analysis.outcome.status is DiagnosisStatus.INSUFFICIENT_EVIDENCE and generator.prompts == []
