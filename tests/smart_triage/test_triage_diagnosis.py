"""Pruebas unitarias del agregado TriageDiagnosis y de la ruta del ticket (T28)."""
import uuid

from app.smart_triage.domain.diagnosis import DiagnosisOutcome, DiagnosisStatus, GeneratedDiagnosis
from app.smart_triage.domain.events import TriageCompleted
from app.smart_triage.domain.grounding import ConfidenceLevel, GroundingEvaluationDomainService, GroundingThresholds
from app.smart_triage.domain.triage_diagnosis import OcrSummary, ReviewStatus, TicketRoute, TriageDiagnosis
from tests.smart_triage.test_grounding import fragment

THRESHOLDS = GroundingThresholds(0.70, 0.85)
WORKSPACE, TICKET = uuid.uuid4(), uuid.uuid4()


def _diagnosis(evaluation, status=DiagnosisStatus.ANSWERED, sources=None):
    generated = None
    if status is DiagnosisStatus.ANSWERED:
        generated = GeneratedDiagnosis(
            summary="Puertos bloqueados [F1].",
            steps=("Reinicia el router [F1].",),
            sources=sources if sources is not None else evaluation.supporting[:1],
            model="gemini-3.5-flash-lite",
        )
    return TriageDiagnosis.from_analysis(
        workspace_id=WORKSPACE,
        ticket_id=TICKET,
        evaluation=evaluation,
        outcome=DiagnosisOutcome(status, diagnosis=generated, reason=None if generated else "motivo"),
        ocr=OcrSummary(legible=True, error_codes=("Error 809",), masked_text="VPN Error 809"),
    )


def evaluate(*scores):
    return GroundingEvaluationDomainService().evaluate([fragment(s) for s in scores], THRESHOLDS)


def test_strong_evidence_with_an_answer_is_proposed_to_the_collaborator():
    diagnosis = _diagnosis(evaluate(0.91, 0.75))
    assert diagnosis.review_status is ReviewStatus.SELF_SERVICE_PROPOSED
    assert diagnosis.route is TicketRoute.SELF_SERVICE_PROPOSED
    assert diagnosis.sources[0].reference == "F1" and diagnosis.sources[0].similarity == 0.91


def test_medium_evidence_with_an_answer_waits_for_an_analyst():
    diagnosis = _diagnosis(evaluate(0.78))
    assert diagnosis.review_status is ReviewStatus.PENDING_REVIEW
    assert diagnosis.route is TicketRoute.PENDING_ASSIGNMENT
    assert diagnosis.summary and diagnosis.model == "gemini-3.5-flash-lite"


def test_cited_sources_keep_their_prompt_reference():
    evaluation = evaluate(0.90, 0.80)
    diagnosis = _diagnosis(evaluation, sources=(evaluation.supporting[1],))
    assert [s.reference for s in diagnosis.sources] == ["F2"]


def test_no_answer_goes_to_the_assignment_queue():
    for status in (DiagnosisStatus.INSUFFICIENT_EVIDENCE, DiagnosisStatus.MODEL_DECLINED, DiagnosisStatus.INVALID_RESPONSE):
        diagnosis = _diagnosis(evaluate(0.91), status=status)
        assert diagnosis.review_status is ReviewStatus.NOT_APPLICABLE
        assert diagnosis.route is TicketRoute.PENDING_ASSIGNMENT
        assert diagnosis.summary is None and diagnosis.sources == ()


def test_failed_triage_goes_to_the_assignment_queue():
    diagnosis = TriageDiagnosis.failed(workspace_id=WORKSPACE, ticket_id=TICKET, reason="Gemini respondió 503")
    assert diagnosis.outcome is DiagnosisStatus.PROVIDER_ERROR
    assert diagnosis.confidence_level is None and diagnosis.route is TicketRoute.PENDING_ASSIGNMENT


def test_emits_triage_completed_with_the_route():
    diagnosis = _diagnosis(evaluate(0.78))
    [event] = diagnosis.pull_events()
    assert isinstance(event, TriageCompleted)
    assert (event.ticket_id, event.diagnosis_id, event.route) == (TICKET, diagnosis.id, "PENDING_ASSIGNMENT")
    assert (event.outcome, event.confidence_level, event.best_score) == ("ANSWERED", ConfidenceLevel.GROUNDED.value, 0.78)
