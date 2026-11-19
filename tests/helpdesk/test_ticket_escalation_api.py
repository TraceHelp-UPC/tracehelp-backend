"""Pruebas de integración de POST /escalate, POST /return-to-l1 y migración 0012 (US17, T79).

Requieren TEST_DATABASE_URL (PostgreSQL local Docker).
"""
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.analytics.infrastructure.persistence.models import AuditLogModel
from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.domain.events import MessagePosted, TicketEscalated, TicketReturnedToL1
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.shared.domain.specialist_group import SpecialistGroup
from app.shared.infrastructure.event_bus import event_bus
from tests.conftest import FAKE_HASH

S = TicketStatus


def _user(
    db_session,
    workspace_id: uuid.UUID,
    role: RoleName,
    name: str,
    *,
    specialist_group: SpecialistGroup | None = None,
) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        full_name=name,
        email=f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=role,
        department="TI",
        specialist_group=specialist_group,
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def people(db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"other-{uuid.uuid4().hex[:6]}")
    db_session.add(other_ws)
    db_session.flush()

    users = {
        "collaborator": collaborator,
        "analyst": analyst,
        "l2_redes": _user(
            db_session, workspace.id, RoleName.SPECIALIST_L2, "Especialista Redes", specialist_group=SpecialistGroup.REDES
        ),
        "l2_seguridad": _user(
            db_session,
            workspace.id,
            RoleName.SPECIALIST_L2,
            "Especialista Seguridad",
            specialist_group=SpecialistGroup.SEGURIDAD,
        ),
        "l2_nogroup": _user(
            db_session, workspace.id, RoleName.SPECIALIST_L2, "Especialista General", specialist_group=None
        ),
        "leader": _user(db_session, workspace.id, RoleName.IT_LEADER, "Líder TI"),
        "other_ws_analyst": _user(db_session, other_ws.id, RoleName.ANALYST_L1, "Analista Ajeno"),
        "other_ws_l2": _user(
            db_session, other_ws.id, RoleName.SPECIALIST_L2, "Especialista Ajeno", specialist_group=SpecialistGroup.REDES
        ),
    }
    return {
        "workspace": workspace,
        "other_workspace": other_ws,
        "users": users,
        "headers": {k: auth_headers(db_session, u) for k, u in users.items()},
    }


@pytest.fixture()
def make_ticket(db_session, people):
    repo = SqlAlchemyTicketRepository(db_session)

    def _make(
        status: TicketStatus = S.ASSIGNED_L1,
        *,
        with_analyst: bool = True,
        escalated_group: SpecialistGroup | None = None,
        escalated_at: datetime | None = None,
        assigned_specialist_id: uuid.UUID | None = None,
        specialist_claimed_at: datetime | None = None,
    ) -> Ticket:
        ticket = Ticket.register(
            workspace_id=people["workspace"].id,
            reporter_id=people["users"]["collaborator"].id,
            title="VPN error 809 al conectar desde casa",
            description="Al conectar a la VPN corporativa aparece el error 809.",
            impact_level=ImpactLevel.MEDIUM,
            affected_module="VPN corporativa",
        )
        ticket.pull_events()
        ticket.status = status
        ticket.category = TicketCategory.NETWORK_VPN
        ticket.priority = TicketPriority.HIGH
        ticket.current_tier = SupportTier.TIER_L2 if status is S.ESCALATED_L2 else SupportTier.TIER_L1
        ticket.assigned_analyst_id = people["users"]["analyst"].id if with_analyst else None
        ticket.escalated_group = escalated_group
        ticket.escalated_at = escalated_at
        ticket.assigned_specialist_id = assigned_specialist_id
        ticket.specialist_claimed_at = specialist_claimed_at
        return repo.save(ticket)

    return _make


def _seed_triage_diagnosis(db_session, *, workspace_id: uuid.UUID, ticket_id: uuid.UUID) -> None:
    """Inserta una fila en triage_diagnoses por SQL directo (mismo aislamiento que el adaptador ACL)."""
    db_session.execute(
        text(
            """
            INSERT INTO triage_diagnoses (
                id, workspace_id, ticket_id, outcome, confidence_level, best_score,
                review_status, summary, steps, sources, suggested_category, suggested_priority,
                ocr_legible, ocr_error_codes, ocr_text
            ) VALUES (
                :id, :workspace_id, :ticket_id, 'ANSWERED', 'GROUNDED', 0.76,
                'PENDING_REVIEW', :summary, CAST(:steps AS jsonb), CAST(:sources AS jsonb),
                'Red/VPN', 'HIGH', true, CAST(:ocr_codes AS jsonb), :ocr_text
            )
            """
        ),
        {
            "id": uuid.uuid4(),
            "workspace_id": workspace_id,
            "ticket_id": ticket_id,
            "summary": "El error 809 indica bloqueo de puertos UDP 500/4500 en el firewall.",
            "steps": '["Verificar conexión a internet", "Revisar regla UDP 4500"]',
            "sources": (
                '[{"reference": "F1", "chunk_id": "00000000-0000-4000-8000-000000000001", '
                '"document_id": "00000000-0000-4000-8000-000000000002", '
                '"document_title": "Manual VPN Corporativa", '
                '"citation": "Sección 3.1 · Error 809", "similarity": 0.76}]'
            ),
            "ocr_codes": '["ERR_809"]',
            "ocr_text": "Error 809 al conectar [EMAIL] desde cliente VPN",
        },
    )
    db_session.flush()


# --- Migración 0012: columnas, índices, FK y CHECK ----------------------------------------------------------

def test_migration_0012_schema_and_check_constraint(db_session, make_ticket):
    inspector = inspect(db_session.bind)
    columns = {col["name"]: col for col in inspector.get_columns("helpdesk_tickets")}
    for name in ("escalated_group", "escalated_at", "assigned_specialist_id", "specialist_claimed_at"):
        assert name in columns
        assert columns[name]["nullable"] is True

    indexes = {idx["name"]: idx["column_names"] for idx in inspector.get_indexes("helpdesk_tickets")}
    assert indexes.get("ix_helpdesk_tickets_assigned_specialist_id") == ["assigned_specialist_id"]
    assert indexes.get("ix_helpdesk_tickets_workspace_escalated_group") == ["workspace_id", "escalated_group"]

    fks = {fk["name"]: fk for fk in inspector.get_foreign_keys("helpdesk_tickets")}
    assert "fk_helpdesk_tickets_assigned_specialist_id" in fks
    assert fks["fk_helpdesk_tickets_assigned_specialist_id"]["referred_table"] == "iam_users"

    checks = {ck["name"] for ck in inspector.get_check_constraints("helpdesk_tickets")}
    assert "ck_helpdesk_tickets_escalated_group" in checks

    # El CHECK constraint rechaza un grupo fuera del catálogo SpecialistGroup
    ticket = make_ticket()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(
                text("UPDATE helpdesk_tickets SET escalated_group = 'VENTAS' WHERE id = :id"),
                {"id": ticket.id},
            )


# --- POST /api/v1/tickets/{id}/escalate ---------------------------------------------------------------------

def test_escalate_with_triage_context_stores_internal_snapshot_and_audits(api_client, db_session, people, make_ticket):
    ticket = make_ticket(
        status=S.ASSIGNED_L1,
        assigned_specialist_id=people["users"]["l2_redes"].id,
        specialist_claimed_at=datetime(2026, 11, 20, 10, 0, tzinfo=UTC),
    )
    _seed_triage_diagnosis(db_session, workspace_id=people["workspace"].id, ticket_id=ticket.id)

    captured: list = []
    event_bus.subscribe(TicketEscalated, captured.append)
    event_bus.subscribe(MessagePosted, captured.append)
    try:
        response = api_client.post(
            f"/api/v1/tickets/{ticket.id}/escalate",
            json={
                "specialist_group": "REDES",
                "reason": "El error 809 persiste tras reiniciar el perfil VPN; requiere firewall.",
            },
            headers=people["headers"]["analyst"],
        )
    finally:
        event_bus._handlers[TicketEscalated].remove(captured.append)
        event_bus._handlers[MessagePosted].remove(captured.append)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ESCALATED_L2"
    assert body["current_tier"] == "TIER_L2"
    assert body["escalated_group"] == "REDES"
    assert body["escalated_at"] is not None
    assert body["assigned_analyst_id"] == str(people["users"]["analyst"].id)
    assert body["assigned_specialist_id"] is None
    assert body["specialist_claimed_at"] is None

    # Solo se emitió TicketEscalated (no MessagePosted)
    assert len(captured) == 1 and isinstance(captured[0], TicketEscalated)
    assert captured[0].has_triage_snapshot is True

    # L2 ve la nota interna con el contexto completo en detalle y mensajes
    l2_detail = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"]["l2_redes"]).json()
    assert l2_detail["escalated_group"] == "REDES"
    assert len(l2_detail["comments"]) == 1
    snapshot = l2_detail["comments"][0]
    assert snapshot["is_internal_note"] is True
    assert "[ESCALAMIENTO A L2 · REDES]" in snapshot["content"]
    assert "bloqueo de puertos UDP 500/4500" in snapshot["content"]
    assert "ERR_809" in snapshot["content"]
    assert "Error 809 al conectar [EMAIL]" in snapshot["content"]
    assert "- [F1] Sección 3.1 · Error 809 (Manual VPN Corporativa)" in snapshot["content"]

    # El colaborador NUNCA ve la nota interna ni en GET /tickets/{id} ni en /messages
    colab_detail = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"]["collaborator"]).json()
    assert colab_detail["comments"] == []
    colab_msgs = api_client.get(f"/api/v1/tickets/{ticket.id}/messages", headers=people["headers"]["collaborator"]).json()
    assert colab_msgs["items"] == [] and colab_msgs["total"] == 0

    # Auditoría registró TicketEscalated con actor_id = analista
    audit = db_session.scalars(
        select(AuditLogModel).where(
            AuditLogModel.ticket_id == ticket.id,
            AuditLogModel.event_type == "TicketEscalated",
        )
    ).one()
    assert audit.actor_id == people["users"]["analyst"].id
    assert audit.entity_type == "ticket"
    assert audit.detail["specialist_group"] == "REDES"
    assert audit.detail["has_triage_snapshot"] is True


def test_escalate_without_triage_diagnosis_succeeds_with_fallback_snapshot(api_client, people, make_ticket):
    ticket = make_ticket(status=S.ASSIGNED_L1)

    captured: list = []
    event_bus.subscribe(TicketEscalated, captured.append)
    try:
        response = api_client.post(
            f"/api/v1/tickets/{ticket.id}/escalate",
            json={"specialist_group": "INFRAESTRUCTURA", "reason": "Servidor ERP sin respuesta desde esta mañana."},
            headers=people["headers"]["analyst"],
        )
    finally:
        event_bus._handlers[TicketEscalated].remove(captured.append)

    assert response.status_code == 200, response.text
    assert response.json()["escalated_group"] == "INFRAESTRUCTURA"
    assert len(captured) == 1 and captured[0].has_triage_snapshot is False

    l2_detail = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"]["l2_redes"]).json()
    snapshot_text = l2_detail["comments"][0]["content"]
    assert "Triaje IA: Sin diagnóstico automático registrado al momento del escalamiento." in snapshot_text
    assert "OCR (anonimizado): Sin evidencia OCR" in snapshot_text
    assert "- Sin fuentes consultadas" in snapshot_text


@pytest.mark.parametrize(
    "payload",
    [
        {"specialist_group": "VENTAS", "reason": "Motivo válido de prueba"},
        {"specialist_group": "REDES", "reason": "   "},
        {"specialist_group": "REDES", "reason": "abc"},
        {"specialist_group": "REDES", "reason": "x" * 501},
        {"specialist_group": "REDES", "reason": "Motivo válido", "extra_field": True},
    ],
)
def test_escalate_rejects_invalid_payload_with_422_problem_details(api_client, people, make_ticket, payload):
    ticket = make_ticket(status=S.ASSIGNED_L1)
    response = api_client.post(
        f"/api/v1/tickets/{ticket.id}/escalate", json=payload, headers=people["headers"]["analyst"]
    )
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == "urn:tracehelp:problems:validation-error"
    assert body["errors"]


@pytest.mark.parametrize("status", [S.PENDING_ASSIGNMENT, S.ESCALATED_L2, S.RESOLVED, S.CLOSED])
def test_escalate_rejects_ticket_not_in_assigned_l1_with_422(api_client, people, make_ticket, status):
    ticket = make_ticket(status=status)
    response = api_client.post(
        f"/api/v1/tickets/{ticket.id}/escalate",
        json={"specialist_group": "REDES", "reason": "Intento de escalar fuera de estado"},
        headers=people["headers"]["analyst"],
    )
    assert response.status_code == 422
    assert response.json()["type"] == "urn:tracehelp:problems:invalid-ticket-state-transition"


@pytest.mark.parametrize("role_key", ["collaborator", "l2_redes", "leader"])
def test_escalate_forbidden_without_permission(api_client, people, make_ticket, role_key):
    ticket = make_ticket(status=S.ASSIGNED_L1)
    response = api_client.post(
        f"/api/v1/tickets/{ticket.id}/escalate",
        json={"specialist_group": "REDES", "reason": "No debería tener permiso para escalar"},
        headers=people["headers"][role_key],
    )
    assert response.status_code == 403
    assert response.json()["type"] == "urn:tracehelp:problems:forbidden"


def test_escalate_returns_401_without_token_and_404_for_missing_or_other_workspace(api_client, people, make_ticket):
    ticket = make_ticket(status=S.ASSIGNED_L1)
    payload = {"specialist_group": "REDES", "reason": "Requiere revisión de firewall"}

    unauth = api_client.post(f"/api/v1/tickets/{ticket.id}/escalate", json=payload)
    assert unauth.status_code == 401

    missing = api_client.post(f"/api/v1/tickets/{uuid.uuid4()}/escalate", json=payload, headers=people["headers"]["analyst"])
    assert missing.status_code == 404
    assert missing.json()["type"] == "urn:tracehelp:problems:ticket-not-found"

    other_ws = api_client.post(
        f"/api/v1/tickets/{ticket.id}/escalate", json=payload, headers=people["headers"]["other_ws_analyst"]
    )
    assert other_ws.status_code == 404
    assert other_ws.json()["type"] == "urn:tracehelp:problems:ticket-not-found"


# --- POST /api/v1/tickets/{id}/return-to-l1 -----------------------------------------------------------------

def test_return_to_l1_by_matching_specialist_restores_l1_queue_and_audits(api_client, db_session, people, make_ticket):
    escalated_at = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    ticket = make_ticket(
        status=S.ESCALATED_L2,
        escalated_group=SpecialistGroup.REDES,
        escalated_at=escalated_at,
        assigned_specialist_id=people["users"]["l2_redes"].id,
        specialist_claimed_at=datetime(2026, 11, 20, 14, 15, tzinfo=UTC),
    )

    captured: list = []
    event_bus.subscribe(TicketReturnedToL1, captured.append)
    try:
        response = api_client.post(
            f"/api/v1/tickets/{ticket.id}/return-to-l1",
            json={"requested_info": "Solicitar al colaborador la captura del comando ipconfig /all."},
            headers=people["headers"]["l2_redes"],
        )
    finally:
        event_bus._handlers[TicketReturnedToL1].remove(captured.append)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ASSIGNED_L1"
    assert body["current_tier"] == "TIER_L1"
    assert body["assigned_analyst_id"] == str(people["users"]["analyst"].id)
    assert body["assigned_specialist_id"] is None
    assert body["specialist_claimed_at"] is None
    assert body["escalated_group"] == "REDES"
    assert body["escalated_at"] is not None
    assert len(captured) == 1

    # Reaparece en Mi cola del L1 original
    queue = api_client.get("/api/v1/tickets/queue?scope=mine", headers=people["headers"]["analyst"]).json()
    assert str(ticket.id) in [item["id"] for item in queue["items"]]

    # Nota interna visible para L1, oculta para colaborador
    l1_detail = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"]["analyst"]).json()
    assert len(l1_detail["comments"]) == 1
    assert l1_detail["comments"][0]["is_internal_note"] is True
    assert "[DEVOLUCIÓN DE L2 A L1 · REDES]" in l1_detail["comments"][0]["content"]
    assert "ipconfig /all" in l1_detail["comments"][0]["content"]

    colab_detail = api_client.get(f"/api/v1/tickets/{ticket.id}", headers=people["headers"]["collaborator"]).json()
    assert colab_detail["comments"] == []

    # Auditoría registró TicketReturnedToL1
    audit = db_session.scalars(
        select(AuditLogModel).where(
            AuditLogModel.ticket_id == ticket.id,
            AuditLogModel.event_type == "TicketReturnedToL1",
        )
    ).one()
    assert audit.actor_id == people["users"]["l2_redes"].id
    assert audit.entity_type == "ticket"
    assert audit.detail["escalated_group"] == "REDES"
    assert audit.detail["assigned_analyst_id"] == str(people["users"]["analyst"].id)


def test_return_to_l1_group_guards_and_legacy_null_group(api_client, people, make_ticket):
    redes_ticket = make_ticket(
        status=S.ESCALATED_L2,
        escalated_group=SpecialistGroup.REDES,
        escalated_at=datetime(2026, 11, 20, 14, 0, tzinfo=UTC),
    )
    payload = {"requested_info": "Confirmar si ocurre en red doméstica o móvil."}

    # Especialista de otro grupo -> 403 ticket-status-change-forbidden
    other_group = api_client.post(
        f"/api/v1/tickets/{redes_ticket.id}/return-to-l1", json=payload, headers=people["headers"]["l2_seguridad"]
    )
    assert other_group.status_code == 403
    assert other_group.json()["type"] == "urn:tracehelp:problems:ticket-status-change-forbidden"
    assert other_group.json()["detail"] == "El ticket está escalado al grupo REDES."

    # Especialista sin grupo sobre ticket con grupo -> 403
    no_group = api_client.post(
        f"/api/v1/tickets/{redes_ticket.id}/return-to-l1", json=payload, headers=people["headers"]["l2_nogroup"]
    )
    assert no_group.status_code == 403
    assert no_group.json()["type"] == "urn:tracehelp:problems:ticket-status-change-forbidden"

    # Ticket legado con escalated_group = None -> cualquier L2 (incluso sin grupo) puede devolverlo
    legacy_ticket = make_ticket(status=S.ESCALATED_L2, escalated_group=None)
    ok = api_client.post(
        f"/api/v1/tickets/{legacy_ticket.id}/return-to-l1", json=payload, headers=people["headers"]["l2_nogroup"]
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "ASSIGNED_L1"
    assert ok.json()["escalated_group"] is None


def test_return_to_l1_rejects_legacy_ticket_without_original_analyst_with_400(api_client, people, make_ticket):
    ticket = make_ticket(status=S.ESCALATED_L2, with_analyst=False, escalated_group=SpecialistGroup.REDES)
    response = api_client.post(
        f"/api/v1/tickets/{ticket.id}/return-to-l1",
        json={"requested_info": "Solicitar datos adicionales al usuario"},
        headers=people["headers"]["l2_redes"],
    )
    assert response.status_code == 400
    assert response.json()["type"] == "urn:tracehelp:problems:invalid-ticket-data"
    assert response.json()["detail"] == "El ticket no tiene un analista L1 original asignado para devolverlo."


@pytest.mark.parametrize("status", [S.PENDING_ASSIGNMENT, S.ASSIGNED_L1, S.REOPENED, S.RESOLVED])
def test_return_to_l1_rejects_non_escalated_statuses_with_422(api_client, people, make_ticket, status):
    ticket = make_ticket(status=status)
    response = api_client.post(
        f"/api/v1/tickets/{ticket.id}/return-to-l1",
        json={"requested_info": "Solicitar datos adicionales al usuario"},
        headers=people["headers"]["l2_redes"],
    )
    assert response.status_code == 422
    assert response.json()["type"] == "urn:tracehelp:problems:invalid-ticket-state-transition"


@pytest.mark.parametrize(
    "payload",
    [
        {"requested_info": "   "},
        {"requested_info": "abc"},
        {"requested_info": "x" * 2001},
        {"requested_info": "Información válida", "unknown": 1},
    ],
)
def test_return_to_l1_rejects_invalid_payload_with_422(api_client, people, make_ticket, payload):
    ticket = make_ticket(status=S.ESCALATED_L2, escalated_group=SpecialistGroup.REDES)
    response = api_client.post(
        f"/api/v1/tickets/{ticket.id}/return-to-l1", json=payload, headers=people["headers"]["l2_redes"]
    )
    assert response.status_code == 422
    assert response.json()["type"] == "urn:tracehelp:problems:validation-error"


@pytest.mark.parametrize("role_key", ["collaborator", "analyst", "leader"])
def test_return_to_l1_forbidden_without_permission(api_client, people, make_ticket, role_key):
    ticket = make_ticket(status=S.ESCALATED_L2, escalated_group=SpecialistGroup.REDES)
    response = api_client.post(
        f"/api/v1/tickets/{ticket.id}/return-to-l1",
        json={"requested_info": "Solicitar datos adicionales al usuario"},
        headers=people["headers"][role_key],
    )
    assert response.status_code == 403
    assert response.json()["type"] == "urn:tracehelp:problems:forbidden"


def test_return_to_l1_returns_401_and_404_across_workspaces(api_client, people, make_ticket):
    ticket = make_ticket(status=S.ESCALATED_L2, escalated_group=SpecialistGroup.REDES)
    payload = {"requested_info": "Solicitar datos adicionales al usuario"}

    assert api_client.post(f"/api/v1/tickets/{ticket.id}/return-to-l1", json=payload).status_code == 401

    other_ws = api_client.post(
        f"/api/v1/tickets/{ticket.id}/return-to-l1", json=payload, headers=people["headers"]["other_ws_l2"]
    )
    assert other_ws.status_code == 404
    assert other_ws.json()["type"] == "urn:tracehelp:problems:ticket-not-found"
