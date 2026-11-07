"""Pruebas del adaptador de diagnóstico de Gemini con un cliente simulado (T31). Nunca llaman a la API real."""
import json
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.smart_triage.application.grounded_prompt import SYSTEM_INSTRUCTION, build_prompt
from app.smart_triage.application.ports import (
    InvalidLlmResponseError,
    LlmProviderError,
    LlmProviderNotConfiguredError,
)
from app.smart_triage.infrastructure.llm.gemini_diagnosis_adapter import DiagnosisPayload, GeminiDiagnosisAdapter
from tests.smart_triage.test_evidence_retrieval_service import masker

VALID = json.dumps(
    {"answerable": True, "summary": "Puertos bloqueados [F1].", "steps": ["Reinicia el router [F1]."], "cited_fragments": [1]}
)


class FakeModels:
    def __init__(self, responses: list) -> None:
        self.calls: list[dict] = []
        self._responses = list(responses)

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        item = self._responses.pop(0)
        if isinstance(item, int):
            raise errors.APIError(item, {"error": {"code": item, "message": "fallo simulado", "status": "X"}})
        return item


def reply(text: str | None, finish_reason: str = "STOP"):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=finish_reason)], prompt_feedback=None)


def adapter(models, **kwargs):
    return GeminiDiagnosisAdapter(api_key="clave-falsa", masker=masker, client=SimpleNamespace(models=models), sleep=lambda _: None, **kwargs)


def prompt():
    return build_prompt(masker.mask("Error 809 en la VPN"), [("Manual.pdf, pág. 1, párr. 17", masker.mask("Abre UDP 500 y 4500."))])


def test_requests_structured_json_with_the_system_instruction():
    models = FakeModels([reply(VALID)])
    draft = adapter(models).generate(prompt())

    assert draft.answerable and draft.cited_fragments == (1,) and draft.steps == ("Reinicia el router [F1].",)
    call = models.calls[0]
    assert call["model"] == "gemini-2.5-flash-lite"
    assert "[F1] Fuente: Manual.pdf, pág. 1, párr. 17" in call["contents"]
    config = call["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is DiagnosisPayload
    assert config.system_instruction == SYSTEM_INSTRUCTION
    assert config.temperature == 0.2


def test_retries_when_gemini_is_rate_limited():
    models = FakeModels([429, 503, reply(VALID)])
    assert adapter(models).generate(prompt()).answerable
    assert len(models.calls) == 3


def test_client_errors_are_not_retried():
    models = FakeModels([400])
    with pytest.raises(LlmProviderError, match="400"):
        adapter(models).generate(prompt())
    assert len(models.calls) == 1


def test_gives_up_after_the_last_attempt():
    with pytest.raises(LlmProviderError):
        adapter(FakeModels([429, 429, 429, 429])).generate(prompt())


@pytest.mark.parametrize("text", ["no es json", json.dumps({"answerable": True, "summary": "x"})])
def test_malformed_output_is_reported(text):
    with pytest.raises(InvalidLlmResponseError):
        adapter(FakeModels([reply(text)])).generate(prompt())


def test_blocked_response_is_reported_with_its_reason():
    with pytest.raises(InvalidLlmResponseError, match="SAFETY"):
        adapter(FakeModels([reply(None, "SAFETY")])).generate(prompt())


def test_missing_api_key():
    with pytest.raises(LlmProviderNotConfiguredError):
        GeminiDiagnosisAdapter(api_key="", masker=masker).generate(prompt())
