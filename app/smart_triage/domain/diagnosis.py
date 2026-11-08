"""Diagnóstico generado por la IA a partir de los manuales (US11, T31).

La IA solo puede responder con los fragmentos que le entregamos. Antes de aceptar su respuesta se valida que:
- tenga un resumen y entre 1 y MAX_STEPS pasos;
- cite al menos un fragmento, y que todas las citas ([F1], [F2], ...) correspondan a fragmentos entregados.
Una respuesta que no cumple se descarta: el ticket lo atiende un analista.
"""
import re
from dataclasses import dataclass
from enum import StrEnum

from app.smart_triage.domain.grounding import EvidenceFragment

MAX_STEPS = 8
MAX_SUMMARY_CHARACTERS = 600
MAX_STEP_CHARACTERS = 500
_MARKER = re.compile(r"\[F(\d+)\]")


class DiagnosisStatus(StrEnum):
    ANSWERED = "ANSWERED"  # la IA respondió con citas válidas
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # no se llamó a la IA: la evidencia no superó el umbral
    MODEL_DECLINED = "MODEL_DECLINED"  # la IA indicó que los fragmentos no responden la consulta
    INVALID_RESPONSE = "INVALID_RESPONSE"  # la IA respondió sin citas válidas o con un formato no aceptado
    PROVIDER_ERROR = "PROVIDER_ERROR"  # Gemini no respondió (cuota, red o clave faltante); decide un analista


@dataclass(frozen=True)
class DiagnosisDraft:
    """Respuesta de la IA tal como llega, antes de validarla."""

    answerable: bool
    summary: str
    steps: tuple[str, ...]
    cited_fragments: tuple[int, ...]


@dataclass(frozen=True)
class GeneratedDiagnosis:
    """Diagnóstico validado: cada fuente es un fragmento real del manual, con su cita."""

    summary: str
    steps: tuple[str, ...]
    sources: tuple[EvidenceFragment, ...]
    model: str

    @property
    def citation_labels(self) -> tuple[str, ...]:
        return tuple(f.citation.label for f in self.sources)


@dataclass(frozen=True)
class DiagnosisOutcome:
    status: DiagnosisStatus
    diagnosis: GeneratedDiagnosis | None = None
    reason: str | None = None

    @property
    def answered(self) -> bool:
        return self.status is DiagnosisStatus.ANSWERED


def validate_draft(draft: DiagnosisDraft, fragments: tuple[EvidenceFragment, ...], *, model: str) -> DiagnosisOutcome:
    """Convierte la respuesta de la IA en un diagnóstico, o explica por qué se descarta."""
    if not draft.answerable:
        return DiagnosisOutcome(
            DiagnosisStatus.MODEL_DECLINED, reason="La IA indicó que los manuales no responden esta consulta."
        )

    summary = (draft.summary or "").strip()
    steps = tuple(s.strip() for s in draft.steps if s and s.strip())
    if not summary:
        return _invalid("La respuesta no tiene resumen.")
    if not steps:
        return _invalid("La respuesta no tiene pasos de solución.")
    if len(steps) > MAX_STEPS:
        return _invalid(f"La respuesta tiene más de {MAX_STEPS} pasos.")
    if len(summary) > MAX_SUMMARY_CHARACTERS or any(len(s) > MAX_STEP_CHARACTERS for s in steps):
        return _invalid("La respuesta es demasiado larga.")

    valid = range(1, len(fragments) + 1)
    inline = {int(n) for text in (summary, *steps) for n in _MARKER.findall(text)}
    cited = set(draft.cited_fragments) | inline
    if not cited:
        return _invalid("La respuesta no cita ningún fragmento del manual.")
    unknown = sorted(n for n in cited if n not in valid)
    if unknown:
        return _invalid(f"La respuesta cita fragmentos que no se entregaron: {', '.join(f'F{n}' for n in unknown)}.")

    sources = tuple(fragments[n - 1] for n in sorted(cited))
    return DiagnosisOutcome(
        DiagnosisStatus.ANSWERED, diagnosis=GeneratedDiagnosis(summary=summary, steps=steps, sources=sources, model=model)
    )


def _invalid(reason: str) -> DiagnosisOutcome:
    return DiagnosisOutcome(DiagnosisStatus.INVALID_RESPONSE, reason=reason)
