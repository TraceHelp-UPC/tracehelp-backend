"""Embeddings con Google Gemini (gemini-embedding-001, 768 dimensiones) (T23, EmbeddingProviderAclAdapter).

- Solo acepta SanitizedText con sello válido: verifica la anonimización antes de enviar (T27).
- Envía lotes de hasta 100 textos por llamada, el máximo de la API.
- Normaliza los vectores, porque Gemini solo los entrega normalizados con 3072 dimensiones.
- Reintenta con espera exponencial si Gemini responde 429 (cuota del plan gratuito) o un error 5xx.
En las pruebas se reemplaza el cliente por un doble; nunca se llama a la API real.
"""
import logging
import time
from collections.abc import Callable, Sequence

from app.knowledge.application.ports import (
    EmbeddingProviderError,
    EmbeddingProviderNotConfiguredError,
    IEmbeddingGenerator,
)
from app.knowledge.domain.value_objects import EMBEDDING_DIMENSIONS, VectorEmbedding
from app.shared.domain.pii import IPiiMasker, SanitizedText, ensure_sealed

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
MAX_ATTEMPTS = 5
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class GeminiEmbeddingAdapter(IEmbeddingGenerator):
    def __init__(
        self,
        *,
        api_key: str,
        masker: IPiiMasker,
        model: str = "gemini-embedding-001",
        dimensions: int = EMBEDDING_DIMENSIONS,
        client=None,
        sleep: Callable[[float], None] = time.sleep,
        base_delay_seconds: float = 2.0,
    ) -> None:
        if dimensions != EMBEDDING_DIMENSIONS:
            raise ValueError(f"La columna de pgvector es vector({EMBEDDING_DIMENSIONS}); EMBEDDING_DIMENSIONS debe coincidir.")
        self._api_key = api_key
        self._masker = masker
        self._model = model
        self._dimensions = dimensions
        self._client = client
        self._sleep = sleep
        self._base_delay = base_delay_seconds

    def embed_documents(self, texts: Sequence[SanitizedText]) -> list[VectorEmbedding]:
        plain = [ensure_sealed(t, self._masker) for t in texts]
        vectors: list[VectorEmbedding] = []
        for start in range(0, len(plain), BATCH_SIZE):
            vectors.extend(self._embed(plain[start : start + BATCH_SIZE], task_type="RETRIEVAL_DOCUMENT"))
        return vectors

    def embed_query(self, text: SanitizedText) -> VectorEmbedding:
        return self._embed([ensure_sealed(text, self._masker)], task_type="RETRIEVAL_QUERY")[0]

    # ------------------------------------------------------------------ llamada a Gemini
    def _get_client(self):
        if self._client is None:
            if not self._api_key:
                raise EmbeddingProviderNotConfiguredError("GEMINI_API_KEY no está configurada.")
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _embed(self, texts: list[str], *, task_type: str) -> list[VectorEmbedding]:
        from google.genai import errors, types

        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self._dimensions)
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = self._get_client().models.embed_content(model=self._model, contents=texts, config=config)
                break
            except errors.APIError as exc:
                if exc.code not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                    raise EmbeddingProviderError(f"Gemini respondió {exc.code}: {exc.message}") from exc
                delay = self._base_delay * 2 ** (attempt - 1)
                logger.warning("Gemini respondió %s; reintento %s de %s en %.0f s", exc.code, attempt, MAX_ATTEMPTS, delay)
                self._sleep(delay)
            except EmbeddingProviderError:
                raise
            except Exception as exc:  # noqa: BLE001 - errores de red del SDK
                if attempt == MAX_ATTEMPTS:
                    raise EmbeddingProviderError(f"No se pudo conectar con Gemini: {exc}") from exc
                self._sleep(self._base_delay * 2 ** (attempt - 1))

        embeddings = list(response.embeddings or [])
        if len(embeddings) != len(texts):
            raise EmbeddingProviderError(f"Gemini devolvió {len(embeddings)} vectores para {len(texts)} textos.")
        return [VectorEmbedding.normalized(e.values) for e in embeddings]
