"""Pruebas unitarias de las acciones HITL sobre TriageDiagnosis (T35)."""
import uuid

import pytest

from app.smart_triage.domain.diagnosis import DiagnosisStatus
from app.smart_triage.domain.events import AiResolutionReviewed
from app.smart_triage.domain.triage_diagnosis import (
    DiagnosisAlreadyReviewedError,
    InvalidReviewError,
    ReviewStatus,
    TriageDiagnosis,
)
from tests.smart_triage.test_triage_diagnosis import _diagnosis, evaluate

ANALYST = uuid.uuid4()


def pending() -> TriageDiagnosis:
    diagnosis = _diagnosis(evaluate(0.78))
    diagnosis.pull_events()
    assert diagnosis.review_status is ReviewStatus.PENDING_REVIEW
    return diagnosis


def without_answer() -> TriageDiagnosis:
    diagnosis = _diagnosis(evaluate(0.50), status=DiagnosisStatus.INSUFFICIENT_EVIDENCE)
    diagnosis.pull_events()
    return diagnosis


def test_approve_keeps_the_ai_text_as_final_response():
    diagnosis = pending()
    diagnosis.approve(ANALYST)
    assert diagnosis.review_status is ReviewStatus.APPROVED and diagnosis.resolves_ticket
    assert (diagnosis.reviewed_by, diagnosis.final_summary, diagnosis.final_steps) == (
        ANALYST, diagnosis.summary, diagnosis.steps,
    )
    assert diagnosis.final_response_text() == (
        "Puertos bloqueados [F1].\n\n1. Reinicia el router [F1].\n\nFuentes: [F1] guia-vpn.md, sección «Error 809», párr. 1"
    )


def test_edit_and_approve_keeps_the_original_for_the_audit():
    diagnosis = pending()
    diagnosis.edit_and_approve(ANALYST, summary=" Router bloquea la VPN. ", steps=["Reinicia el router.", " ", "Usa datos móviles."])
    assert diagnosis.review_status is ReviewStatus.EDITED_AND_APPROVED
    assert diagnosis.final_summary == "Router bloquea la VPN."
    assert diagnosis.final_steps == ("Reinicia el router.", "Usa datos móviles.")
    assert diagnosis.summary == "Puertos bloqueados [F1]."  # la versión de la IA no se pierde


@pytest.mark.parametrize(
    ("summary", "steps"),
    [("", ["Paso"]), ("Resumen", []), ("Resumen", ["x" * 501]), ("x" * 601, ["Paso"]), ("Resumen", ["Paso"] * 9)],
)
def test_invalid_edits_are_rejected(summary, steps):
    with pytest.raises(InvalidReviewError):
        pending().edit_and_approve(ANALYST, summary=summary, steps=steps)


def test_reject_requires_a_reason_and_keeps_the_ticket_open():
    diagnosis = pending()
    with pytest.raises(InvalidReviewError):
        diagnosis.reject(ANALYST, reason=" ")
    diagnosis.reject(ANALYST, reason="El manual habla de otra versión de la VPN")
    assert diagnosis.review_status is ReviewStatus.REJECTED and not diagnosis.resolves_ticket
    assert diagnosis.review_note == "El manual habla de otra versión de la VPN"
    assert diagnosis.final_response_text() is None


def test_manual_response_after_a_rejection():
    diagnosis = pending()
    diagnosis.reject(ANALYST, reason="Respuesta incompleta")
    diagnosis.respond_manually(ANALYST, response="Reinstalé el perfil VPN de forma remota; prueba de nuevo.")
    assert diagnosis.review_status is ReviewStatus.MANUAL_RESPONSE and diagnosis.resolves_ticket
    assert diagnosis.final_response_text() == "Reinstalé el perfil VPN de forma remota; prueba de nuevo."


def test_manual_response_when_the_ai_did_not_answer():
    diagnosis = without_answer()
    diagnosis.respond_manually(ANALYST, response="Se cambió la silla por una nueva.")
    assert diagnosis.review_status is ReviewStatus.MANUAL_RESPONSE


@pytest.mark.parametrize("response", ["", "corto", "x" * 4001])
def test_invalid_manual_responses_are_rejected(response):
    with pytest.raises(InvalidReviewError):
        without_answer().respond_manually(ANALYST, response=response)


@pytest.mark.parametrize("action", ["approve", "edit", "reject"])
def test_without_an_ai_answer_only_a_manual_response_is_possible(action):
    diagnosis = without_answer()
    with pytest.raises(DiagnosisAlreadyReviewedError, match="solo se puede responder manualmente"):
        {
            "approve": lambda: diagnosis.approve(ANALYST),
            "edit": lambda: diagnosis.edit_and_approve(ANALYST, summary="S", steps=["P"]),
            "reject": lambda: diagnosis.reject(ANALYST, reason="No aplica"),
        }[action]()


def test_a_review_cannot_be_repeated():
    diagnosis = pending()
    diagnosis.approve(ANALYST)
    with pytest.raises(DiagnosisAlreadyReviewedError, match="APPROVED"):
        diagnosis.approve(ANALYST)
    with pytest.raises(DiagnosisAlreadyReviewedError):
        diagnosis.respond_manually(ANALYST, response="Otra respuesta para el colaborador")


def test_self_service_proposals_are_not_reviewed_by_analysts():
    diagnosis = _diagnosis(evaluate(0.91))
    with pytest.raises(DiagnosisAlreadyReviewedError, match="autoservicio"):
        diagnosis.approve(ANALYST)


def test_each_review_publishes_ai_resolution_reviewed():
    diagnosis = pending()
    diagnosis.reject(ANALYST, reason="No corresponde al error")
    [event] = diagnosis.pull_events()
    assert isinstance(event, AiResolutionReviewed)
    assert (event.decision, event.previous_status, event.ai_outcome) == ("REJECT", "PENDING_REVIEW", "ANSWERED")
    assert (event.reviewer_id, event.resolves_ticket, event.note) == (ANALYST, False, "No corresponde al error")
