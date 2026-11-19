"""Pruebas unitarias y de integración de integridad encadenada y trazabilidad de auditoría (US21, T96)."""
import concurrent.futures
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.analytics.application.audit_log_service import AuditLogService
from app.analytics.application.ports import (
    DiagnosisTraceSummary,
    ITicketTraceReader,
    TicketTraceSnapshot,
    TicketTraceSummary,
    TraceSourceItem,
    UserIdentity,
)
from app.analytics.domain.audit_entry import (
    AuditEntry,
    AuditIntegrityReport,
    AuditIntegrityStatus,
    compute_integrity_hash,
)
from app.analytics.domain.exceptions import AuditEntryNotFoundError, TicketNotFoundError
from app.analytics.domain.repositories import AuditLogFilter, IAuditLogRepository
from app.analytics.infrastructure.persistence.audit_log_repository import SqlAlchemyAuditLogRepository
from app.helpdesk.domain.enums import ImpactLevel, TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.smart_triage.domain.diagnosis import DiagnosisStatus
from app.smart_triage.domain.grounding import ConfidenceLevel
from app.smart_triage.domain.triage_diagnosis import DiagnosisSource, ReviewStatus, TriageDiagnosis
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)
from tests.conftest import FAKE_HASH


# --------------------------------------------------------------------------------------------------- Unitarias


def test_compute_integrity_hash_is_backward_compatible_and_sensitive_to_previous_hash():
    ws_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    ticket_id = uuid.uuid4()
    ts_utc = datetime(2026, 11, 19, 15, 30, 0, tzinfo=UTC)
    ts_lima = ts_utc.astimezone(timezone(timedelta(hours=-5)))

    base_hash = compute_integrity_hash(
        event_type="TicketRegistered",
        workspace_id=ws_id,
        actor_id=actor_id,
        entity_type="ticket",
        entity_id=entity_id,
        ticket_id=ticket_id,
        occurred_at=ts_utc,
        detail={"has_evidence": True},
    )
    explicit_none = compute_integrity_hash(
        event_type="TicketRegistered",
        workspace_id=ws_id,
        actor_id=actor_id,
        entity_type="ticket",
        entity_id=entity_id,
        ticket_id=ticket_id,
        occurred_at=ts_lima,
        detail={"has_evidence": True},
        previous_hash=None,
    )
    chained_hash = compute_integrity_hash(
        event_type="TicketRegistered",
        workspace_id=ws_id,
        actor_id=actor_id,
        entity_type="ticket",
        entity_id=entity_id,
        ticket_id=ticket_id,
        occurred_at=ts_utc,
        detail={"has_evidence": True},
        previous_hash=base_hash,
    )

    assert base_hash == explicit_none
    assert len(base_hash) == 64
    assert chained_hash != base_hash


def test_chained_to_and_integrity_report_evaluate_all_states():
    ws_id = uuid.uuid4()
    t1 = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 19, 10, 5, tzinfo=UTC)

    e1_raw = AuditEntry.record(
        workspace_id=ws_id, event_type="TicketRegistered", entity_type="ticket", detail={"a": 1}, occurred_at=t1
    )
    e1 = AuditEntry(
        id=e1_raw.id,
        workspace_id=e1_raw.workspace_id,
        event_type=e1_raw.event_type,
        actor_id=e1_raw.actor_id,
        entity_type=e1_raw.entity_type,
        entity_id=e1_raw.entity_id,
        ticket_id=e1_raw.ticket_id,
        detail=e1_raw.detail,
        integrity_hash=e1_raw.integrity_hash,
        occurred_at=e1_raw.occurred_at,
        previous_hash=None,
        seq=1,
    )

    e2_chained = AuditEntry.record(
        workspace_id=ws_id, event_type="TriageCompleted", entity_type="triage_diagnosis", detail={"b": 2}, occurred_at=t2
    ).chained_to(e1.integrity_hash)
    e2 = AuditEntry(
        id=e2_chained.id,
        workspace_id=e2_chained.workspace_id,
        event_type=e2_chained.event_type,
        actor_id=e2_chained.actor_id,
        entity_type=e2_chained.entity_type,
        entity_id=e2_chained.entity_id,
        ticket_id=e2_chained.ticket_id,
        detail=e2_chained.detail,
        integrity_hash=e2_chained.integrity_hash,
        occurred_at=e2_chained.occurred_at,
        previous_hash=e2_chained.previous_hash,
        seq=2,
    )

    # 1. Génesis válido
    rep1 = AuditIntegrityReport.evaluate(e1, None)
    assert rep1.valid is True
    assert rep1.status is AuditIntegrityStatus.VALID
    assert rep1.hash_valid is True and rep1.chain_valid is True
    assert rep1.previous_entry_id is None and rep1.expected_previous_hash is None

    # 2. Encadenado válido
    rep2 = AuditIntegrityReport.evaluate(e2, e1)
    assert rep2.valid is True
    assert rep2.status is AuditIntegrityStatus.VALID
    assert rep2.previous_entry_id == e1.id
    assert rep2.stored_previous_hash == e1.integrity_hash
    assert rep2.expected_previous_hash == e1.integrity_hash

    # 3. Contenido alterado -> TAMPERED
    e2_tampered = AuditEntry(
        **{**e2.__dict__, "detail": {"b": 999}},
    )
    rep_tampered = AuditIntegrityReport.evaluate(e2_tampered, e1)
    assert rep_tampered.valid is False
    assert rep_tampered.status is AuditIntegrityStatus.TAMPERED
    assert rep_tampered.hash_valid is False and rep_tampered.chain_valid is True
    assert rep_tampered.stored_hash != rep_tampered.computed_hash

    # 4. Predecesor alterado en contenido -> CHAIN_BROKEN en la entrada siguiente
    e1_tampered = AuditEntry(**{**e1.__dict__, "detail": {"a": 999}})
    rep_broken_prev = AuditIntegrityReport.evaluate(e2, e1_tampered)
    assert rep_broken_prev.valid is False
    assert rep_broken_prev.status is AuditIntegrityStatus.CHAIN_BROKEN
    assert rep_broken_prev.hash_valid is True and rep_broken_prev.chain_valid is False

    # 5. Génesis con previous_hash no nulo pero hash propio consistente -> CHAIN_BROKEN
    bad_genesis = e1.chained_to("a" * 64)
    rep_bad_genesis = AuditIntegrityReport.evaluate(bad_genesis, None)
    assert rep_bad_genesis.valid is False
    assert rep_bad_genesis.status is AuditIntegrityStatus.CHAIN_BROKEN
    assert rep_bad_genesis.hash_valid is True and rep_bad_genesis.chain_valid is False


class _InMemoryRepo(IAuditLogRepository):
    def __init__(self, entries: list[AuditEntry]) -> None:
        self._entries = entries

    def append(self, entry: AuditEntry) -> AuditEntry:
        self._entries.append(entry)
        return entry

    def query(self, criteria: AuditLogFilter, *, offset: int = 0, limit: int = 20):
        return self._entries, len(self._entries)

    def find_by_id(self, workspace_id: uuid.UUID, entry_id: uuid.UUID) -> AuditEntry | None:
        return next((e for e in self._entries if e.workspace_id == workspace_id and e.id == entry_id), None)

    def find_previous(self, workspace_id: uuid.UUID, seq: int) -> AuditEntry | None:
        prevs = [e for e in self._entries if e.workspace_id == workspace_id and e.seq is not None and e.seq < seq]
        return max(prevs, key=lambda e: e.seq or 0) if prevs else None

    def list_for_ticket(self, workspace_id: uuid.UUID, ticket_id: uuid.UUID) -> list[AuditEntry]:
        return [e for e in self._entries if e.workspace_id == workspace_id and e.ticket_id == ticket_id]


class _FakeTraceReader(ITicketTraceReader):
    def __init__(self, snapshot: TicketTraceSnapshot | None, users: dict[uuid.UUID, UserIdentity]) -> None:
        self._snapshot = snapshot
        self._users = users

    def get_ticket_trace_snapshot(self, workspace_id: uuid.UUID, ticket_id: uuid.UUID) -> TicketTraceSnapshot | None:
        return self._snapshot

    def get_users_by_ids(self, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, UserIdentity]:
        return {uid: self._users[uid] for uid in user_ids if uid in self._users}


def test_service_authorizing_analyst_resolution_priority():
    ws_id = uuid.uuid4()
    ticket_id = uuid.uuid4()
    reporter_id = uuid.uuid4()
    analyst_a = uuid.uuid4()
    analyst_b = uuid.uuid4()
    now = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)

    snapshot = TicketTraceSnapshot(
        ticket=TicketTraceSummary(
            id=ticket_id,
            code="TK-0007",
            title="Fallo VPN",
            status="RESOLVED",
            priority="HIGH",
            category="Red/VPN",
            reporter_id=reporter_id,
            reporter_name="Carlos",
            assigned_analyst_id=analyst_b,
            assigned_analyst_name="Karim",
            created_at=now,
            resolved_at=now + timedelta(minutes=10),
        ),
        diagnosis=DiagnosisTraceSummary(
            id=uuid.uuid4(),
            outcome="ANSWERED",
            confidence_level="GROUNDED",
            best_score=0.77,
            similarity_threshold=0.68,
            self_service_threshold=0.80,
            model="gemini-2.5-flash-lite",
            review_status="MANUAL_RESPONSE",
            reviewed_by=analyst_b,
            reviewed_at=now + timedelta(minutes=10),
        ),
        sources=[],
    )
    users = {
        analyst_a: UserIdentity(id=analyst_a, full_name="Analista Uno", role="ANALYST_L1"),
        analyst_b: UserIdentity(id=analyst_b, full_name="Karim Ramírez", role="ANALYST_L1"),
    }

    # Caso 1: primero REJECT por analyst_a, luego MANUAL_RESPONSE por analyst_b -> elige MANUAL_RESPONSE
    e_reject = AuditEntry.record(
        workspace_id=ws_id,
        event_type="AiResolutionReviewed",
        actor_id=analyst_a,
        entity_type="triage_diagnosis",
        ticket_id=ticket_id,
        detail={"decision": "REJECT"},
        occurred_at=now + timedelta(minutes=3),
    )
    e_manual = AuditEntry.record(
        workspace_id=ws_id,
        event_type="AiResolutionReviewed",
        actor_id=analyst_b,
        entity_type="triage_diagnosis",
        ticket_id=ticket_id,
        detail={"decision": "MANUAL_RESPONSE"},
        occurred_at=now + timedelta(minutes=8),
    )
    service = AuditLogService(_InMemoryRepo([e_reject, e_manual]), trace_reader=_FakeTraceReader(snapshot, users))
    trace = service.ticket_trace(ws_id, ticket_id)
    assert trace.authorizing_analyst is not None
    assert trace.authorizing_analyst.id == analyst_b
    assert trace.authorizing_analyst.decision == "MANUAL_RESPONSE"
    assert trace.authorizing_analyst.role == "ANALYST_L1"

    # Caso 2: sin eventos AiResolutionReviewed, usa respaldo de diagnosis.reviewed_by
    service_fallback = AuditLogService(_InMemoryRepo([]), trace_reader=_FakeTraceReader(snapshot, users))
    trace_fb = service_fallback.ticket_trace(ws_id, ticket_id)
    assert trace_fb.authorizing_analyst is not None
    assert trace_fb.authorizing_analyst.id == analyst_b
    assert trace_fb.authorizing_analyst.decision == "MANUAL_RESPONSE"
    assert trace_fb.all_hashes_valid is True

    # Caso 3: not found en servicio
    service_missing = AuditLogService(_InMemoryRepo([]), trace_reader=_FakeTraceReader(None, {}))
    with pytest.raises(TicketNotFoundError):
        service_missing.ticket_trace(ws_id, ticket_id)
    with pytest.raises(AuditEntryNotFoundError):
        service_missing.verify_entry(ws_id, uuid.uuid4())


# --------------------------------------------------------------------------------------------------- Integración


@pytest.fixture()
def trace_setup(db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    leader = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        full_name="Líder Auditor",
        email=f"lider-aud-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=RoleName.IT_LEADER,
        department="TI",
    )
    specialist = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        full_name="Especialista L2",
        email=f"l2-aud-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=RoleName.SPECIALIST_L2,
        department="TI",
    )
    db_session.add_all([leader, specialist])
    db_session.flush()

    ticket = Ticket.register(
        workspace_id=workspace.id,
        reporter_id=collaborator.id,
        title="VPN corporativa devuelve error 809",
        description="Al conectar a la VPN aparece código 809",
        impact_level=ImpactLevel.HIGH,
    )
    ticket.status = TicketStatus.RESOLVED
    ticket.priority = TicketPriority.HIGH
    ticket.category = TicketCategory.NETWORK_VPN
    ticket.assigned_analyst_id = analyst.id
    ticket.resolved_at = datetime(2026, 11, 19, 13, 25, 7, tzinfo=UTC)
    SqlAlchemyTicketRepository(db_session).save(ticket)

    src1 = DiagnosisSource(
        reference="F1",
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Manual VPN Corporativa v2",
        citation="manual-vpn.pdf, pág. 4, párr. 2",
        similarity=0.7842,
    )
    diagnosis = TriageDiagnosis(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        ticket_id=ticket.id,
        outcome=DiagnosisStatus.ANSWERED,
        confidence_level=ConfidenceLevel.GROUNDED,
        best_score=0.7842,
        similarity_threshold=0.68,
        self_service_threshold=0.80,
        review_status=ReviewStatus.APPROVED,
        summary="Reiniciar el servicio IKEEXT y verificar el puerto UDP 4500.",
        steps=("Abrir servicios", "Reiniciar IKEEXT"),
        sources=(src1,),
        model="gemini-2.5-flash-lite",
        reviewed_by=analyst.id,
        reviewed_at=datetime(2026, 11, 19, 13, 25, 7, tzinfo=UTC),
    )
    SqlAlchemyTriageDiagnosisRepository(db_session).save(diagnosis)

    return {
        "workspace": workspace,
        "collaborator": collaborator,
        "analyst": analyst,
        "specialist": specialist,
        "leader": leader,
        "ticket": ticket,
        "diagnosis": diagnosis,
        "source": src1,
        "headers": {
            "leader": auth_headers(db_session, leader),
            "analyst": auth_headers(db_session, analyst),
            "specialist": auth_headers(db_session, specialist),
            "collaborator": auth_headers(db_session, collaborator),
        },
    }


def test_append_chains_per_workspace_and_verify_detects_tampering_and_chain_break(api_client, db_session, trace_setup):
    ws = trace_setup["workspace"]
    ticket = trace_setup["ticket"]
    analyst = trace_setup["analyst"]
    leader_headers = trace_setup["headers"]["leader"]
    repo = SqlAlchemyAuditLogRepository(db_session)

    # Otro workspace independiente para confirmar aislamiento de cadena
    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Otro WS", subdomain=f"otro-{uuid.uuid4().hex[:6]}")
    db_session.add(other_ws)
    db_session.flush()
    other_entry = repo.append(
        AuditEntry.record(
            workspace_id=other_ws.id,
            event_type="UserAuthenticated",
            entity_type="user",
            occurred_at=datetime(2026, 11, 19, 9, 0, tzinfo=UTC),
        )
    )
    assert other_entry.previous_hash is None
    assert other_entry.seq is not None

    # Cadena de 3 entradas en el workspace principal
    e1 = repo.append(
        AuditEntry.record(
            workspace_id=ws.id,
            event_type="TicketRegistered",
            actor_id=trace_setup["collaborator"].id,
            entity_type="ticket",
            entity_id=ticket.id,
            ticket_id=ticket.id,
            detail={"has_evidence": False},
            occurred_at=datetime(2026, 11, 19, 13, 10, 0, tzinfo=UTC),
        )
    )
    e2 = repo.append(
        AuditEntry.record(
            workspace_id=ws.id,
            event_type="TriageCompleted",
            entity_type="triage_diagnosis",
            entity_id=trace_setup["diagnosis"].id,
            ticket_id=ticket.id,
            detail={"outcome": "ANSWERED", "best_score": 0.7842},
            occurred_at=datetime(2026, 11, 19, 13, 15, 0, tzinfo=UTC),
        )
    )
    e3 = repo.append(
        AuditEntry.record(
            workspace_id=ws.id,
            event_type="AiResolutionReviewed",
            actor_id=analyst.id,
            entity_type="triage_diagnosis",
            entity_id=trace_setup["diagnosis"].id,
            ticket_id=ticket.id,
            detail={"decision": "APPROVE", "resolves_ticket": True},
            occurred_at=datetime(2026, 11, 19, 13, 25, 7, tzinfo=UTC),
        )
    )

    assert e1.previous_hash is None
    assert e2.previous_hash == e1.integrity_hash
    assert e3.previous_hash == e2.integrity_hash
    assert e1.seq < e2.seq < e3.seq

    # GET /audit/logs expone seq y previous_hash de forma aditiva
    logs_resp = api_client.get("/api/v1/audit/logs", headers=leader_headers)
    assert logs_resp.status_code == 200
    items = logs_resp.json()["items"]
    assert len(items) == 3
    assert items[0]["seq"] == e3.seq
    assert items[0]["previous_hash"] == e2.integrity_hash
    assert items[2]["previous_hash"] is None

    # Verificar #1 (génesis) y #3 -> ambos VALID
    v1 = api_client.get(f"/api/v1/audit/logs/{e1.id}/verify", headers=leader_headers)
    assert v1.status_code == 200
    v1_body = v1.json()
    assert v1_body["valid"] is True and v1_body["status"] == "VALID"
    assert v1_body["previous_entry_id"] is None and v1_body["expected_previous_hash"] is None

    v3 = api_client.get(f"/api/v1/audit/logs/{e3.id}/verify", headers=leader_headers)
    assert v3.status_code == 200
    v3_body = v3.json()
    assert v3_body["valid"] is True and v3_body["status"] == "VALID"
    assert v3_body["hash_valid"] is True and v3_body["chain_valid"] is True
    assert v3_body["previous_entry_id"] == str(e2.id)
    assert v3_body["stored_previous_hash"] == e2.integrity_hash
    assert v3_body["expected_previous_hash"] == e2.integrity_hash

    # Manipulación directa en PostgreSQL sobre la fila #2
    db_session.execute(
        text("UPDATE analytics_audit_log SET detail = '{\"tampered\": true}'::jsonb WHERE id = :id"),
        {"id": e2.id},
    )
    db_session.flush()

    # Verificar #2 -> 200 TAMPERED
    v2_tampered = api_client.get(f"/api/v1/audit/logs/{e2.id}/verify", headers=leader_headers)
    assert v2_tampered.status_code == 200
    b2 = v2_tampered.json()
    assert b2["valid"] is False
    assert b2["status"] == "TAMPERED"
    assert b2["hash_valid"] is False
    assert b2["chain_valid"] is True
    assert b2["stored_hash"] != b2["computed_hash"]

    # Verificar #3 (fila siguiente a la manipulada) -> 200 CHAIN_BROKEN
    v3_broken = api_client.get(f"/api/v1/audit/logs/{e3.id}/verify", headers=leader_headers)
    assert v3_broken.status_code == 200
    b3 = v3_broken.json()
    assert b3["valid"] is False
    assert b3["status"] == "CHAIN_BROKEN"
    assert b3["hash_valid"] is True
    assert b3["chain_valid"] is False

    # Entrada de otro workspace o inexistente -> 404 audit-entry-not-found
    not_found_other = api_client.get(f"/api/v1/audit/logs/{other_entry.id}/verify", headers=leader_headers)
    assert not_found_other.status_code == 404
    assert not_found_other.json()["type"] == "urn:tracehelp:problems:audit-entry-not-found"

    not_found_rand = api_client.get(f"/api/v1/audit/logs/{uuid.uuid4()}/verify", headers=leader_headers)
    assert not_found_rand.status_code == 404
    assert not_found_rand.json()["type"] == "urn:tracehelp:problems:audit-entry-not-found"


def test_ticket_trace_returns_sources_authorizing_analyst_and_chronological_events(api_client, db_session, trace_setup):
    ws = trace_setup["workspace"]
    ticket = trace_setup["ticket"]
    analyst = trace_setup["analyst"]
    collaborator = trace_setup["collaborator"]
    diagnosis = trace_setup["diagnosis"]
    source = trace_setup["source"]
    leader_headers = trace_setup["headers"]["leader"]
    repo = SqlAlchemyAuditLogRepository(db_session)

    # Insertar intencionalmente con timestamp distinto para comprobar orden occurred_at ASC, seq ASC
    e_review = repo.append(
        AuditEntry.record(
            workspace_id=ws.id,
            event_type="AiResolutionReviewed",
            actor_id=analyst.id,
            entity_type="triage_diagnosis",
            entity_id=diagnosis.id,
            ticket_id=ticket.id,
            detail={"decision": "APPROVE", "resolves_ticket": True},
            occurred_at=datetime(2026, 11, 19, 13, 25, 7, tzinfo=UTC),
        )
    )
    e_reg = repo.append(
        AuditEntry.record(
            workspace_id=ws.id,
            event_type="TicketRegistered",
            actor_id=collaborator.id,
            entity_type="ticket",
            entity_id=ticket.id,
            ticket_id=ticket.id,
            detail={"has_evidence": True},
            occurred_at=datetime(2026, 11, 19, 13, 10, 0, tzinfo=UTC),
        )
    )
    e_triage = repo.append(
        AuditEntry.record(
            workspace_id=ws.id,
            event_type="TriageCompleted",
            entity_type="triage_diagnosis",
            entity_id=diagnosis.id,
            ticket_id=ticket.id,
            detail={"outcome": "ANSWERED", "confidence_level": "GROUNDED"},
            occurred_at=datetime(2026, 11, 19, 13, 15, 0, tzinfo=UTC),
        )
    )

    resp = api_client.get(f"/api/v1/audit/tickets/{ticket.id}/trace", headers=leader_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["ticket"]["id"] == str(ticket.id)
    assert body["ticket"]["code"].startswith("TK-")
    assert body["ticket"]["title"] == "VPN corporativa devuelve error 809"
    assert body["ticket"]["status"] == "RESOLVED"
    assert body["ticket"]["priority"] == "HIGH"
    assert body["ticket"]["category"] == "Red/VPN"
    assert body["ticket"]["reporter_name"] == "Colaborador Demo"
    assert body["ticket"]["assigned_analyst_name"] == "Analista Demo"

    assert body["diagnosis"]["id"] == str(diagnosis.id)
    assert body["diagnosis"]["outcome"] == "ANSWERED"
    assert body["diagnosis"]["confidence_level"] == "GROUNDED"
    assert body["diagnosis"]["best_score"] == pytest.approx(0.7842)
    assert body["diagnosis"]["review_status"] == "APPROVED"

    assert len(body["sources"]) == 1
    assert body["sources"][0]["reference"] == "F1"
    assert body["sources"][0]["document_id"] == str(source.document_id)
    assert body["sources"][0]["document_title"] == "Manual VPN Corporativa v2"
    assert body["sources"][0]["citation"] == "manual-vpn.pdf, pág. 4, párr. 2"

    assert body["authorizing_analyst"]["id"] == str(analyst.id)
    assert body["authorizing_analyst"]["name"] == "Analista Demo"
    assert body["authorizing_analyst"]["role"] == "ANALYST_L1"
    assert body["authorizing_analyst"]["decision"] == "APPROVE"

    assert body["total_events"] == 3
    assert body["all_hashes_valid"] is True
    assert [e["id"] for e in body["events"]] == [str(e_reg.id), str(e_triage.id), str(e_review.id)]
    assert [e["event_type"] for e in body["events"]] == [
        "TicketRegistered",
        "TriageCompleted",
        "AiResolutionReviewed",
    ]

    # Si manipulamos un evento del ticket en SQL, all_hashes_valid debe ser False
    db_session.execute(
        text("UPDATE analytics_audit_log SET detail = '{\"tampered\": 1}'::jsonb WHERE id = :id"),
        {"id": e_triage.id},
    )
    db_session.flush()
    resp_after = api_client.get(f"/api/v1/audit/tickets/{ticket.id}/trace", headers=leader_headers)
    assert resp_after.status_code == 200
    assert resp_after.json()["all_hashes_valid"] is False


def test_ticket_trace_without_diagnosis_or_events_and_workspace_isolation(api_client, db_session, trace_setup):
    ws = trace_setup["workspace"]
    collaborator = trace_setup["collaborator"]
    leader_headers = trace_setup["headers"]["leader"]

    fresh_ticket = Ticket.register(
        workspace_id=ws.id,
        reporter_id=collaborator.id,
        title="Monitor sin señal",
        description="No enciende el monitor secundario",
        impact_level=ImpactLevel.LOW,
    )
    SqlAlchemyTicketRepository(db_session).save(fresh_ticket)

    resp = api_client.get(f"/api/v1/audit/tickets/{fresh_ticket.id}/trace", headers=leader_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["diagnosis"] is None
    assert body["sources"] == []
    assert body["authorizing_analyst"] is None
    assert body["events"] == []
    assert body["total_events"] == 0
    assert body["all_hashes_valid"] is True

    # Ticket en otro workspace -> 404 ticket-not-found
    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Empresa Ajena", subdomain=f"ajena-{uuid.uuid4().hex[:6]}")
    db_session.add(other_ws)
    db_session.flush()
    other_rep = UserModel(
        id=uuid.uuid4(),
        workspace_id=other_ws.id,
        full_name="Externo",
        email=f"ext-{uuid.uuid4().hex[:6]}@ajena.pe",
        password_hash=FAKE_HASH,
        role=RoleName.COLLABORATOR,
        department="Ops",
    )
    db_session.add(other_rep)
    db_session.flush()
    other_ticket = Ticket.register(
        workspace_id=other_ws.id,
        reporter_id=other_rep.id,
        title="Otro ticket",
        description="Incidente de otro tenant",
        impact_level=ImpactLevel.LOW,
    )
    SqlAlchemyTicketRepository(db_session).save(other_ticket)

    r_other = api_client.get(f"/api/v1/audit/tickets/{other_ticket.id}/trace", headers=leader_headers)
    assert r_other.status_code == 404
    assert r_other.json()["type"] == "urn:tracehelp:problems:ticket-not-found"

    r_missing = api_client.get(f"/api/v1/audit/tickets/{uuid.uuid4()}/trace", headers=leader_headers)
    assert r_missing.status_code == 404
    assert r_missing.json()["type"] == "urn:tracehelp:problems:ticket-not-found"


def test_verify_and_trace_enforce_rbac_and_validation(api_client, trace_setup):
    ticket_id = trace_setup["ticket"].id
    fake_entry = uuid.uuid4()

    for path in (f"/api/v1/audit/logs/{fake_entry}/verify", f"/api/v1/audit/tickets/{ticket_id}/trace"):
        assert api_client.get(path).status_code == 401
        for role in ("collaborator", "analyst", "specialist"):
            resp = api_client.get(path, headers=trace_setup["headers"][role])
            assert resp.status_code == 403
            assert resp.json()["type"] == "urn:tracehelp:problems:forbidden"

    leader_headers = trace_setup["headers"]["leader"]
    bad_verify = api_client.get("/api/v1/audit/logs/no-uuid/verify", headers=leader_headers)
    assert bad_verify.status_code == 422
    assert bad_verify.json()["type"] == "urn:tracehelp:problems:validation-error"

    bad_trace = api_client.get("/api/v1/audit/tickets/no-uuid/trace", headers=leader_headers)
    assert bad_trace.status_code == 422
    assert bad_trace.json()["type"] == "urn:tracehelp:problems:validation-error"


def test_openapi_documents_verify_and_trace_endpoints(api_client):
    paths = api_client.get("/openapi.json").json()["paths"]
    verify_op = paths["/api/v1/audit/logs/{entry_id}/verify"]["get"]
    trace_op = paths["/api/v1/audit/tickets/{ticket_id}/trace"]["get"]
    assert {"200", "401", "403", "404", "422"} <= set(verify_op["responses"])
    assert {"200", "401", "403", "404", "422"} <= set(trace_op["responses"])


def test_concurrent_appends_serialize_chain_without_forks(db_engine):
    ws_id = uuid.uuid4()
    with Session(db_engine) as setup_session:
        setup_session.add(WorkspaceModel(id=ws_id, name="Concurrent WS", subdomain=f"conc-{ws_id.hex[:8]}"))
        setup_session.commit()

    def _worker(idx: int) -> AuditEntry:
        with Session(db_engine) as session:
            entry = SqlAlchemyAuditLogRepository(session).append(
                AuditEntry.record(
                    workspace_id=ws_id,
                    event_type="UserAuthenticated",
                    entity_type="user",
                    detail={"worker": idx},
                    occurred_at=datetime(2026, 11, 19, 14, 0, idx % 60, tzinfo=UTC),
                )
            )
            session.commit()
            return entry

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(_worker, range(12)))

        assert len(results) == 12
        ordered = sorted(results, key=lambda e: e.seq)
        assert len({e.seq for e in ordered}) == 12
        assert ordered[0].previous_hash is None
        for idx, current in enumerate(ordered):
            prev = ordered[idx - 1] if idx > 0 else None
            report = AuditIntegrityReport.evaluate(current, prev)
            assert report.valid is True, f"Fallo en posición {idx}: {report}"
    finally:
        with Session(db_engine) as cleanup_session:
            cleanup_session.execute(text("DELETE FROM analytics_audit_log WHERE workspace_id = :w"), {"w": ws_id})
            cleanup_session.execute(text("DELETE FROM iam_workspaces WHERE id = :w"), {"w": ws_id})
            cleanup_session.commit()


def test_migration_0014_backfills_existing_rows_deterministically_and_supports_downgrade(db_engine):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", db_engine.url.render_as_string(hide_password=False).replace("%", "%%"))

    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    id_a_late = uuid.uuid4()
    id_a_early = uuid.uuid4()
    id_b_only = uuid.uuid4()
    t_early = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    t_late = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)

    try:
        # 1. Bajar a 0013 (antes de seq y previous_hash)
        command.downgrade(cfg, "0013")
        cols_before = {c["name"] for c in inspect(db_engine).get_columns("analytics_audit_log")}
        assert "seq" not in cols_before and "previous_hash" not in cols_before

        # 2. Insertar filas históricas en dos workspaces con orden inverso de timestamp
        with db_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO iam_workspaces (id, name, subdomain) VALUES (:id, :name, :sub)"),
                [
                    {"id": ws_a, "name": "Mig A", "sub": f"miga-{ws_a.hex[:6]}"},
                    {"id": ws_b, "name": "Mig B", "sub": f"migb-{ws_b.hex[:6]}"},
                ],
            )
            conn.execute(
                text(
                    """
                    INSERT INTO analytics_audit_log
                        (id, workspace_id, event_type, entity_type, detail, integrity_hash, occurred_at)
                    VALUES
                        (:id1, :wsa, 'TicketStatusChanged', 'ticket', '{"step": 2}'::jsonb, :legacy_h, :t_late),
                        (:id2, :wsa, 'TicketRegistered', 'ticket', '{"step": 1}'::jsonb, :legacy_h, :t_early),
                        (:id3, :wsb, 'UserAuthenticated', 'user', '{"step": 1}'::jsonb, :legacy_h, :t_early)
                    """
                ),
                {
                    "id1": id_a_late,
                    "id2": id_a_early,
                    "id3": id_b_only,
                    "wsa": ws_a,
                    "wsb": ws_b,
                    "legacy_h": "0" * 64,
                    "t_early": t_early,
                    "t_late": t_late,
                },
            )

        # 3. Subir a 0014 y comprobar backfill + índices + secuencia IDENTITY
        command.upgrade(cfg, "0014")
        indexes = {ix["name"] for ix in inspect(db_engine).get_indexes("analytics_audit_log")}
        assert "ix_analytics_audit_log_workspace_seq" in indexes
        assert "ix_analytics_audit_log_actor_id" in indexes

        with Session(db_engine) as session:
            repo = SqlAlchemyAuditLogRepository(session)
            a_early = repo.find_by_id(ws_a, id_a_early)
            a_late = repo.find_by_id(ws_a, id_a_late)
            b_only = repo.find_by_id(ws_b, id_b_only)

            assert a_early is not None and a_late is not None and b_only is not None
            assert a_early.seq < a_late.seq
            assert a_early.previous_hash is None
            assert a_late.previous_hash == a_early.integrity_hash
            assert b_only.previous_hash is None
            assert a_early.verify_integrity() is True
            assert a_late.verify_integrity() is True
            assert b_only.verify_integrity() is True
            assert AuditIntegrityReport.evaluate(a_early, None).valid is True
            assert AuditIntegrityReport.evaluate(a_late, a_early).valid is True
            assert AuditIntegrityReport.evaluate(b_only, None).valid is True

            # Insertar una fila nueva post-migración: la identidad debe continuar sin colisión
            a_new = repo.append(
                AuditEntry.record(
                    workspace_id=ws_a,
                    event_type="AiResolutionReviewed",
                    entity_type="triage_diagnosis",
                    detail={"decision": "APPROVE"},
                    occurred_at=datetime(2026, 11, 10, 10, 0, tzinfo=UTC),
                )
            )
            session.commit()
            assert a_new.seq > a_late.seq
            assert a_new.previous_hash == a_late.integrity_hash
            assert AuditIntegrityReport.evaluate(a_new, a_late).valid is True

        # 4. Probar downgrade limpio y vuelta a head
        command.downgrade(cfg, "0013")
        cols_after_down = {c["name"] for c in inspect(db_engine).get_columns("analytics_audit_log")}
        assert "seq" not in cols_after_down and "previous_hash" not in cols_after_down
        indexes_after_down = {ix["name"] for ix in inspect(db_engine).get_indexes("analytics_audit_log")}
        assert "ix_analytics_audit_log_workspace_seq" not in indexes_after_down
        assert "ix_analytics_audit_log_actor_id" not in indexes_after_down
    finally:
        command.upgrade(cfg, "head")
        with db_engine.begin() as conn:
            conn.execute(
                text("DELETE FROM analytics_audit_log WHERE workspace_id IN (:a, :b)"),
                {"a": ws_a, "b": ws_b},
            )
            conn.execute(text("DELETE FROM iam_workspaces WHERE id IN (:a, :b)"), {"a": ws_a, "b": ws_b})
