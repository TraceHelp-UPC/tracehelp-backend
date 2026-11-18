"""Generación del diagnóstico fundamentado con la IA (US11, T31).

Recibe la evaluación de la evidencia (T30) y:
- si no hay evidencia suficiente, no llama a la IA (no tiene con qué responder);
- si la hay, anonimiza el incidente y el contenido de cada fragmento (los manuales se guardan con el texto
  original), arma el prompt con los fragmentos numerados y valida la respuesta antes de aceptarla.
Los errores del proveedor (LlmProviderError) se propagan: el triaje automático (T28) deja el ticket para un analista.
"""
from app.shared.domain.pii import IPiiMasker
from app.smart_triage.application.grounded_prompt import build_prompt
from app.smart_triage.application.ports import IDiagnosisGenerator, InvalidLlmResponseError
from app.smart_triage.domain.diagnosis import DiagnosisOutcome, DiagnosisStatus, validate_draft
from app.smart_triage.domain.grounding import GroundingEvaluation

DEFAULT_MAX_FRAGMENTS = 5
MAX_INCIDENT_CHARACTERS = 4000


class DiagnosisGenerationService:
    def __init__(
        self, *, generator: IDiagnosisGenerator, masker: IPiiMasker, max_fragments: int = DEFAULT_MAX_FRAGMENTS
    ) -> None:
        self._generator = generator
        self._masker = masker
        self._max_fragments = max_fragments

    def generate(self, incident_text: str, evaluation: GroundingEvaluation) -> DiagnosisOutcome:
        if not evaluation.is_grounded:
            return DiagnosisOutcome(
                DiagnosisStatus.INSUFFICIENT_EVIDENCE,
                reason="Ningún fragmento de los manuales superó el umbral de evidencia.",
            )

        fragments = evaluation.supporting[: self._max_fragments]
        prompt = build_prompt(
            self._masker.mask((incident_text or "").strip()[:MAX_INCIDENT_CHARACTERS]),
            [(f.citation.label, self._masker.mask(f.content)) for f in fragments],
        )
        try:
            draft = self._generator.generate(prompt)
        except InvalidLlmResponseError as exc:
            return DiagnosisOutcome(DiagnosisStatus.INVALID_RESPONSE, reason=str(exc))
        return validate_draft(draft, fragments, model=self._generator.model_name)
