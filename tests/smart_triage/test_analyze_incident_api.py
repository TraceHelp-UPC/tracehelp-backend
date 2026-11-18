"""Pruebas de integración de POST /triage/analyze (T28). Requieren TEST_DATABASE_URL.

La búsqueda usa pgvector con vectores por palabras y Gemini se simula. La prueba con captura usa Tesseract real
y se omite si no está instalado (corre dentro de Docker).
"""
import io

import pytest
from PIL import Image

from app.main import app
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.triage_analysis_service import TriageAnalysisService
from app.smart_triage.infrastructure.ocr.tesseract_ocr_adapter import TesseractOcrAdapter
from app.smart_triage.interfaces.rest.dependencies import get_triage_analysis_service
from tests.knowledge.test_ingestion_pipeline import masker
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator
from tests.smart_triage.test_evidence_search_api import kb  # noqa: F401 - fixture reutilizada
from tests.smart_triage.test_ocr_adapter import _screenshot, needs_tesseract

URL = "/api/v1/triage/analyze"


@pytest.fixture()
def analyze(api_client, kb):  # noqa: F811
    generator = FakeGenerator()
    app.dependency_overrides[get_triage_analysis_service] = lambda: TriageAnalysisService(
        ocr=TesseractOcrAdapter(),
        retrieval=kb["service"],
        generation=DiagnosisGenerationService(generator=generator, masker=masker),
    )
    yield {"client": api_client, "kb": kb, "generator": generator}
    app.dependency_overrides.pop(get_triage_analysis_service, None)


def _post(analyze, who="analyst", files=None, **form):
    data = {"workspace_id": str(analyze["kb"]["workspace"].id), **form}
    return analyze["client"].post(URL, data=data, files=files, headers=analyze["kb"]["headers"][who])


def test_text_incident_returns_diagnosis_citations_and_confidence(analyze):
    response = _post(analyze, description="Me sale el error 809 en la vpn, los puertos udp 500 y 4500")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ANSWERED"
    assert body["confidence_score"] > body["similarity_threshold"]
    assert body["diagnosis"]["sources"][0]["citation"] == "guia-vpn.md, sección «Error 809», párr. 1"
    assert body["ocr"] == {"screenshot_received": False, "legible": None, "error_codes": [], "feedback": None}


@needs_tesseract
def test_screenshot_text_and_error_codes_are_used(analyze):
    files = {"screenshot": ("error.png", _screenshot(), "image/png")}
    body = _post(analyze, files=files, description="No puedo entrar a la red de la empresa").json()
    assert body["ocr"]["screenshot_received"] and body["ocr"]["legible"]
    assert "Error 809" in body["ocr"]["error_codes"] and "0x80070005" in body["ocr"]["error_codes"]
    prompt = analyze["generator"].prompts[0].render(masker)
    assert "Códigos de error:" in prompt and "Error 809" in prompt


def test_unrelated_incident_returns_low_confidence(analyze):
    body = _post(analyze, description="La silla de mi escritorio rechina mucho").json()
    assert body["status"] == "INSUFFICIENT_EVIDENCE" and body["confidence_level"] == "LOW_CONFIDENCE"
    assert body["diagnosis"] is None and analyze["generator"].prompts == []


@pytest.mark.parametrize("form", [{}, {"description": "   "}, {"description": "error"}])
def test_missing_parameters_return_400(analyze, form):
    response = _post(analyze, **form)
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")


def test_invalid_image_returns_400(analyze):
    files = {"screenshot": ("error.png", b"esto no es una imagen", "image/png")}
    assert _post(analyze, files=files, description="La VPN no conecta desde casa").status_code == 400


@needs_tesseract
def test_illegible_screenshot_without_description_returns_400(analyze):
    buffer = io.BytesIO()
    Image.new("RGB", (400, 200), "white").save(buffer, format="PNG")
    response = _post(analyze, files={"screenshot": ("blanco.png", buffer.getvalue(), "image/png")})
    assert response.status_code == 400
    assert "captura" in response.json()["detail"]


def test_unknown_workspace_returns_404(analyze):
    import uuid

    response = analyze["client"].post(
        URL,
        data={"workspace_id": str(uuid.uuid4()), "description": "La VPN no conecta desde casa"},
        headers=analyze["kb"]["headers"]["analyst"],
    )
    assert response.status_code == 404


def test_collaborators_cannot_call_the_analysis(analyze):
    assert _post(analyze, who="collaborator", description="La VPN no conecta").status_code == 403


def test_automatic_triage_is_wired_to_ticket_registration(monkeypatch):
    from app.core.config import get_settings
    from app.core.event_handlers import register_event_handlers
    from app.helpdesk.domain.events import TicketRegistered
    from app.smart_triage.domain.events import TriageCompleted

    monkeypatch.setattr(get_settings(), "triage_worker_enabled", True)
    monkeypatch.setattr(get_settings(), "ingestion_worker_enabled", False)
    bus = InMemoryEventBus()
    register_event_handlers(bus)
    assert any(getattr(h, "__name__", "") == "on_ticket_registered" for h in bus.handlers_for(TicketRegistered))
    assert any(type(h).__name__ == "TriageRoutingHandler" for h in bus.handlers_for(TriageCompleted))
