"""Pruebas unitarias de consumo de parámetros RAG y strict_grounding en Smart Triage (US07, T62)."""
import uuid

from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.evidence_retrieval_service import (
    EvidenceRetrievalService,
    RetrieveEvidenceCommand,
)
from app.smart_triage.application.ports import IRagParametersProvider, RagParameters
from app.smart_triage.domain.diagnosis import DiagnosisDraft, DiagnosisStatus, validate_draft
from app.smart_triage.domain.events import LowConfidenceAlertRaised
from app.smart_triage.domain.grounding import (
    ConfidenceLevel,
    GroundingEvaluationDomainService,
    GroundingThresholds,
)
from app.smart_triage.domain.triage_diagnosis import ReviewStatus, TicketRoute, TriageDiagnosis
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator
from tests.smart_triage.test_evidence_retrieval_service import FakeRetriever, masker
from tests.smart_triage.test_grounding import fragment

WORKSPACE = uuid.uuid4()
TICKET = uuid.uuid4()


class MutableRagProvider(IRagParametersProvider):
    def __init__(self, initial: RagParameters) -> None:
        self.by_workspace: dict[uuid.UUID, RagParameters] = {}
        self.default = initial

    def for_workspace(self, workspace_id: uuid.UUID) -> RagParameters:
        return self.by_workspace.get(workspace_id, self.default)


def test_evidence_retrieval_resolves_parameters_on_every_call():
    provider = MutableRagProvider(RagParameters(0.68, 0.80, 5, True))
    retriever = FakeRetriever(0.70)
    bus = InMemoryEventBus()
    alerts: list[LowConfidenceAlertRaised] = []
    bus.subscribe(LowConfidenceAlertRaised, alerts.append)
    service = EvidenceRetrievalService(retriever=retriever, masker=masker, events=bus, parameters=provider)

    # Con 0.68, un fragmento de 0.70 es GROUNDED y usa top_k=5
    first = service.retrieve_and_evaluate(RetrieveEvidenceCommand(WORKSPACE, "error 809 vpn"))
    assert first.level is ConfidenceLevel.GROUNDED
    assert first.strict_grounding is True
    assert retriever.calls[-1][2] == 5
    assert alerts == []

    # Cambiar los parámetros surte efecto inmediato sin reconstruir el servicio
    provider.by_workspace[WORKSPACE] = RagParameters(0.72, 0.85, 8, False)
    second = service.retrieve_and_evaluate(RetrieveEvidenceCommand(WORKSPACE, "error 809 vpn", ticket_id=TICKET))
    assert second.level is ConfidenceLevel.LOW_CONFIDENCE
    assert second.strict_grounding is False
    assert retriever.calls[-1][2] == 8
    assert len(alerts) == 1 and alerts[0].similarity_threshold == 0.72

    # command.top_k sigue teniendo prioridad sobre retrieval_top_k del workspace
    service.retrieve_and_evaluate(RetrieveEvidenceCommand(WORKSPACE, "error 809 vpn", top_k=2))
    assert retriever.calls[-1][2] == 2


def test_validate_draft_allows_uncited_answer_only_when_strict_grounding_is_disabled():
    fragments = (fragment(0.92, "Manual VPN"), fragment(0.85, "Manual Red"))
    uncited = DiagnosisDraft(
        answerable=True,
        summary="Reinicia el servicio VPN.",
        steps=("Cierra el cliente VPN.", "Vuelve a conectar."),
        cited_fragments=(),
    )

    strict_outcome = validate_draft(uncited, fragments, model="gemini", require_citations=True)
    assert strict_outcome.status is DiagnosisStatus.INVALID_RESPONSE

    relaxed_outcome = validate_draft(uncited, fragments, model="gemini", require_citations=False)
    assert relaxed_outcome.status is DiagnosisStatus.ANSWERED
    assert relaxed_outcome.diagnosis is not None
    assert relaxed_outcome.diagnosis.sources == ()

    # Incluso con strict_grounding=False, las citas a fragmentos inexistentes se rechazan siempre
    hallucinated = DiagnosisDraft(
        answerable=True,
        summary="Reinicia el router [F9].",
        steps=("Paso [F9].",),
        cited_fragments=(9,),
    )
    bad_outcome = validate_draft(hallucinated, fragments, model="gemini", require_citations=False)
    assert bad_outcome.status is DiagnosisStatus.INVALID_RESPONSE


def test_relaxed_grounding_without_citations_never_proposes_self_service():
    evaluation = GroundingEvaluationDomainService().evaluate(
        [fragment(0.95)],
        GroundingThresholds(0.68, 0.80),
        strict_grounding=False,
    )
    uncited_draft = DiagnosisDraft(
        answerable=True,
        summary="Abre los puertos UDP 500 y 4500.",
        steps=("Revisa las reglas del router.",),
        cited_fragments=(),
    )
    outcome = DiagnosisGenerationService(generator=FakeGenerator(uncited_draft), masker=masker).generate(
        "error 809", evaluation
    )
    assert outcome.status is DiagnosisStatus.ANSWERED
    assert outcome.diagnosis is not None and outcome.diagnosis.sources == ()

    diagnosis = TriageDiagnosis.from_analysis(
        workspace_id=WORKSPACE,
        ticket_id=TICKET,
        evaluation=evaluation,
        outcome=outcome,
        ocr=None,
    )
    assert diagnosis.review_status is ReviewStatus.PENDING_REVIEW
    assert diagnosis.route is TicketRoute.PENDING_ASSIGNMENT
    assert diagnosis.sources == ()


def test_diagnosis_generation_forwards_more_than_five_supporting_fragments_by_default():
    fragments = [fragment(0.70 + i * 0.02, f"Doc {i}") for i in range(8)]
    evaluation = GroundingEvaluationDomainService().evaluate(fragments, GroundingThresholds(0.68, 0.80))
    generator = FakeGenerator()

    DiagnosisGenerationService(generator=generator, masker=masker).generate("error 809", evaluation)

    assert len(generator.prompts[0].fragments) == 8


def test_strict_grounding_discards_uncited_draft_as_invalid_response():
    evaluation = GroundingEvaluationDomainService().evaluate(
        [fragment(0.95)],
        GroundingThresholds(0.68, 0.80),
        strict_grounding=True,
    )
    uncited_draft = DiagnosisDraft(
        answerable=True,
        summary="Abre los puertos UDP 500 y 4500.",
        steps=("Revisa las reglas del router.",),
        cited_fragments=(),
    )
    outcome = DiagnosisGenerationService(generator=FakeGenerator(uncited_draft), masker=masker).generate(
        "error 809", evaluation
    )
    assert outcome.status is DiagnosisStatus.INVALID_RESPONSE
    assert outcome.diagnosis is None

    diagnosis = TriageDiagnosis.from_analysis(
        workspace_id=WORKSPACE,
        ticket_id=TICKET,
        evaluation=evaluation,
        outcome=outcome,
        ocr=None,
    )
    assert diagnosis.outcome is DiagnosisStatus.INVALID_RESPONSE
    assert diagnosis.review_status is ReviewStatus.NOT_APPLICABLE
    assert diagnosis.route is TicketRoute.PENDING_ASSIGNMENT
    assert diagnosis.sources == ()


def test_build_evidence_retrieval_service_wires_iam_rag_parameters():
    from app.smart_triage.infrastructure.iam.iam_rag_parameters import IamRagParametersProvider
    from app.smart_triage.interfaces.rest.dependencies import build_evidence_retrieval_service

    service = build_evidence_retrieval_service(session=None, events=InMemoryEventBus())  # type: ignore[arg-type]
    assert isinstance(service._parameters, IamRagParametersProvider)
