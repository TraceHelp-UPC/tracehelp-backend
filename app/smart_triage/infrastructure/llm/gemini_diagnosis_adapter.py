"""Diagnóstico con Google Gemini (gemini-2.5-flash-lite) (T31, LlmProviderAclAdapter).

- Verifica el sello de anonimización de todo el texto antes de enviarlo (GroundedPrompt.render).
- Pide la respuesta en JSON con un esquema fijo (structured output) y temperatura baja.
- Reintenta con espera exponencial si Gemini responde 429 (cuota del plan gratuito) o un error 5xx.
- Una respuesta bloqueada, vacía o con otro formato se informa como InvalidLlmResponseError.
En las pruebas se reemplaza el cliente por un doble; nunca se llama a la API real.
"""
import logging
import time
from collections.abc import Callable

from pydantic import BaseModel, Field, ValidationError

from app.shared.domain.pii import IPiiMasker
from app.smart_triage.application.grounded_prompt import GroundedPrompt
from app.smart_triage.application.ports import (
    IDiagnosisGenerator,
    InvalidLlmResponseError,
    LlmProviderError,
    LlmProviderNotConfiguredError,
)
from app.smart_triage.domain.diagnosis import DiagnosisDraft

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class DiagnosisPayload(BaseModel):
    """Esquema JSON que se le exige a Gemini."""

    answerable: bool = Field(description="false si los fragmentos no explican cómo resolver el incidente")
    summary: str = Field(description="Causa probable y solución en una o dos oraciones")
    steps: list[str] = Field(description="Pasos de solución; cada uno termina con su cita, por ejemplo [F1]")
    cited_fragments: list[int] = Field(description="Números de los fragmentos usados, por ejemplo [1, 3]")


class GeminiDiagnosisAdapter(IDiagnosisGenerator):
    def __init__(
        self,
        *,
        api_key: str,
        masker: IPiiMasker,
        model: str = "gemini-2.5-flash-lite",
        client=None,
        sleep: Callable[[float], None] = time.sleep,
        base_delay_seconds: float = 2.0,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> None:
        self._api_key = api_key
        self._masker = masker
        self._model = model
        self._client = client
        self._sleep = sleep
        self._base_delay = base_delay_seconds
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, prompt: GroundedPrompt) -> DiagnosisDraft:
        from google.genai import errors, types

        contents = prompt.render(self._masker)  # lanza UnsealedTextError si algo no está anonimizado
        client = self._get_client()
        config = types.GenerateContentConfig(
            system_instruction=prompt.system_instruction,
            response_mime_type="application/json",
            response_schema=DiagnosisPayload,
            temperature=self._temperature,
            max_output_tokens=self._max_output_tokens,
        )
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                response = client.models.generate_content(model=self._model, contents=contents, config=config)
                break
            except errors.APIError as exc:
                if exc.code not in RETRYABLE_STATUS or attempt == MAX_ATTEMPTS:
                    raise LlmProviderError(f"Gemini respondió {exc.code}: {exc.message}") from exc
                delay = self._base_delay * 2 ** (attempt - 1)
                logger.warning("Gemini respondió %s; reintento %s de %s en %.0f s", exc.code, attempt, MAX_ATTEMPTS, delay)
                self._sleep(delay)
            except Exception as exc:  # noqa: BLE001 - errores de red del SDK
                if attempt == MAX_ATTEMPTS:
                    raise LlmProviderError(f"No se pudo conectar con Gemini: {exc}") from exc
                self._sleep(self._base_delay * 2 ** (attempt - 1))

        text = getattr(response, "text", None)
        if not text:
            reason = _finish_reason(response)
            raise InvalidLlmResponseError(f"Gemini no devolvió texto (motivo: {reason}).")
        try:
            payload = DiagnosisPayload.model_validate_json(text)
        except ValidationError as exc:
            raise InvalidLlmResponseError("Gemini devolvió una respuesta que no cumple el formato JSON pedido.") from exc
        return DiagnosisDraft(
            answerable=payload.answerable,
            summary=payload.summary,
            steps=tuple(payload.steps),
            cited_fragments=tuple(payload.cited_fragments),
        )

    def _get_client(self):
        if self._client is None:
            if not self._api_key:
                raise LlmProviderNotConfiguredError("GEMINI_API_KEY no está configurada.")
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client


def _finish_reason(response) -> str:
    candidates = getattr(response, "candidates", None) or []
    if candidates and getattr(candidates[0], "finish_reason", None):
        return str(candidates[0].finish_reason)
    feedback = getattr(response, "prompt_feedback", None)
    if feedback and getattr(feedback, "block_reason", None):
        return f"bloqueado ({feedback.block_reason})"
    return "desconocido"
