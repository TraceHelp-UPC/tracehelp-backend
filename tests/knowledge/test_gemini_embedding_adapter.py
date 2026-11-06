"""Pruebas del adaptador de embeddings de Gemini con un cliente simulado (T23). Nunca llaman a la API real."""
import math
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.knowledge.application.ports import EmbeddingProviderError
from app.knowledge.domain.value_objects import EMBEDDING_DIMENSIONS
from app.knowledge.infrastructure.embeddings.gemini_embedding_adapter import GeminiEmbeddingAdapter
from app.shared.domain.pii import SanitizedText, UnsealedTextError
from app.shared.infrastructure.pii_masker import RegexSpacyPiiMasker

masker = RegexSpacyPiiMasker("clave-de-pruebas-del-sello-pii-0123456789", spacy_model=None)


class FakeModels:
    def __init__(self, failures: list[int] | None = None) -> None:
        self.calls: list[dict] = []
        self._failures = list(failures or [])

    def embed_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        if self._failures:
            code = self._failures.pop(0)
            raise errors.APIError(code, {"error": {"code": code, "message": "fallo simulado", "status": "X"}})
        # Vectores sin normalizar (como los entrega Gemini con 768 dimensiones)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[3.0] + [4.0] + [0.0] * (EMBEDDING_DIMENSIONS - 2)) for _ in contents])


def _adapter(models: FakeModels, **kwargs) -> GeminiEmbeddingAdapter:
    return GeminiEmbeddingAdapter(
        api_key="clave-falsa", masker=masker, client=SimpleNamespace(models=models), sleep=lambda _: None, **kwargs
    )


def test_embeds_documents_with_768_normalized_dimensions():
    models = FakeModels()
    vectors = _adapter(models).embed_documents(masker.mask_many(["Paso 1: abre la VPN", "Paso 2: reinicia"]))

    assert len(vectors) == 2
    assert vectors[0].dimensions == EMBEDDING_DIMENSIONS
    assert math.isclose(sum(v * v for v in vectors[0].values), 1.0)
    call = models.calls[0]
    assert call["model"] == "gemini-embedding-001"
    assert call["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert call["config"].output_dimensionality == 768


def test_sends_batches_of_at_most_100_texts():
    models = FakeModels()
    vectors = _adapter(models).embed_documents(masker.mask_many([f"fragmento {i}" for i in range(250)]))
    assert len(vectors) == 250
    assert [len(c["contents"]) for c in models.calls] == [100, 100, 50]


def test_query_uses_retrieval_query_task():
    models = FakeModels()
    _adapter(models).embed_query(masker.mask("No conecta la VPN, error 809"))
    assert models.calls[0]["config"].task_type == "RETRIEVAL_QUERY"


def test_only_anonymized_text_is_sent():
    models = FakeModels()
    _adapter(models).embed_documents(masker.mask_many(["Escribe a soporte@empresa.pe desde 10.4.2.18"]))
    assert models.calls[0]["contents"] == ["Escribe a [REDACTED_EMAIL] desde [REDACTED_IP]"]


def test_rejects_text_without_a_valid_seal():
    models = FakeModels()
    forged = SanitizedText(text="mi correo es ana@empresa.pe", audit_seal="hmac-sha256:v1:falso")
    with pytest.raises(UnsealedTextError):
        _adapter(models).embed_documents([forged])
    assert models.calls == []


def test_retries_when_gemini_rate_limits():
    models = FakeModels(failures=[429, 503])
    vectors = _adapter(models).embed_documents(masker.mask_many(["texto"]))
    assert len(vectors) == 1 and len(models.calls) == 3


def test_gives_up_after_the_last_attempt():
    models = FakeModels(failures=[429] * 5)
    with pytest.raises(EmbeddingProviderError, match="429"):
        _adapter(models).embed_documents(masker.mask_many(["texto"]))


def test_client_errors_are_not_retried():
    models = FakeModels(failures=[400])
    with pytest.raises(EmbeddingProviderError, match="400"):
        _adapter(models).embed_documents(masker.mask_many(["texto"]))
    assert len(models.calls) == 1


def test_missing_api_key_is_reported():
    adapter = GeminiEmbeddingAdapter(api_key="", masker=masker)
    with pytest.raises(EmbeddingProviderError, match="GEMINI_API_KEY"):
        adapter.embed_documents(masker.mask_many(["texto"]))


def test_dimensions_must_match_the_pgvector_column():
    with pytest.raises(ValueError):
        GeminiEmbeddingAdapter(api_key="x", masker=masker, dimensions=1536)
