"""Pruebas unitarias de DiagnosisGenerationService con un generador simulado (T31)."""
import pytest

from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.ports import IDiagnosisGenerator, InvalidLlmResponseError, LlmProviderError
from app.smart_triage.domain.diagnosis import DiagnosisDraft, DiagnosisStatus
from app.smart_triage.domain.grounding import GroundingEvaluationDomainService, GroundingThresholds
from tests.smart_triage.test_evidence_retrieval_service import masker
from tests.smart_triage.test_grounding import fragment

THRESHOLDS = GroundingThresholds(0.70, 0.85)


class FakeGenerator(IDiagnosisGenerator):
    def __init__(self, draft=None, error: Exception | None = None) -> None:
        self.prompts = []
        self._draft = draft or DiagnosisDraft(True, "Abre los puertos [F1].", ("Reinicia el router [F1].",), (1,))
        self._error = error

    @property
    def model_name(self) -> str:
        return "modelo-falso"

    def generate(self, prompt):
        self.prompts.append(prompt)
        if self._error:
            raise self._error
        return self._draft


def evaluation(*fragments):
    return GroundingEvaluationDomainService().evaluate(fragments, THRESHOLDS)


def service(generator, **kwargs):
    return DiagnosisGenerationService(generator=generator, masker=masker, **kwargs)


def test_low_confidence_never_calls_the_model():
    generator = FakeGenerator()
    outcome = service(generator).generate("la silla rechina", evaluation(fragment(0.60)))
    assert outcome.status is DiagnosisStatus.INSUFFICIENT_EVIDENCE
    assert generator.prompts == []


def test_only_supporting_fragments_are_sent_in_order():
    generator = FakeGenerator()
    strong, medium, weak = fragment(0.90, "A"), fragment(0.75, "B"), fragment(0.50, "C")
    outcome = service(generator).generate("error 809", evaluation(weak, medium, strong))
    prompt = generator.prompts[0]
    assert [f.citation for f in prompt.fragments] == [strong.citation.label, medium.citation.label]
    assert outcome.answered and outcome.diagnosis.sources == (strong,)


def test_fragment_and_incident_text_are_anonymized():
    generator = FakeGenerator()
    leaky = fragment(0.9)
    leaky = leaky.__class__(**{**leaky.__dict__, "content": "Escribe a soporte.vpn@empresa.pe desde 10.0.0.5"})
    service(generator).generate("Soy ana@empresa.pe", evaluation(leaky))
    text = generator.prompts[0].render(masker)
    assert "soporte.vpn@empresa.pe" not in text and "10.0.0.5" not in text and "ana@empresa.pe" not in text


def test_at_most_max_fragments_are_sent():
    generator = FakeGenerator()
    service(generator, max_fragments=2).generate("vpn", evaluation(*(fragment(0.8 + i / 100) for i in range(5))))
    assert len(generator.prompts[0].fragments) == 2


def test_invalid_model_output_is_reported_without_raising():
    outcome = service(FakeGenerator(error=InvalidLlmResponseError("formato inválido"))).generate("vpn", evaluation(fragment(0.8)))
    assert outcome.status is DiagnosisStatus.INVALID_RESPONSE and outcome.reason == "formato inválido"


def test_answers_citing_unknown_fragments_are_discarded():
    draft = DiagnosisDraft(True, "Usa la clave [F4].", ("Paso [F4].",), (4,))
    outcome = service(FakeGenerator(draft)).generate("vpn", evaluation(fragment(0.8)))
    assert outcome.status is DiagnosisStatus.INVALID_RESPONSE


def test_provider_errors_propagate():
    with pytest.raises(LlmProviderError):
        service(FakeGenerator(error=LlmProviderError("503"))).generate("vpn", evaluation(fragment(0.8)))
