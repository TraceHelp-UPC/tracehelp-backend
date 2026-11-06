"""Casos de uso de diagnóstico RAG y revisión humana HITL del Bounded Context Smart Triage (US11, US15, TS07)."""
import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.analytics.application.audit_trail_service import translate_event_to_audit_command
from app.analytics.domain.audit_trail_entry import AuditTrailEntry
from app.analytics.domain.repositories import IAuditTrailRepository
from app.helpdesk.domain.enums import TicketStatus
from app.helpdesk.domain.repositories import ITicketRepository
from app.shared.domain.aggregate_root import DomainEvent
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.domain.exceptions import (
    InvalidTriageReviewError,
    TriageDiagnosisNotFoundError,
)
from app.smart_triage.domain.repositories import ITriageDiagnosisRepository
from app.smart_triage.domain.triage_diagnosis import TriageDiagnosis
from app.smart_triage.domain.value_objects import SimilarityThresholds, SourceCitation


@dataclass(frozen=True)
class EvaluateRagDiagnosisCommand:
    workspace_id: uuid.UUID
    ticket_id: uuid.UUID
    query_text: str
    citations: list[SourceCitation] = field(default_factory=list)
    synthesized_answer: str | None = None
    thresholds: SimilarityThresholds | None = None


@dataclass(frozen=True)
class ReviewAiResolutionCommand:
    diagnosis_id: uuid.UUID
    workspace_id: uuid.UUID
    reviewer_id: uuid.UUID
    action: str
    edited_text: str | None = None
    reason: str | None = None


class TriageService:
    """Orquesta la evaluación RAG, las acciones HITL y la coordinación con Helpdesk y Analytics."""

    def __init__(
        self,
        session: Session,
        diagnoses: ITriageDiagnosisRepository,
        tickets: ITicketRepository,
        audit_logs: IAuditTrailRepository,
        events: InMemoryEventBus,
    ) -> None:
        self._session = session
        self._diagnoses = diagnoses
        self._tickets = tickets
        self._audit_logs = audit_logs
        self._events = events

    def evaluate_rag_diagnosis(self, command: EvaluateRagDiagnosisCommand) -> TriageDiagnosis:
        """Evalúa los fragmentos recuperados, guarda el diagnóstico y registra el evento en auditoría (US11)."""
        diagnosis = TriageDiagnosis.evaluate_and_create(
            workspace_id=command.workspace_id,
            ticket_id=command.ticket_id,
            query_text=command.query_text,
            citations=command.citations,
            synthesized_answer=command.synthesized_answer,
            thresholds=command.thresholds,
        )
        self._diagnoses.save(diagnosis)
        emitted = diagnosis.pull_events()
        self._append_audit_entries(emitted)
        self._session.commit()
        self._events.publish_all(emitted)
        return diagnosis

    def get_diagnosis_by_ticket(self, ticket_id: uuid.UUID, workspace_id: uuid.UUID) -> TriageDiagnosis:
        """Recupera el diagnóstico asociado al ticket validando el workspace (TS07)."""
        diagnosis = self._diagnoses.find_by_ticket_id(ticket_id)
        if diagnosis is None or diagnosis.workspace_id != workspace_id:
            raise TriageDiagnosisNotFoundError("El diagnóstico solicitado no existe.")
        return diagnosis

    def review_diagnosis(self, command: ReviewAiResolutionCommand) -> TriageDiagnosis:
        """Ejecuta la revisión humana HITL (APPROVE, EDIT, REJECT, MANUAL) y actualiza ticket + auditoría (US15, TS07)."""
        diagnosis = self._diagnoses.find_by_id(command.diagnosis_id)
        if diagnosis is None or diagnosis.workspace_id != command.workspace_id:
            raise TriageDiagnosisNotFoundError("El diagnóstico solicitado no existe.")

        action_normalized = (command.action or "").strip().upper()
        if action_normalized == "APPROVE":
            diagnosis.approve_hitl(command.reviewer_id)
            is_ai_generated = True
            should_publish_and_resolve = True
        elif action_normalized in {"EDIT", "EDIT_AND_APPROVE"}:
            diagnosis.edit_and_approve_hitl(command.reviewer_id, command.edited_text or "")
            is_ai_generated = True
            should_publish_and_resolve = True
        elif action_normalized == "REJECT":
            diagnosis.reject_hitl(command.reviewer_id, command.reason)
            is_ai_generated = False
            should_publish_and_resolve = False
        elif action_normalized in {"MANUAL", "MANUAL_RESPONSE"}:
            diagnosis.provide_manual_resolution(command.reviewer_id, command.edited_text or "")
            is_ai_generated = False
            should_publish_and_resolve = True
        else:
            raise InvalidTriageReviewError(
                f"La acción de revisión '{command.action}' no es válida. Use APPROVE, EDIT, REJECT o MANUAL."
            )

        self._diagnoses.save(diagnosis)
        emitted: list[DomainEvent] = list(diagnosis.pull_events())

        if should_publish_and_resolve and diagnosis.final_approved_text:
            ticket = self._tickets.find_by_id(diagnosis.ticket_id)
            if ticket is not None and ticket.workspace_id == command.workspace_id:
                ticket.add_comment(
                    author_id=command.reviewer_id,
                    content=diagnosis.final_approved_text,
                    is_internal_note=False,
                    is_ai_generated=is_ai_generated,
                )
                if ticket.status is TicketStatus.OPEN:
                    ticket.change_status(TicketStatus.PENDING_ASSIGNMENT, changed_by=command.reviewer_id)
                if ticket.status is TicketStatus.PENDING_ASSIGNMENT:
                    ticket.change_status(
                        TicketStatus.ASSIGNED_L1,
                        changed_by=command.reviewer_id,
                        assignee_id=command.reviewer_id,
                    )
                if ticket.status in {TicketStatus.ASSIGNED_L1, TicketStatus.ESCALATED_L2}:
                    ticket.change_status(
                        TicketStatus.RESOLVED,
                        changed_by=command.reviewer_id,
                        reason="Resuelto tras validación humana HITL",
                    )
                self._tickets.save(ticket)
                emitted.extend(ticket.pull_events())

        self._append_audit_entries(emitted)
        self._session.commit()
        self._events.publish_all(emitted)
        return diagnosis

    def _append_audit_entries(self, events: list[DomainEvent]) -> None:
        for ev in events:
            audit_cmd = translate_event_to_audit_command(ev)
            if audit_cmd is not None:
                entry = AuditTrailEntry.record(
                    workspace_id=audit_cmd.workspace_id,
                    ticket_id=audit_cmd.ticket_id,
                    action_type=audit_cmd.action_type,
                    consulted_sources=audit_cmd.consulted_sources,
                    validator_analyst_id=audit_cmd.validator_analyst_id,
                    confidence_score=audit_cmd.confidence_score,
                    details=audit_cmd.details,
                    occurred_at=audit_cmd.occurred_at,
                )
                self._audit_logs.append(entry)
