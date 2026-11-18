"""Pruebas unitarias de la validación de la respuesta de la IA (T31)."""
import pytest

from app.smart_triage.domain.diagnosis import MAX_STEPS, DiagnosisDraft, DiagnosisStatus, validate_draft
from tests.smart_triage.test_grounding import fragment

FRAGMENTS = (fragment(0.82, "Error 809"), fragment(0.75, "Error 691"))


def draft(**changes) -> DiagnosisDraft:
    values = {
        "answerable": True,
        "summary": "El router bloquea los puertos de la VPN [F1].",
        "steps": ("Reinicia el router [F1].", "Conéctate desde los datos del celular [F1]."),
        "cited_fragments": (1,),
    }
    return DiagnosisDraft(**(values | changes))


def test_valid_answer_keeps_only_the_cited_fragments_as_sources():
    outcome = validate_draft(draft(), FRAGMENTS, model="gemini-3.5-flash-lite")
    assert outcome.status is DiagnosisStatus.ANSWERED
    assert outcome.diagnosis.sources == (FRAGMENTS[0],)
    assert outcome.diagnosis.model == "gemini-3.5-flash-lite"


def test_inline_markers_count_as_citations():
    outcome = validate_draft(
        draft(cited_fragments=(), summary="Clave precompartida mal escrita.", steps=("Revisa la clave [F2].",)), FRAGMENTS, model="m"
    )
    assert outcome.answered and outcome.diagnosis.sources == (FRAGMENTS[1],)


def test_model_can_decline_to_answer():
    outcome = validate_draft(draft(answerable=False, steps=(), cited_fragments=()), FRAGMENTS, model="m")
    assert outcome.status is DiagnosisStatus.MODEL_DECLINED and outcome.diagnosis is None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"cited_fragments": (), "summary": "Sin citas.", "steps": ("Reinicia el router.",)}, "no cita"),
        ({"cited_fragments": (3,)}, "F3"),
        ({"steps": ("Usa la clave del manual [F7].",)}, "F7"),
        ({"summary": "  "}, "resumen"),
        ({"steps": ("", "  ")}, "pasos"),
        ({"steps": tuple(f"Paso {i} [F1]" for i in range(MAX_STEPS + 1))}, "más de"),
        ({"summary": "x" * 601}, "larga"),
    ],
)
def test_invalid_answers_are_discarded(changes, reason):
    outcome = validate_draft(draft(**changes), FRAGMENTS, model="m")
    assert outcome.status is DiagnosisStatus.INVALID_RESPONSE and outcome.diagnosis is None
    assert reason in outcome.reason
