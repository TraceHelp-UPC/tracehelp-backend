"""Análisis multimodal de un incidente (TS02, T28).

Orquesta, en este orden:
1. OCR local de las capturas (T26): el texto y los códigos de error se suman a la descripción;
2. recuperación y evaluación de la evidencia (T30), que anonimiza la consulta antes de vectorizarla;
3. diagnóstico fundamentado con Gemini (T31), solo si la evidencia supera el umbral.
Lo usan el endpoint POST /triage/analyze y el triaje automático de tickets.
"""
import uuid
from dataclasses import dataclass, field

from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.evidence_retrieval_service import EvidenceRetrievalService, RetrieveEvidenceCommand
from app.smart_triage.application.ports import IOcrExtractor
from app.smart_triage.domain.diagnosis import DiagnosisOutcome
from app.smart_triage.domain.exceptions import IllegibleImageError, MissingIncidentDataError
from app.smart_triage.domain.grounding import GroundingEvaluation
from app.smart_triage.domain.value_objects import OcrExtractionResult

MIN_DESCRIPTION_CHARACTERS = 10  # menos que esto no alcanza para buscar si la captura tampoco se lee


@dataclass(frozen=True)
class AnalyzeIncidentCommand:
    workspace_id: uuid.UUID
    description: str | None
    title: str | None = None
    affected_module: str | None = None
    screenshots: tuple[bytes, ...] = field(default=(), repr=False)
    ticket_id: uuid.UUID | None = None


@dataclass(frozen=True)
class IncidentAnalysis:
    incident_text: str
    ocr_results: tuple[OcrExtractionResult, ...]
    evaluation: GroundingEvaluation
    outcome: DiagnosisOutcome

    @property
    def error_codes(self) -> tuple[str, ...]:
        codes: list[str] = []
        for result in self.ocr_results:
            codes.extend(c for c in result.error_codes if c not in codes)
        return tuple(codes)

    @property
    def screenshots_legible(self) -> bool:
        return any(r.is_legible for r in self.ocr_results)

    @property
    def ocr_text(self) -> str:
        return "\n".join(r.text for r in self.ocr_results if r.is_legible and r.text)


def compose_incident_text(command: AnalyzeIncidentCommand, ocr_results: tuple[OcrExtractionResult, ...]) -> str:
    parts = []
    if command.title and command.title.strip():
        parts.append(f"Asunto: {command.title.strip()}")
    if command.affected_module and command.affected_module.strip():
        parts.append(f"Sistema afectado: {command.affected_module.strip()}")
    if command.description and command.description.strip():
        parts.append(f"Descripción: {command.description.strip()}")
    legible = [r for r in ocr_results if r.is_legible and r.text]
    if legible:
        parts.append("Texto de la captura: " + " ".join(r.text.replace("\n", " ") for r in legible))
    codes = []
    for result in ocr_results:
        codes.extend(c for c in result.error_codes if c not in codes)
    if codes:
        parts.append("Códigos de error: " + ", ".join(codes))
    return "\n".join(parts)


class TriageAnalysisService:
    def __init__(
        self,
        *,
        ocr: IOcrExtractor,
        retrieval: EvidenceRetrievalService,
        generation: DiagnosisGenerationService,
    ) -> None:
        self._ocr = ocr
        self._retrieval = retrieval
        self._generation = generation

    def analyze(self, command: AnalyzeIncidentCommand) -> IncidentAnalysis:
        """Lanza MissingIncidentDataError, InvalidScreenshotError o IllegibleImageError (400) si no hay qué analizar.

        Los errores del proveedor de IA (EmbeddingProviderError, LlmProviderError) se propagan.
        """
        description = (command.description or "").strip()
        if not description and not command.screenshots:
            raise MissingIncidentDataError("Describe el problema o adjunta una captura del error.")

        ocr_results = tuple(self._ocr.extract(content) for content in command.screenshots)
        if len(description) < MIN_DESCRIPTION_CHARACTERS and not any(r.is_legible for r in ocr_results):
            if command.screenshots:
                raise IllegibleImageError()
            raise MissingIncidentDataError("Describe el problema con más detalle para poder buscar una solución.")

        incident_text = compose_incident_text(command, ocr_results)
        evaluation = self._retrieval.retrieve_and_evaluate(
            RetrieveEvidenceCommand(
                workspace_id=command.workspace_id, query_text=incident_text, ticket_id=command.ticket_id
            )
        )
        outcome = self._generation.generate(incident_text, evaluation)
        return IncidentAnalysis(
            incident_text=incident_text, ocr_results=ocr_results, evaluation=evaluation, outcome=outcome
        )
