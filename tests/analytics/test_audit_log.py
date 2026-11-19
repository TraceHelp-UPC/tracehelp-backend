"""Pruebas unitarias y de integración de la bitácora de auditoría (US15, T36)."""
import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.analytics.application.audit_log_service import AuditEventHandler
from app.analytics.domain.audit_entry import AuditEntry
from app.analytics.domain.repositories import AuditLogFilter
from app.analytics.infrastructure.persistence.audit_log_repository import SqlAlchemyAuditLogRepository
from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.events import TicketRegistered, TicketStatusChanged
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.domain.events import UserAuthenticated, UserRegistered
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.knowledge.domain.events import TechnicalDocumentUploaded
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.shared.infrastructure.pii_masker import RegexSpacyPiiMasker
from app.smart_triage.domain.events import AiResolutionReviewed, LowConfidenceAlertRaised, TriageCompleted
from tests.conftest import FAKE_HASH

masker = RegexSpacyPiiMasker("clave-de-pruebas-del-sello-pii-0123456789", spacy_model=None)


# --- Dominio y conversión de eventos (unitarias) --------------------------------------------------------------


def test_audit_entry_computes_deterministic_sha256_and_detects_tampering():
    workspace_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    ticket_id = uuid.uuid4()
    occurred = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    entry = AuditEntry.record(
        workspace_id=workspace_id,
        event_type="AiResolutionReviewed",
        actor_id=actor_id,
        entity_type="triage_diagnosis",
        entity_id=uuid.uuid4(),
        ticket_id=ticket_id,
        detail={"decision": "APPROVE", "resolves_ticket": True},
        occurred_at=occurred,
    )
    assert len(entry.integrity_hash) == 64
    assert entry.verify_integrity() is True

    tampered = AuditEntry(
        id=entry.id,
        workspace_id=entry.workspace_id,
        event_type=entry.event_type,
        actor_id=entry.actor_id,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        ticket_id=entry.ticket_id,
        detail={"decision": "REJECT", "resolves_ticket": False},
        integrity_hash=entry.integrity_hash,
        occurred_at=entry.occurred_at,
    )
    assert tampered.verify_integrity() is False


def test_handler_masks_pii_in_free_text_fields():
    handler = AuditEventHandler(masker=masker)
    workspace_id = uuid.uuid4()
    ticket_id = uuid.uuid4()
    reviewer_id = uuid.uuid4()

    review_event = AiResolutionReviewed(
        diagnosis_id=uuid.uuid4(),
        ticket_id=ticket_id,
        workspace_id=workspace_id,
        reviewer_id=reviewer_id,
        decision="REJECT",
        previous_status="PENDING_REVIEW",
        ai_outcome="ANSWERED",
        resolves_ticket=False,
        note="El usuario juan.perez@empresa.pe reportó desde 10.0.0.25 que no aplica",
    )
    entry = handler.to_audit_entry(review_event)
    assert entry is not None
    assert "juan.perez@empresa.pe" not in entry.detail["note"]
    assert "10.0.0.25" not in entry.detail["note"]
    assert entry.verify_integrity()

    status_event = TicketStatusChanged(
        ticket_id=ticket_id,
        workspace_id=workspace_id,
        reporter_id=uuid.uuid4(),
        previous_status="ASSIGNED_L1",
        new_status="ESCALATED_L2",
        changed_by=reviewer_id,
        reason="Credenciales clave=SuperSecreta123 de ana@empresa.pe bloqueadas",
    )
    status_entry = handler.to_audit_entry(status_event)
    assert status_entry is not None
    assert "SuperSecreta123" not in status_entry.detail["reason"]
    assert "ana@empresa.pe" not in status_entry.detail["reason"]


@pytest.mark.parametrize(
    "event",
    [
        UserRegistered(user_id=uuid.uuid4(), workspace_id=uuid.uuid4(), role=RoleName.ANALYST_L1),
        UserAuthenticated(user_id=uuid.uuid4(), workspace_id=uuid.uuid4()),
        TicketRegistered(ticket_id=uuid.uuid4(), workspace_id=uuid.uuid4(), reporter_id=uuid.uuid4(), has_evidence=True),
        TechnicalDocumentUploaded(
            document_id=uuid.uuid4(), job_id=uuid.uuid4(), workspace_id=uuid.uuid4(), uploaded_by=uuid.uuid4()
        ),
        LowConfidenceAlertRaised(
            workspace_id=uuid.uuid4(), ticket_id=uuid.uuid4(), best_score=0.45, similarity_threshold=0.68, fragments_retrieved=2
        ),
        TriageCompleted(
            diagnosis_id=uuid.uuid4(),
            ticket_id=uuid.uuid4(),
            workspace_id=uuid.uuid4(),
            outcome="ANSWERED",
            confidence_level="GROUNDED",
            best_score=0.78,
            route="PENDING_ASSIGNMENT",
        ),
    ],
)
def test_handler_translates_all_domain_events(event):
    handler = AuditEventHandler(masker=masker)
    entry = handler.to_audit_entry(event)
    assert entry is not None
    assert entry.event_type == type(event).__name__
    assert entry.workspace_id == event.workspace_id
    assert entry.verify_integrity()


# --- Persistencia y endpoint GET /api/v1/audit-log (integración) ----------------------------------------------


@pytest.fixture()
def audit_setup(db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    leader = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace.id,
        full_name="Líder Demo",
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
        title="Error VPN",
        description="No conecta la VPN",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.status = TicketStatus.ASSIGNED_L1
    ticket.assigned_analyst_id = analyst.id
    SqlAlchemyTicketRepository(db_session).save(ticket)

    bus = InMemoryEventBus()
    handler = AuditEventHandler(session_factory=lambda: contextlib.nullcontext(db_session), masker=masker)
    from app.shared.domain.aggregate_root import DomainEvent

    bus.subscribe(DomainEvent, handler)

    return {
        "workspace": workspace,
        "collaborator": collaborator,
        "analyst": analyst,
        "leader": leader,
        "ticket": ticket,
        "bus": bus,
        "headers": {
            "leader": auth_headers(db_session, leader),
            "analyst": auth_headers(db_session, analyst),
            "collaborator": auth_headers(db_session, collaborator),
        },
    }


def test_event_bus_persists_audit_entries_and_filters_by_event_ticket_and_dates(api_client, db_session, audit_setup):
    ws = audit_setup["workspace"]
    ticket = audit_setup["ticket"]
    analyst = audit_setup["analyst"]
    collaborator = audit_setup["collaborator"]
    bus = audit_setup["bus"]

    t1 = datetime(2026, 11, 8, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 11, 8, 11, 0, tzinfo=UTC)
    t3 = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)

    bus.publish_all(
        [
            TicketRegistered(
                ticket_id=ticket.id,
                workspace_id=ws.id,
                reporter_id=collaborator.id,
                has_evidence=False,
                occurred_on=t1,
            ),
            TicketStatusChanged(
                ticket_id=ticket.id,
                workspace_id=ws.id,
                reporter_id=collaborator.id,
                previous_status="OPEN",
                new_status="ASSIGNED_L1",
                changed_by=analyst.id,
                reason="Atendido por soporte para ana@empresa.pe",
                occurred_on=t2,
            ),
            AiResolutionReviewed(
                diagnosis_id=uuid.uuid4(),
                ticket_id=ticket.id,
                workspace_id=ws.id,
                reviewer_id=analyst.id,
                decision="APPROVE",
                previous_status="PENDING_REVIEW",
                ai_outcome="ANSWERED",
                resolves_ticket=True,
                note="Aprobado sin cambios",
                occurred_on=t3,
            ),
        ]
    )

    response = api_client.get("/api/v1/audit-log", headers=audit_setup["headers"]["leader"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 3
    assert [item["event_type"] for item in body["items"]] == [
        "AiResolutionReviewed",
        "TicketStatusChanged",
        "TicketRegistered",
    ]
    assert body["items"][0]["actor_name"] == "Analista Demo"
    assert "ana@empresa.pe" not in body["items"][1]["detail"]["reason"]

    # Filtro por event_type
    by_event = api_client.get(
        "/api/v1/audit-log?event_type=AiResolutionReviewed", headers=audit_setup["headers"]["leader"]
    ).json()
    assert by_event["total"] == 1 and by_event["items"][0]["event_type"] == "AiResolutionReviewed"

    # Filtro por ticket_id
    by_ticket = api_client.get(
        f"/api/v1/audit-log?ticket_id={ticket.id}", headers=audit_setup["headers"]["leader"]
    ).json()
    assert by_ticket["total"] == 3

    # Filtro por rango de fechas
    from_iso = (t2 - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    to_iso = (t2 + timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    by_date = api_client.get(
        f"/api/v1/audit-log?from_date={from_iso}&to_date={to_iso}", headers=audit_setup["headers"]["leader"]
    ).json()
    assert [i["event_type"] for i in by_date["items"]] == ["TicketStatusChanged"]


def test_only_it_leader_with_audit_read_can_query_audit_log(api_client, audit_setup):
    assert api_client.get("/api/v1/audit-log").status_code == 401
    assert api_client.get("/api/v1/audit-log", headers=audit_setup["headers"]["collaborator"]).status_code == 403
    assert api_client.get("/api/v1/audit-log", headers=audit_setup["headers"]["analyst"]).status_code == 403


def test_audit_log_is_isolated_by_workspace(api_client, db_session, audit_setup):
    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    db_session.add(other_ws)
    db_session.flush()
    SqlAlchemyAuditLogRepository(db_session).append(
        AuditEntry.record(
            workspace_id=other_ws.id,
            event_type="UserAuthenticated",
            entity_type="user",
        )
    )
    body = api_client.get("/api/v1/audit-log", headers=audit_setup["headers"]["leader"]).json()
    assert body["total"] == 0


def test_invalid_pagination_or_date_range_returns_400(api_client, audit_setup):
    headers = audit_setup["headers"]["leader"]
    assert api_client.get("/api/v1/audit-log?page=0", headers=headers).status_code == 400
    assert api_client.get("/api/v1/audit-log?size=101", headers=headers).status_code == 400
    assert (
        api_client.get(
            "/api/v1/audit-log?from_date=2026-11-09T00:00:00Z&to_date=2026-11-08T00:00:00Z", headers=headers
        ).status_code
        == 400
    )


# --- TS06 · GET /api/v1/audit/logs (T94) ------------------------------------------------------------------------

CANONICAL = "/api/v1/audit/logs"
PAGE_PROBLEM = "urn:tracehelp:problems:invalid-page-request"


def _seed_entries(db_session, workspace_id, count, *, actor_id=None, event_type="UserAuthenticated", ticket_id=None,
                  start=datetime(2026, 11, 1, 8, 0, tzinfo=UTC)):
    repo = SqlAlchemyAuditLogRepository(db_session)
    for i in range(count):
        repo.append(
            AuditEntry.record(
                workspace_id=workspace_id,
                event_type=event_type,
                actor_id=actor_id,
                entity_type="user",
                ticket_id=ticket_id,
                occurred_at=start + timedelta(minutes=i),
            )
        )


def test_filter_dependency_normalizes_naive_dates_to_utc_and_validates_range():
    from app.analytics.domain.exceptions import InvalidDateRangeError
    from app.analytics.interfaces.rest.dependencies import audit_log_filter

    ws = uuid.uuid4()

    class _User:
        workspace_id = ws

    criteria = audit_log_filter(
        event_type="  TriageCompleted ",
        ticket_id=None,
        actor_id=None,
        from_date=datetime(2026, 11, 1, 0, 0),
        to_date=datetime(2026, 11, 2, 0, 0, tzinfo=UTC),
        current_user=_User(),
    )
    assert criteria.workspace_id == ws
    assert criteria.event_type == "TriageCompleted"
    assert criteria.from_date.tzinfo is UTC and criteria.from_date == datetime(2026, 11, 1, tzinfo=UTC)
    with pytest.raises(InvalidDateRangeError):
        audit_log_filter(
            event_type=None, ticket_id=None, actor_id=None,
            from_date=datetime(2026, 11, 3), to_date=datetime(2026, 11, 2, tzinfo=UTC), current_user=_User(),
        )


def test_audit_logs_paginates_with_metadata(api_client, db_session, audit_setup):
    leader = audit_setup["headers"]["leader"]
    ws_id = audit_setup["workspace"].id
    _seed_entries(db_session, ws_id, 25)
    body = api_client.get(f"{CANONICAL}?page=2&size=10", headers=leader).json()
    assert (body["page"], body["size"], body["total"], body["total_pages"]) == (2, 10, 25, 3)
    assert len(body["items"]) == 10
    dates = [i["occurred_at"] for i in body["items"]]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.parametrize("query", ["page=0", "page=-1", "size=0", "size=101", "page=99"])
def test_audit_logs_out_of_range_pagination_is_400_invalid_page_request(api_client, db_session, audit_setup, query):
    _seed_entries(db_session, audit_setup["workspace"].id, 3)
    response = api_client.get(f"{CANONICAL}?{query}", headers=audit_setup["headers"]["leader"])
    assert response.status_code == 400
    assert response.json()["type"] == PAGE_PROBLEM
    assert response.json()["instance"] == CANONICAL


def test_audit_logs_empty_first_page_is_200_and_non_numeric_page_is_422(api_client, audit_setup):
    leader = audit_setup["headers"]["leader"]
    body = api_client.get(CANONICAL, headers=leader).json()
    assert body["items"] == [] and body["total"] == 0
    bad = api_client.get(f"{CANONICAL}?page=abc", headers=leader)
    assert bad.status_code == 422 and bad.json()["type"].endswith("validation-error")
    assert api_client.get(f"{CANONICAL}?actor_id=no-uuid", headers=leader).status_code == 422


def test_audit_logs_combined_filters_including_actor(api_client, db_session, audit_setup):
    leader = audit_setup["headers"]["leader"]
    ws_id = audit_setup["workspace"].id
    analyst_a, analyst_b = uuid.uuid4(), audit_setup["analyst"].id
    ticket_id = audit_setup["ticket"].id
    base = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    _seed_entries(db_session, ws_id, 2, actor_id=audit_setup["analyst"].id, event_type="AiResolutionReviewed",
                  ticket_id=ticket_id, start=base)
    _seed_entries(db_session, ws_id, 1, actor_id=audit_setup["analyst"].id, event_type="TriageCompleted",
                  start=base + timedelta(hours=5))
    _seed_entries(db_session, ws_id, 1, actor_id=None, event_type="AiResolutionReviewed",
                  start=base + timedelta(hours=1))
    assert analyst_a != analyst_b

    by_actor = api_client.get(f"{CANONICAL}?actor_id={analyst_b}", headers=leader).json()
    assert by_actor["total"] == 3
    combined = api_client.get(
        f"{CANONICAL}?actor_id={analyst_b}&event_type=AiResolutionReviewed&ticket_id={ticket_id}", headers=leader
    ).json()
    assert combined["total"] == 2
    # fechas sin zona horaria = UTC; to_date excluye la entrada de +5h
    ranged = api_client.get(
        f"{CANONICAL}?actor_id={analyst_b}&from_date=2026-11-10T00:00:00&to_date=2026-11-10T10:00:00", headers=leader
    ).json()
    assert ranged["total"] == 2
    assert api_client.get(f"{CANONICAL}?actor_id={analyst_a}", headers=leader).json()["total"] == 0
    assert api_client.get(f"{CANONICAL}?event_type=NoExiste", headers=leader).json()["total"] == 0


def test_audit_logs_inverted_date_range_is_400_invalid_date_range(api_client, audit_setup):
    response = api_client.get(
        f"{CANONICAL}?from_date=2026-11-09T00:00:00Z&to_date=2026-11-08T00:00:00Z",
        headers=audit_setup["headers"]["leader"],
    )
    assert response.status_code == 400
    assert response.json()["type"] == "urn:tracehelp:problems:invalid-date-range"


def test_audit_logs_requires_audit_read(api_client, audit_setup):
    assert api_client.get(CANONICAL).status_code == 401
    for role in ("collaborator", "analyst"):
        response = api_client.get(CANONICAL, headers=audit_setup["headers"][role])
        assert response.status_code == 403
        assert response.json()["type"] == "urn:tracehelp:problems:forbidden"


def test_legacy_alias_is_deprecated_with_headers_and_same_response(api_client, db_session, audit_setup):
    leader = audit_setup["headers"]["leader"]
    _seed_entries(db_session, audit_setup["workspace"].id, 3)
    legacy = api_client.get("/api/v1/audit-log", headers=leader)
    canonical = api_client.get(CANONICAL, headers=leader)
    assert legacy.status_code == 200 and legacy.json() == canonical.json()
    assert legacy.headers["Deprecation"] == "true"
    assert legacy.headers["Link"] == f'<{CANONICAL}>; rel="successor-version"'
    assert "Deprecation" not in canonical.headers
    bad = api_client.get("/api/v1/audit-log?size=101", headers=leader)
    assert bad.status_code == 400 and bad.json()["type"] == PAGE_PROBLEM


def test_openapi_documents_canonical_route_and_deprecated_alias(api_client):
    paths = api_client.get("/openapi.json").json()["paths"]
    assert paths["/api/v1/audit-log"]["get"]["deprecated"] is True
    canonical = paths[CANONICAL]["get"]
    assert "deprecated" not in canonical or canonical["deprecated"] is False
    assert "actor_id" in {p["name"] for p in canonical["parameters"]}
    assert {"200", "400", "401", "403", "422"} <= set(canonical["responses"])
