"""DTOs del contexto Smart Triage."""
from pydantic import BaseModel, Field

from app.knowledge.application.knowledge_retrieval_service import MAX_TOP_K
from app.smart_triage.application.evidence_retrieval_service import MAX_QUERY_CHARACTERS
from app.smart_triage.domain.diagnosis import DiagnosisOutcome
from app.smart_triage.domain.grounding import EvidenceFragment, GroundingEvaluation


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
            )
        return cls(
            status=outcome.status.value,
            reason=outcome.reason,
            confidence_level=evaluation.level.value,
            best_score=evaluation.best_score,
            diagnosis=diagnosis,
        )
