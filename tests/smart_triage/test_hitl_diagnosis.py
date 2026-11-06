"""Pruebas unitarias y de integración para TriageDiagnosis, acciones HITL y endpoints REST (US11, US15, TS07)."""
import uuid

import pytest

from app.smart_triage.domain.enums import ConfidenceLevel, ValidationStatus
from app.smart_triage.domain.exceptions import (
    InvalidTriageReviewError,
    TriageDiagnosisAlreadyReviewedError,
)
from app.smart_triage.domain.triage_diagnosis import TriageDiagnosis
from app.smart_triage.domain.value_objects import SourceCitation


def _make_diagnosis_with_evidence() -> TriageDiagnosis:
    return TriageDiagnosis.evaluate_and_create(
        workspace_id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        query_text="No puedo conectar la VPN corporativa",
        citations=[
            SourceCitation(
                source_file="manual_vpn.pdf",
                page_number=4,
                paragraph_number=2,
                similarity_score=0.89,
            )
        ],
        synthesized_answer="Reinicie el cliente VPN y verifique el puerto 443.",
    )


def test_approve_hitl_marks_diagnosis_approved_and_emits_event():
    diagnosis = _make_diagnosis_with_evidence()
    diagnosis.pull_events()
    reviewer_id = uuid.uuid4()

    diagnosis.approve_hitl(reviewer_id)

    assert diagnosis.validation_status is ValidationStatus.APPROVED
    assert diagnosis.final_approved_text == "Reinicie el cliente VPN y verifique el puerto 443."
    assert diagnosis.reviewer_id == reviewer_id
    events = diagnosis.pull_events()
    assert len(events) == 1
    assert events[0].action == "APPROVE"


def test_edit_and_approve_hitl_stores_modified_text():
    diagnosis = _make_diagnosis_with_evidence()
    diagnosis.pull_events()
    reviewer_id = uuid.uuid4()

    diagnosis.edit_and_approve_hitl(reviewer_id, "Actualice el certificado TLS y reconecte.")

    assert diagnosis.validation_status is ValidationStatus.EDITED
    assert diagnosis.final_approved_text == "Actualice el certificado TLS y reconecte."


def test_reject_hitl_clears_final_text():
    diagnosis = _make_diagnosis_with_evidence()
    diagnosis.pull_events()
    reviewer_id = uuid.uuid4()

    diagnosis.reject_hitl(reviewer_id, reason="No corresponde al sistema operativo del usuario")

    assert diagnosis.validation_status is ValidationStatus.REJECTED
    assert diagnosis.final_approved_text is None


def test_manual_resolution_on_low_confidence_diagnosis():
    diagnosis = TriageDiagnosis.evaluate_and_create(
        workspace_id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        query_text="Fallo no documentado",
        citations=[],
    )
    assert diagnosis.confidence_level is ConfidenceLevel.INSUFFICIENT_EVIDENCE
    diagnosis.pull_events()

    diagnosis.provide_manual_resolution(uuid.uuid4(), "Se reemplazó el cable de red en sitio.")

    assert diagnosis.validation_status is ValidationStatus.MANUAL_ONLY
    assert diagnosis.final_approved_text == "Se reemplazó el cable de red en sitio."


def test_cannot_review_already_reviewed_diagnosis():
    diagnosis = _make_diagnosis_with_evidence()
    diagnosis.approve_hitl(uuid.uuid4())

    with pytest.raises(TriageDiagnosisAlreadyReviewedError):
        diagnosis.reject_hitl(uuid.uuid4())


def test_cannot_approve_automatically_without_evidence():
    diagnosis = TriageDiagnosis.evaluate_and_create(
        workspace_id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        query_text="Sin fuentes",
        citations=[],
    )
    with pytest.raises(InvalidTriageReviewError):
        diagnosis.approve_hitl(uuid.uuid4())
