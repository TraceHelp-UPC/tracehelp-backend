"""Pruebas unitarias y de integración para la bitácora inmutable de auditoría (US15, T36)."""
import uuid
from dataclasses import dataclass

import pytest

from app.analytics.application.audit_trail_service import (
    AuditTrailService,
    RecordAuditEntryCommand,
    translate_event_to_audit_command,
)
from app.analytics.domain.audit_trail_entry import AuditTrailEntry
from app.analytics.domain.enums import AuditActionType
from app.analytics.domain.exceptions import InvalidAuditLogDataError
from app.analytics.domain.repositories import IAuditTrailRepository
from app.analytics.domain.value_objects import IntegrityHash
from app.analytics.infrastructure.persistence.audit_trail_repository import SqlAlchemyAuditTrailRepository
from app.analytics.infrastructure.persistence.models import AuditLogModel
from app.helpdesk.domain.enums import ImpactLevel
from app.helpdesk.domain.events import TicketStatusChanged
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel
from app.shared.domain.aggregate_root import DomainEvent
from tests.conftest import FAKE_HASH


class InMemoryAuditTrailRepository(IAuditTrailRepository):
    def __init__(self) -> None:
        self._entries: list[AuditTrailEntry] = []

    def append(self, entry: AuditTrailEntry) -> AuditTrailEntry:
        self._entries.append(entry)
        return entry

    def find_by_ticket(self, ticket_id: uuid.UUID, workspace_id: uuid.UUID) -> list[AuditTrailEntry]:
        return [e for e in self._entries if e.ticket_id == ticket_id and e.workspace_id == workspace_id]

    def list_by_workspace(
        self,
        workspace_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        ticket_id: uuid.UUID | None = None,
    ) -> tuple[list[AuditTrailEntry], int]:
        filtered = [
            e
            for e in self._entries
            if e.workspace_id == workspace_id and (ticket_id is None or e.ticket_id == ticket_id)
        ]
        start = (page - 1) * page_size
        return filtered[start : start + page_size], len(filtered)


@dataclass(frozen=True, kw_only=True)
class RagRecommendationGenerated(DomainEvent):
    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    confidence_score: float
    consulted_sources: list[dict]


@dataclass(frozen=True, kw_only=True)
class LowConfidenceAlertTriggered(DomainEvent):
    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    confidence_score: float
    reason: str = "Puntaje inferior al umbral 0.70"


@dataclass(frozen=True, kw_only=True)
class AiResolutionReviewed(DomainEvent):
    ticket_id: uuid.UUID
    workspace_id: uuid.UUID
    reviewer_id: uuid.UUID
    action: str
    consulted_sources: list[dict]


def test_audit_trail_entry_computes_and_verifies_sha256_integrity_hash():
    entry = AuditTrailEntry.record(
        workspace_id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        action_type=AuditActionType.AI_RESOLUTION_APPROVED,
        consulted_sources=[{"source_file": "manual_vpn.pdf", "page_number": 4, "paragraph_number": 2}],
        validator_analyst_id=uuid.uuid4(),
        confidence_score=0.91,
        details="Aprobación HITL por analista L1",
    )

    assert len(entry.integrity_hash_sha256) == 64
    assert entry.verify_integrity() is True


def test_tampered_audit_trail_entry_fails_integrity_verification():
    original = AuditTrailEntry.record(
        workspace_id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        action_type=AuditActionType.AI_RESOLUTION_APPROVED,
        consulted_sources=[{"source_file": "manual_vpn.pdf", "page_number": 4, "paragraph_number": 2}],
        validator_analyst_id=uuid.uuid4(),
    )
    tampered = AuditTrailEntry(
        id=original.id,
        workspace_id=original.workspace_id,
        ticket_id=original.ticket_id,
        action_type=AuditActionType.AI_RESOLUTION_REJECTED,  # alterado
        consulted_sources=original.consulted_sources,
        validator_analyst_id=original.validator_analyst_id,
        occurred_at=original.occurred_at,
        integrity_hash=original.integrity_hash,
    )

    assert tampered.verify_integrity() is False


def test_invalid_integrity_hash_format_raises_domain_error():
    with pytest.raises(InvalidAuditLogDataError):
        IntegrityHash("hash-invalido")


def test_translate_inference_alert_and_hitl_events_to_audit_commands():
    ws_id = uuid.uuid4()
    tk_id = uuid.uuid4()
    analyst_id = uuid.uuid4()
    sources = [{"source_file": "guia_erp.pdf", "page_number": 2, "paragraph_number": 1}]

    rag_cmd = translate_event_to_audit_command(
        RagRecommendationGenerated(
            ticket_id=tk_id, workspace_id=ws_id, confidence_score=0.88, consulted_sources=sources
        )
    )
    assert rag_cmd is not None
    assert rag_cmd.action_type is AuditActionType.RAG_RECOMMENDATION_GENERATED
    assert rag_cmd.consulted_sources == sources

    alert_cmd = translate_event_to_audit_command(
        LowConfidenceAlertTriggered(ticket_id=tk_id, workspace_id=ws_id, confidence_score=0.42)
    )
    assert alert_cmd is not None
    assert alert_cmd.action_type is AuditActionType.LOW_CONFIDENCE_ALERT_TRIGGERED

    hitl_cmd = translate_event_to_audit_command(
        AiResolutionReviewed(
            ticket_id=tk_id,
            workspace_id=ws_id,
            reviewer_id=analyst_id,
            action="EDIT",
            consulted_sources=sources,
        )
    )
    assert hitl_cmd is not None
    assert hitl_cmd.action_type is AuditActionType.AI_RESOLUTION_EDITED
    assert hitl_cmd.validator_analyst_id == analyst_id

    status_cmd = translate_event_to_audit_command(
        TicketStatusChanged(
            ticket_id=tk_id,
            workspace_id=ws_id,
            reporter_id=uuid.uuid4(),
            previous_status="ASSIGNED_L1",
            new_status="RESOLVED",
            changed_by=analyst_id,
            reason="Resuelto tras validación HITL",
        )
    )
    assert status_cmd is not None
    assert status_cmd.action_type is AuditActionType.TICKET_STATUS_CHANGED


def test_persist_and_query_audit_logs_via_api(db_session, workspace_and_users, api_client, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    leader = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        full_name="Líder TI",
        email=f"lider-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=RoleName.IT_LEADER,
        department="TI",
    )
    db_session.add(leader)
    db_session.flush()

    ticket = Ticket.register(
        workspace_id=workspace.id,
        reporter_id=collaborator.id,
        title="Error VPN corporativa",
        description="No conecta al gateway",
        impact_level=ImpactLevel.HIGH,
    )
    SqlAlchemyTicketRepository(db_session).save(ticket)

    repo = SqlAlchemyAuditTrailRepository(db_session)
    service = AuditTrailService(db_session, repo)

    service.record_entry(
        RecordAuditEntryCommand(
            workspace_id=workspace.id,
            ticket_id=ticket.id,
            action_type=AuditActionType.RAG_RECOMMENDATION_GENERATED,
            consulted_sources=[{"source_file": "manual_vpn.pdf", "page_number": 3, "paragraph_number": 1}],
            confidence_score=0.86,
        )
    )
    service.record_entry(
        RecordAuditEntryCommand(
            workspace_id=workspace.id,
            ticket_id=ticket.id,
            action_type=AuditActionType.AI_RESOLUTION_APPROVED,
            consulted_sources=[{"source_file": "manual_vpn.pdf", "page_number": 3, "paragraph_number": 1}],
            validator_analyst_id=analyst.id,
            confidence_score=0.86,
        )
    )

    entries = repo.find_by_ticket(ticket.id, workspace.id)
    assert len(entries) == 2
    assert all(e.verify_integrity() for e in entries)

    # El Líder de TI con permiso audit:read puede consultar la bitácora paginada
    response = api_client.get(
        f"/api/v1/audit/logs?ticket_id={ticket.id}&page=1&page_size=10",
        headers=auth_headers(db_session, leader),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 2
    assert all(item["integrity_verified"] is True for item in body["items"])

    # Un colaborador sin permiso audit:read recibe 403
    forbidden = api_client.get("/api/v1/audit/logs", headers=auth_headers(db_session, collaborator))
    assert forbidden.status_code == 403

    # Paginación fuera de rango devuelve 400
    bad_page = api_client.get("/api/v1/audit/logs?page_size=101", headers=auth_headers(db_session, leader))
    assert bad_page.status_code == 400
