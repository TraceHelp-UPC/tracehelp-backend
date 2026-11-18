"""Pruebas de integración de POST /triage/diagnosis-preview (T31). Requieren TEST_DATABASE_URL.

La búsqueda usa pgvector con los vectores por palabras de las pruebas de ingesta y Gemini se reemplaza por un
generador simulado: así se prueba el flujo completo sin llamar a la API real.
"""
import pytest

from app.main import app
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.domain.diagnosis import DiagnosisDraft
from app.smart_triage.interfaces.rest.dependencies import (
    get_diagnosis_generation_service,
    get_evidence_retrieval_service,
)
from tests.knowledge.test_ingestion_pipeline import masker
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator
from tests.smart_triage.test_evidence_search_api import kb  # noqa: F401 - fixture reutilizada

URL = "/api/v1/triage/diagnosis-preview"


@pytest.fixture()
def preview(api_client, kb):  # noqa: F811
    generator = FakeGenerator(
        DiagnosisDraft(
            answerable=True,
            summary="El firewall bloquea los puertos de la VPN [F1].",
            steps=("Abre los puertos UDP 500 y 4500 en el router [F1].", "O conéctate desde otra red [F1]."),
            cited_fragments=(1,),
        )
    )
    app.dependency_overrides[get_evidence_retrieval_service] = lambda: kb["service"]
    app.dependency_overrides[get_diagnosis_generation_service] = lambda: DiagnosisGenerationService(
        generator=generator, masker=masker
    )
    yield {"client": api_client, "generator": generator, "headers": kb["headers"]}
    app.dependency_overrides.pop(get_evidence_retrieval_service, None)
    app.dependency_overrides.pop(get_diagnosis_generation_service, None)


def test_returns_a_diagnosis_with_real_citations(preview):
    response = preview["client"].post(
        URL,
        json={"incident": "me sale el error 809 en la vpn, los puertos udp 500 y 4500. Soy ana.diaz@empresa.pe"},
        headers=preview["headers"]["analyst"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ANSWERED" and body["reason"] is None
    diagnosis = body["diagnosis"]
    assert diagnosis["steps"][0].endswith("[F1].")
    assert diagnosis["sources"] == [
        {
            "reference": "F1",
            "citation": "guia-vpn.md, sección «Error 809», párr. 1",
            "document_title": "guia-vpn",
            "similarity": body["best_score"],
        }
    ]
    prompt_text = preview["generator"].prompts[0].render(masker)
    assert "ana.diaz@empresa.pe" not in prompt_text
    assert "[F1] Fuente: guia-vpn.md, sección «Error 809», párr. 1" in prompt_text


def test_low_confidence_does_not_call_the_model(preview):
    body = preview["client"].post(URL, json={"incident": "la silla rechina"}, headers=preview["headers"]["leader"]).json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE" and body["diagnosis"] is None
    assert body["confidence_level"] == "LOW_CONFIDENCE"
    assert preview["generator"].prompts == []


def test_collaborators_cannot_use_the_preview(preview):
    response = preview["client"].post(URL, json={"incident": "vpn"}, headers=preview["headers"]["collaborator"])
    assert response.status_code == 403


def test_missing_gemini_key_returns_503(api_client, kb, monkeypatch):  # noqa: F811
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    response = api_client.post(URL, json={"incident": "error 809"}, headers=kb["headers"]["analyst"])
    assert response.status_code == 503 and "GEMINI_API_KEY" in response.json()["detail"]
