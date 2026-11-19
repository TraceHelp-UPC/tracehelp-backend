"""Steps BDD para integridad criptográfica de bitácora y trazabilidad de tickets (US21, T96/T99)."""
import json
import uuid
from datetime import UTC, datetime, timedelta

from behave import given, then, when
from sqlalchemy import text

from app.analytics.domain.audit_entry import AuditEntry, compute_integrity_hash
from app.analytics.infrastructure.persistence.audit_log_repository import SqlAlchemyAuditLogRepository
from app.helpdesk.domain.enums import ImpactLevel, TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.smart_triage.domain.diagnosis import DiagnosisStatus
from app.smart_triage.domain.grounding import ConfidenceLevel
from app.smart_triage.domain.triage_diagnosis import DiagnosisSource, ReviewStatus, TriageDiagnosis
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)

FAKE_HASH = "$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm"


def _headers(context, role: str) -> dict[str, str]:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _ensure_store(context) -> None:
    if not hasattr(context, "chained_entries"):
        context.chained_entries = {}
    if not hasattr(context, "foreign_entries"):
        context.foreign_entries = {}
    if not hasattr(context, "foreign_tickets"):
        context.foreign_tickets = {}


def _append_chained(
    context,
    *,
    workspace_id: uuid.UUID,
    event_type: str,
    entity_type: str,
    actor_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    ticket_id: uuid.UUID | None = None,
    detail: dict | None = None,
    occurred_at: datetime | None = None,
) -> AuditEntry:
    repo = SqlAlchemyAuditLogRepository(context.session)
    entry = AuditEntry.record(
        workspace_id=workspace_id,
        event_type=event_type,
        entity_type=entity_type,
        actor_id=actor_id,
        entity_id=entity_id or uuid.uuid4(),
        ticket_id=ticket_id,
        detail=detail or {},
        occurred_at=occurred_at or datetime.now(UTC),
    )
    persisted = repo.append(entry)
    context.session.flush()
    return persisted


@given("a chained audit sequence of {count:d} entries in the workspace")
def step_chained_sequence(context, count: int):
    _ensure_store(context)
    base = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
    for idx in range(1, count + 1):
        label = f"C{idx}"
        persisted = _append_chained(
            context,
            workspace_id=context.workspace.id,
            event_type="TicketStatusChanged",
            entity_type="ticket",
            actor_id=context.users["ANALYST_L1"].id,
            detail={"step": label, "seq_label": idx},
            occurred_at=base + timedelta(minutes=idx),
        )
        context.chained_entries[label] = persisted


@given('a triaged ticket in status "{status}" with a pending AI diagnosis and cited sources')
def step_traced_triaged_ticket(context, status: str):
    _ensure_store(context)
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title="VPN corporativa devuelve error 809",
        description="No conecta la VPN corporativa desde red doméstica",
        impact_level=ImpactLevel.HIGH,
    )
    ticket.status = TicketStatus(status)
    ticket.category = TicketCategory.NETWORK_VPN
    ticket.priority = TicketPriority.HIGH
    if ticket.status in {TicketStatus.ASSIGNED_L1, TicketStatus.ESCALATED_L2, TicketStatus.RESOLVED}:
        ticket.assigned_analyst_id = context.users["ANALYST_L1"].id
    SqlAlchemyTicketRepository(context.session).save(ticket)
    context.traced_ticket = ticket
    context.traced_ticket_events = []

    source = DiagnosisSource(
        reference="F1",
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Manual VPN Corporativa v2",
        citation="manual-vpn.pdf, pág. 4, párr. 2",
        similarity=0.7842,
    )
    diagnosis = TriageDiagnosis(
        id=uuid.uuid4(),
        workspace_id=context.workspace.id,
        ticket_id=ticket.id,
        outcome=DiagnosisStatus.ANSWERED,
        confidence_level=ConfidenceLevel.GROUNDED,
        best_score=0.7842,
        similarity_threshold=0.68,
        self_service_threshold=0.80,
        review_status=ReviewStatus.PENDING_REVIEW,
        summary="Habilitar puertos UDP 500 y 4500 para IKEv2 [F1].",
        steps=["Verificar firewall local", "Reconectar cliente VPN"],
        sources=[source],
        model="gemini-2.5-flash-lite",
    )
    SqlAlchemyTriageDiagnosisRepository(context.session).save(diagnosis)
    context.traced_diagnosis = diagnosis
    context.session.flush()


@given('the ticket has chained audit events for registration, triage, HITL approval by "{role}", and resolution')
def step_traced_ticket_events_approved(context, role: str):
    t = context.traced_ticket
    d = context.traced_diagnosis
    analyst = context.users[role]
    base = datetime(2026, 11, 20, 13, 10, tzinfo=UTC)

    e1 = _append_chained(
        context,
        workspace_id=context.workspace.id,
        event_type="TicketRegistered",
        entity_type="ticket",
        actor_id=context.users["COLLABORATOR"].id,
        entity_id=t.id,
        ticket_id=t.id,
        detail={"has_evidence": False},
        occurred_at=base,
    )
    e2 = _append_chained(
        context,
        workspace_id=context.workspace.id,
        event_type="TriageCompleted",
        entity_type="triage_diagnosis",
        actor_id=None,
        entity_id=d.id,
        ticket_id=t.id,
        detail={"outcome": "ANSWERED", "confidence_level": "GROUNDED", "best_score": 0.7842},
        occurred_at=base + timedelta(minutes=1),
    )

    reviewed_at = base + timedelta(minutes=5)
    context.session.execute(
        text(
            """
            UPDATE triage_diagnoses
               SET review_status = 'APPROVED',
                   reviewed_by = :reviewer_id,
                   reviewed_at = :reviewed_at
             WHERE id = :diag_id
            """
        ),
        {"reviewer_id": analyst.id, "reviewed_at": reviewed_at, "diag_id": d.id},
    )
    context.session.execute(
        text(
            """
            UPDATE helpdesk_tickets
               SET status = 'RESOLVED',
                   resolved_at = :resolved_at
             WHERE id = :ticket_id
            """
        ),
        {"resolved_at": reviewed_at, "ticket_id": t.id},
    )

    e3 = _append_chained(
        context,
        workspace_id=context.workspace.id,
        event_type="AiResolutionReviewed",
        entity_type="triage_diagnosis",
        actor_id=analyst.id,
        entity_id=d.id,
        ticket_id=t.id,
        detail={"decision": "APPROVE", "previous_status": "PENDING_REVIEW", "resolves_ticket": True},
        occurred_at=reviewed_at,
    )
    e4 = _append_chained(
        context,
        workspace_id=context.workspace.id,
        event_type="TicketStatusChanged",
        entity_type="ticket",
        actor_id=analyst.id,
        entity_id=t.id,
        ticket_id=t.id,
        detail={"previous_status": "ASSIGNED_L1", "new_status": "RESOLVED"},
        occurred_at=base + timedelta(minutes=6),
    )
    context.traced_ticket_events = [e1, e2, e3, e4]
    context.session.flush()


@given("a newly registered ticket without AI diagnosis with a chained registration audit event")
def step_untriaged_traced_ticket(context):
    _ensure_store(context)
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title="Solicitud de acceso a carpeta compartida",
        description="Requiero permisos de lectura en Finanzas",
        impact_level=ImpactLevel.LOW,
    )
    SqlAlchemyTicketRepository(context.session).save(ticket)
    context.traced_ticket = ticket
    context.traced_diagnosis = None
    e1 = _append_chained(
        context,
        workspace_id=context.workspace.id,
        event_type="TicketRegistered",
        entity_type="ticket",
        actor_id=context.users["COLLABORATOR"].id,
        entity_id=ticket.id,
        ticket_id=ticket.id,
        detail={"has_evidence": False},
        occurred_at=datetime(2026, 11, 20, 14, 0, tzinfo=UTC),
    )
    context.traced_ticket_events = [e1]


@given('the ticket has a rejected AI review followed by a manual response from "{role}"')
def step_rejected_then_manual(context, role: str):
    t = context.traced_ticket
    d = context.traced_diagnosis
    analyst = context.users[role]
    base = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)

    e1 = _append_chained(
        context,
        workspace_id=context.workspace.id,
        event_type="AiResolutionReviewed",
        entity_type="triage_diagnosis",
        actor_id=analyst.id,
        entity_id=d.id,
        ticket_id=t.id,
        detail={"decision": "REJECT", "previous_status": "PENDING_REVIEW", "resolves_ticket": False},
        occurred_at=base,
    )
    e2 = _append_chained(
        context,
        workspace_id=context.workspace.id,
        event_type="AiResolutionReviewed",
        entity_type="triage_diagnosis",
        actor_id=analyst.id,
        entity_id=d.id,
        ticket_id=t.id,
        detail={"decision": "MANUAL_RESPONSE", "previous_status": "REJECTED", "resolves_ticket": True},
        occurred_at=base + timedelta(minutes=3),
    )
    context.traced_ticket_events = [e1, e2]


@given('a second workspace exists with its own chained entry "{entry_label}" and ticket "{ticket_label}"')
def step_second_workspace_resources(context, entry_label: str, ticket_label: str):
    _ensure_store(context)
    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Empresa Externa", subdomain=f"ext-{uuid.uuid4().hex[:6]}")
    context.session.add(other_ws)
    context.session.flush()

    other_user = UserModel(
        id=uuid.uuid4(),
        workspace_id=other_ws.id,
        full_name="Colaborador Externo",
        email=f"ext-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=RoleName.COLLABORATOR,
        department="Operaciones",
    )
    context.session.add(other_user)
    context.session.flush()

    foreign_ticket = Ticket.register(
        workspace_id=other_ws.id,
        reporter_id=other_user.id,
        title="Incidente de otro workspace",
        description="Detalle aislado",
        impact_level=ImpactLevel.LOW,
    )
    SqlAlchemyTicketRepository(context.session).save(foreign_ticket)
    context.foreign_tickets[ticket_label] = foreign_ticket

    foreign_entry = _append_chained(
        context,
        workspace_id=other_ws.id,
        event_type="TicketRegistered",
        entity_type="ticket",
        actor_id=other_user.id,
        entity_id=foreign_ticket.id,
        ticket_id=foreign_ticket.id,
        detail={"label": entry_label},
        occurred_at=datetime(2026, 11, 20, 9, 0, tzinfo=UTC),
    )
    context.foreign_entries[entry_label] = foreign_entry


# --------------------------------------------------------------------------------------------------- acciones / tampering
@when('entry "{label}" has its detail tampered directly in PostgreSQL')
def step_tamper_detail_sql(context, label: str):
    entry = context.chained_entries[label]
    context.session.execute(
        text("UPDATE analytics_audit_log SET detail = CAST(:payload AS jsonb) WHERE id = :id"),
        {"id": entry.id, "payload": json.dumps({"tampered": True})},
    )
    context.session.flush()


@when("the second traced ticket audit event is tampered directly in PostgreSQL")
def step_tamper_traced_event_sql(context):
    target = context.traced_ticket_events[1]
    context.session.execute(
        text("UPDATE analytics_audit_log SET detail = CAST(:payload AS jsonb) WHERE id = :id"),
        {"id": target.id, "payload": json.dumps({"tampered": True})},
    )
    context.session.flush()


@when('entry "{label}" has its previous_hash replaced and its own hash recomputed in PostgreSQL')
def step_break_previous_hash_with_valid_self_hash(context, label: str):
    entry = context.chained_entries[label]
    fake_prev = "f" * 64
    recomputed = compute_integrity_hash(
        event_type=entry.event_type,
        workspace_id=entry.workspace_id,
        actor_id=entry.actor_id,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        ticket_id=entry.ticket_id,
        occurred_at=entry.occurred_at,
        detail=entry.detail,
        previous_hash=fake_prev,
    )
    context.session.execute(
        text(
            """
            UPDATE analytics_audit_log
               SET previous_hash = :prev,
                   integrity_hash = :hash
             WHERE id = :id
            """
        ),
        {"id": entry.id, "prev": fake_prev, "hash": recomputed},
    )
    context.session.flush()


@when('the "{role}" verifies the chained entry "{label}"')
def step_verify_entry(context, role: str, label: str):
    entry = context.chained_entries[label]
    context.response = context.client.get(
        f"/api/v1/audit/logs/{entry.id}/verify",
        headers=_headers(context, role),
    )


@when('the "{role}" verifies a nonexistent audit entry UUID')
def step_verify_nonexistent(context, role: str):
    context.response = context.client.get(
        f"/api/v1/audit/logs/{uuid.uuid4()}/verify",
        headers=_headers(context, role),
    )


@when('the "{role}" verifies the foreign workspace entry "{label}"')
def step_verify_foreign(context, role: str, label: str):
    entry = context.foreign_entries[label]
    context.response = context.client.get(
        f"/api/v1/audit/logs/{entry.id}/verify",
        headers=_headers(context, role),
    )


@when('the "{role}" requests the traceability of the traced ticket')
def step_trace_ticket(context, role: str):
    context.response = context.client.get(
        f"/api/v1/audit/tickets/{context.traced_ticket.id}/trace",
        headers=_headers(context, role),
    )


@when('the "{role}" requests the traceability of a nonexistent ticket UUID')
def step_trace_nonexistent(context, role: str):
    context.response = context.client.get(
        f"/api/v1/audit/tickets/{uuid.uuid4()}/trace",
        headers=_headers(context, role),
    )


@when('the "{role}" requests the traceability of the foreign workspace ticket "{label}"')
def step_trace_foreign(context, role: str, label: str):
    ticket = context.foreign_tickets[label]
    context.response = context.client.get(
        f"/api/v1/audit/tickets/{ticket.id}/trace",
        headers=_headers(context, role),
    )


@when('the "{role}" requests "{endpoint}" for the audit integrity resources')
def step_role_requests_endpoint(context, role: str, endpoint: str):
    url = (
        f"/api/v1/audit/logs/{context.chained_entries['C1'].id}/verify"
        if endpoint == "verify"
        else f"/api/v1/audit/tickets/{context.traced_ticket.id}/trace"
    )
    context.response = context.client.get(url, headers=_headers(context, role))


@when('an unauthenticated client with auth "{auth}" requests "{endpoint}"')
def step_unauth_requests_endpoint(context, auth: str, endpoint: str):
    url = (
        f"/api/v1/audit/logs/{context.chained_entries['C1'].id}/verify"
        if endpoint == "verify"
        else f"/api/v1/audit/tickets/{context.traced_ticket.id}/trace"
    )
    headers = {} if auth == "none" else {"Authorization": f"Bearer {auth}"}
    context.response = context.client.get(url, headers=headers)


@when('the "{role}" requests "{endpoint}" with invalid UUID "{raw_id}"')
def step_invalid_uuid_endpoint(context, role: str, endpoint: str, raw_id: str):
    url = (
        f"/api/v1/audit/logs/{raw_id}/verify"
        if endpoint == "verify"
        else f"/api/v1/audit/tickets/{raw_id}/trace"
    )
    context.response = context.client.get(url, headers=_headers(context, role))


# --------------------------------------------------------------------------------------------------- aserciones
def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() == "true"


@then('the integrity verification result is "{status}" with valid {valid}, hash_valid {hash_valid} and chain_valid {chain_valid}')
def step_assert_verify_status(context, status: str, valid: str, hash_valid: str, chain_valid: str):
    body = context.response.json()
    assert body["status"] == status, body
    assert body["valid"] is _parse_bool(valid), body
    assert body["hash_valid"] is _parse_bool(hash_valid), body
    assert body["chain_valid"] is _parse_bool(chain_valid), body
    assert body["message"], body


@then("the verification response reports a genesis entry with no predecessor")
def step_assert_genesis_verify(context):
    body = context.response.json()
    assert body["previous_entry_id"] is None, body
    assert body["stored_previous_hash"] is None, body
    assert body["expected_previous_hash"] is None, body


@then("the verification stored_hash matches computed_hash")
def step_assert_hash_matches(context):
    body = context.response.json()
    assert body["stored_hash"] == body["computed_hash"], body


@then("the verification stored_hash differs from computed_hash")
def step_assert_hash_differs(context):
    body = context.response.json()
    assert body["stored_hash"] != body["computed_hash"], body


@then("the verification stored_previous_hash differs from expected_previous_hash")
def step_assert_prev_hash_differs(context):
    body = context.response.json()
    assert body["stored_previous_hash"] != body["expected_previous_hash"], body


@then('the verification links entry "{label}" to predecessor "{prev_label}"')
def step_assert_prev_link(context, label: str, prev_label: str):
    body = context.response.json()
    entry = context.chained_entries[label]
    prev = context.chained_entries[prev_label]
    assert body["entry_id"] == str(entry.id), body
    assert body["seq"] == entry.seq, body
    assert body["previous_entry_id"] == str(prev.id), body
    assert body["expected_previous_hash"] == prev.integrity_hash, body


@then('the audit log listing shows "{l1}", "{l2}", "{l3}" with monotonic seq and valid previous_hash links')
def step_assert_listing_chain(context, l1: str, l2: str, l3: str):
    resp = context.client.get("/api/v1/audit/logs?size=10", headers=_headers(context, "IT_LEADER"))
    assert resp.status_code == 200, resp.text
    items_by_id = {item["id"]: item for item in resp.json()["items"]}
    e1, e2, e3 = context.chained_entries[l1], context.chained_entries[l2], context.chained_entries[l3]
    i1, i2, i3 = items_by_id[str(e1.id)], items_by_id[str(e2.id)], items_by_id[str(e3.id)]
    assert i1["seq"] < i2["seq"] < i3["seq"]
    assert i1["previous_hash"] is None
    assert i2["previous_hash"] == i1["integrity_hash"]
    assert i3["previous_hash"] == i2["integrity_hash"]


@then('the trace ticket summary shows status "{status}" and reporter "{reporter_role}"')
def step_assert_trace_ticket(context, status: str, reporter_role: str):
    body = context.response.json()
    ticket = body["ticket"]
    assert ticket["id"] == str(context.traced_ticket.id), ticket
    assert ticket["code"] == context.traced_ticket.code, ticket
    assert ticket["status"] == status, ticket
    assert ticket["reporter_name"] == context.users[reporter_role].full_name, ticket


@then('the trace diagnosis shows outcome "{outcome}", confidence "{confidence}" and review_status "{review_status}"')
def step_assert_trace_diagnosis(context, outcome: str, confidence: str, review_status: str):
    diag = context.response.json()["diagnosis"]
    assert diag is not None
    assert diag["outcome"] == outcome, diag
    assert diag["confidence_level"] == confidence, diag
    assert diag["review_status"] == review_status, diag


@then('the trace sources include {count:d} consulted source from "{doc_title}"')
def step_assert_trace_sources(context, count: int, doc_title: str):
    sources = context.response.json()["sources"]
    assert len(sources) == count, sources
    assert sources[0]["document_title"] == doc_title, sources
    assert sources[0]["reference"] == "F1", sources


@then('the trace authorizing analyst is "{role}" with decision "{decision}"')
def step_assert_trace_analyst(context, role: str, decision: str):
    analyst = context.response.json()["authorizing_analyst"]
    assert analyst is not None, context.response.json()
    assert analyst["id"] == str(context.users[role].id), analyst
    assert analyst["name"] == context.users[role].full_name, analyst
    assert analyst["role"] == role, analyst
    assert analyst["decision"] == decision, analyst


@then("the trace events are ordered chronologically with {count:d} events and all_hashes_valid {flag}")
def step_assert_trace_events(context, count: int, flag: str):
    body = context.response.json()
    events = body["events"]
    assert body["total_events"] == count, body
    assert len(events) == count, events
    assert body["all_hashes_valid"] is _parse_bool(flag), body
    keys = [(e["occurred_at"], e["seq"]) for e in events]
    assert keys == sorted(keys), keys


@then("the trace reports all_hashes_valid false")
def step_assert_trace_tampered(context):
    assert context.response.json()["all_hashes_valid"] is False, context.response.json()


@then("the trace diagnosis is null, sources are empty and authorizing_analyst is null")
def step_assert_trace_empty_diag(context):
    body = context.response.json()
    assert body["diagnosis"] is None, body
    assert body["sources"] == [], body
    assert body["authorizing_analyst"] is None, body


@then('the foreign entry "{label}" is a genesis entry with previous_hash null')
def step_assert_foreign_genesis(context, label: str):
    entry = context.foreign_entries[label]
    assert entry.previous_hash is None, entry


@then('the local entry "{l1}" is a genesis entry and "{l2}" links to "{l1_ref}"')
def step_assert_local_chain(context, l1: str, l2: str, l1_ref: str):
    e1 = context.chained_entries[l1]
    e2 = context.chained_entries[l2]
    assert e1.previous_hash is None, e1
    assert e2.previous_hash == e1.integrity_hash, e2
