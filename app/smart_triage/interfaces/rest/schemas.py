"""DTOs del contexto Smart Triage."""
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.knowledge.application.knowledge_retrieval_service import MAX_TOP_K
from app.smart_triage.application.diagnosis_query_service import DiagnosisView
from app.smart_triage.application.evidence_retrieval_service import MAX_QUERY_CHARACTERS
from app.smart_triage.application.triage_analysis_service import IncidentAnalysis
from app.smart_triage.domain.diagnosis import DiagnosisOutcome
from app.smart_triage.domain.grounding import EvidenceFragment, GroundingEvaluation
from app.smart_triage.domain.triage_diagnosis import ReviewDecision


class EvidenceSearchRequest(BaseModel):
    query: str = Field(
        ..., min_length=1, max_length=MAX_QUERY_CHARACTERS, examples=["Me sale el error 809 al conectarme a la VPN"]
    )
    top_k: int | None = Field(None, ge=1, le=MAX_TOP_K, description="Fragmentos a recuperar (por defecto RETRIEVAL_TOP_K)")


class EvidenceFragmentResponse(BaseModel):
    document_id: str
    document_title: str
    citation: str = Field(..., examples=["guia-vpn.md, sección «Error 809», párr. 1"])
    source_file: str
    page_number: int | None
    section_title: str | None
    paragraph_number: int
    content: str
    similarity: float
    supports_answer: bool = Field(..., description="True si supera el umbral de evidencia y puede citarse")

    @classmethod
    def from_fragment(cls, f: EvidenceFragment, threshold: float) -> "EvidenceFragmentResponse":
        return cls(
            document_id=str(f.document_id),
            document_title=f.document_title,
            citation=f.citation.label,
            source_file=f.citation.source_file,
            page_number=f.citation.page_number,
            section_title=f.citation.section_title,
            paragraph_number=f.citation.paragraph_number,
            content=f.content,
            similarity=f.similarity,
            supports_answer=f.similarity >= threshold,
        )


class EvidenceSearchResponse(BaseModel):
    confidence_level: str = Field(..., examples=["GROUNDED"], description="SELF_SERVICE, GROUNDED o LOW_CONFIDENCE")
    best_score: float
    similarity_threshold: float
    self_service_threshold: float
    low_confidence_alert: bool
    fragments: list[EvidenceFragmentResponse]

    @classmethod
    def from_evaluation(cls, e: GroundingEvaluation) -> "EvidenceSearchResponse":
        return cls(
            confidence_level=e.level.value,
            best_score=e.best_score,
            similarity_threshold=e.thresholds.similarity,
            self_service_threshold=e.thresholds.self_service,
            low_confidence_alert=e.requires_low_confidence_alert,
            fragments=[EvidenceFragmentResponse.from_fragment(f, e.thresholds.similarity) for f in e.retrieved],
        )


class DiagnosisPreviewRequest(BaseModel):
    incident: str = Field(
        ...,
        min_length=1,
        max_length=MAX_QUERY_CHARACTERS,
        examples=["No puedo conectarme a la VPN desde mi casa, me sale el error 809"],
    )


class DiagnosisSourceResponse(BaseModel):
    reference: str = Field(..., examples=["F1"])
    citation: str
    document_title: str
    similarity: float


class GeneratedDiagnosisResponse(BaseModel):
    summary: str
    steps: list[str]
    sources: list[DiagnosisSourceResponse]
    model: str
    suggested_category: str | None = None
    suggested_priority: str | None = None


class DiagnosisPreviewResponse(BaseModel):
    status: str = Field(..., description="ANSWERED, INSUFFICIENT_EVIDENCE, MODEL_DECLINED o INVALID_RESPONSE")
    reason: str | None
    confidence_level: str
    best_score: float
    diagnosis: GeneratedDiagnosisResponse | None

    @classmethod
    def build(cls, evaluation: GroundingEvaluation, outcome: DiagnosisOutcome) -> "DiagnosisPreviewResponse":
        diagnosis = None
        if outcome.diagnosis:
            d = outcome.diagnosis
            numbers = {f.chunk_id: i for i, f in enumerate(evaluation.supporting, start=1)}
            diagnosis = GeneratedDiagnosisResponse(
                summary=d.summary,
                steps=list(d.steps),
                sources=[
                    DiagnosisSourceResponse(
                        reference=f"F{numbers[f.chunk_id]}",
                        citation=f.citation.label,
                        document_title=f.document_title,
                        similarity=f.similarity,
                    )
                    for f in d.sources
                ],
                model=d.model,
                suggested_category=d.suggested_category.value if d.suggested_category else None,
                suggested_priority=d.suggested_priority.value if d.suggested_priority else None,
            )
        return cls(
            status=outcome.status.value,
            reason=outcome.reason,
            confidence_level=evaluation.level.value,
            best_score=evaluation.best_score,
            diagnosis=diagnosis,
        )


class OcrResultResponse(BaseModel):
    screenshot_received: bool
    legible: bool | None
    error_codes: list[str]
    feedback: str | None = Field(None, description="Mensaje para el colaborador si la captura no se pudo leer")


class AnalyzeIncidentResponse(BaseModel):
    """Resultado del análisis multimodal: diagnóstico con citas y puntaje de confianza (TS02)."""

    status: str = Field(..., description="ANSWERED, INSUFFICIENT_EVIDENCE, MODEL_DECLINED o INVALID_RESPONSE")
    reason: str | None
    confidence_level: str = Field(..., examples=["GROUNDED"])
    confidence_score: float = Field(..., description="Mejor similitud coseno entre el incidente y los manuales")
    similarity_threshold: float
    self_service_threshold: float
    ocr: OcrResultResponse
    diagnosis: GeneratedDiagnosisResponse | None

    @classmethod
    def from_analysis(cls, analysis: IncidentAnalysis) -> "AnalyzeIncidentResponse":
        preview = DiagnosisPreviewResponse.build(analysis.evaluation, analysis.outcome)
        received = bool(analysis.ocr_results)
        feedback = next((r.feedback_message for r in analysis.ocr_results if r.feedback_message), None)
        return cls(
            status=preview.status,
            reason=preview.reason,
            confidence_level=preview.confidence_level,
            confidence_score=preview.best_score,
            similarity_threshold=analysis.evaluation.thresholds.similarity,
            self_service_threshold=analysis.evaluation.thresholds.self_service,
            ocr=OcrResultResponse(
                screenshot_received=received,
                legible=analysis.screenshots_legible if received else None,
                error_codes=list(analysis.error_codes),
                feedback=None if analysis.screenshots_legible else feedback,
            ),
            diagnosis=preview.diagnosis,
        )


# --- Diagnóstico y revisión HITL (TS07) -------------------------------------------------------------------------

class AnswerSourceResponse(BaseModel):
    reference: str = Field(..., examples=["F1"])
    citation: str = Field(..., examples=["Manual_Soporte_Tecnico_Empresa_Demo.pdf, pág. 1, párr. 16"])
    document_title: str
    similarity: float | None = Field(None, description="Solo para el equipo de soporte")


class AiAnswerResponse(BaseModel):
    summary: str
    steps: list[str]
    sources: list[AnswerSourceResponse]
    model: str | None = None
    suggested_category: str | None = None
    suggested_priority: str | None = None


class FinalAnswerResponse(BaseModel):
    summary: str
    steps: list[str]


class ReviewInfoResponse(BaseModel):
    reviewed_by: uuid.UUID
    reviewer_name: str | None
    reviewed_at: datetime
    rejection_reason: str | None


class DiagnosisOcrResponse(BaseModel):
    legible: bool
    error_codes: list[str]
    text: str | None = Field(None, description="Texto leído de las capturas, ya anonimizado")


class DiagnosisResponse(BaseModel):
    """Diagnóstico del triaje de un ticket (W-07). Los campos de detalle solo se envían al equipo de soporte."""

    diagnosis_id: uuid.UUID
    ticket_id: uuid.UUID
    ticket_code: str = Field(..., examples=["TK-0009"])
    ticket_status: str
    review_status: str = Field(
        ...,
        description="PENDING_REVIEW, SELF_SERVICE_PROPOSED, NOT_APPLICABLE, APPROVED, EDITED_AND_APPROVED, REJECTED o MANUAL_RESPONSE",
    )
    allowed_actions: list[str] = Field(..., description="Revisiones que el usuario puede hacer ahora (botones de W-07)")
    ai_answer: AiAnswerResponse | None
    final_answer: FinalAnswerResponse | None
    manual_response: str | None
    outcome: str | None = None
    outcome_reason: str | None = None
    confidence_level: str | None = None
    confidence_score: float | None = None
    similarity_threshold: float | None = None
    self_service_threshold: float | None = None
    ocr: DiagnosisOcrResponse | None = None
    review: ReviewInfoResponse | None = None
    created_at: datetime

    @classmethod
    def from_view(cls, view: DiagnosisView) -> "DiagnosisResponse":
        d, full = view.diagnosis, view.full_detail
        ai_answer = None
        if d.summary:
            ai_answer = AiAnswerResponse(
                summary=d.summary,
                steps=list(d.steps),
                sources=[
                    AnswerSourceResponse(
                        reference=s.reference,
                        citation=s.citation,
                        document_title=s.document_title,
                        similarity=s.similarity if full else None,
                    )
                    for s in d.sources
                ],
                model=d.model if full else None,
                suggested_category=d.suggested_category.value if full and d.suggested_category else None,
                suggested_priority=d.suggested_priority.value if full and d.suggested_priority else None,
            )
        final = FinalAnswerResponse(summary=d.final_summary, steps=list(d.final_steps)) if d.final_summary else None
        data = {
            "diagnosis_id": d.id,
            "ticket_id": d.ticket_id,
            "ticket_code": view.ticket.code,
            "ticket_status": view.ticket.status,
            "review_status": d.review_status.value,
            "allowed_actions": [a.value for a in view.allowed_actions],
            "ai_answer": ai_answer,
            "final_answer": final,
            "manual_response": d.manual_response,
            "created_at": d.created_at,
        }
        if full:
            data |= {
                "outcome": d.outcome.value,
                "outcome_reason": d.outcome_reason,
                "confidence_level": d.confidence_level.value if d.confidence_level else None,
                "confidence_score": d.best_score,
                "similarity_threshold": d.similarity_threshold,
                "self_service_threshold": d.self_service_threshold,
                "ocr": DiagnosisOcrResponse(
                    legible=d.ocr.legible, error_codes=list(d.ocr.error_codes), text=d.ocr.masked_text
                )
                if d.ocr
                else None,
                "review": ReviewInfoResponse(
                    reviewed_by=d.reviewed_by,
                    reviewer_name=view.names.get(d.reviewed_by),
                    reviewed_at=d.reviewed_at,
                    rejection_reason=d.review_note,
                )
                if d.reviewed_at
                else None,
            }
        return cls(**data)


class ReviewDiagnosisRequest(BaseModel):
    decision: ReviewDecision = Field(..., examples=["APPROVE"])
    summary: str | None = Field(None, description="EDIT_AND_APPROVE: resumen corregido", max_length=600)
    steps: list[str] | None = Field(None, description="EDIT_AND_APPROVE: pasos corregidos (1 a 8)", max_length=8)
    reason: str | None = Field(None, description="REJECT: motivo del rechazo", max_length=500)
    response: str | None = Field(None, description="MANUAL_RESPONSE: respuesta para el colaborador", max_length=4000)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"decision": "APPROVE"},
                {"decision": "EDIT_AND_APPROVE", "summary": "El router bloquea la VPN.", "steps": ["Reinicia el router."]},
                {"decision": "REJECT", "reason": "El manual corresponde a otra versión de la VPN."},
                {"decision": "MANUAL_RESPONSE", "response": "Reinstalé tu perfil VPN; prueba de nuevo."},
            ]
        }
    }


class ReviewDiagnosisResponse(BaseModel):
    ticket_resolved: bool = Field(..., description="True si la revisión resolvió el ticket (todas menos REJECT)")
    diagnosis: DiagnosisResponse
