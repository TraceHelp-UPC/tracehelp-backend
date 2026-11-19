"""Steps BDD para escalamiento a soporte L2 y devolución a L1 (T81, US17).

Reutiliza steps de ticket_status_steps (workspace y ticket base), ticket_messages_steps
(detalle, mensajes, auditoría vacía y analista de otro workspace), analyst_queue_steps (bandeja),
user_administration_steps (OpenAPI y problem details) y common_steps.
"""
import json
import uuid
from datetime import UTC, datetime

from behave import given, then, when
from sqlalchemy import select, text

from app.analytics.infrastructure.persistence.models import AuditLogModel
from app.helpdesk.domain import state_machine
from app.helpdesk.domain.enums import SupportTier, TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.domain.events import MessagePosted, TicketEscalated, TicketReturnedToL1
from app.helpdesk.infrastructure.persistence.models import TicketModel
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.shared.domain.specialist_group import SpecialistGroup
from app.shared.infrastructure.event_bus import event_bus

FAKE_HASH = "$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm"


def _headers_for(context, user_model: UserModel) -> dict[str, str]:
    user = SqlAlchemyUserRepository(context.session).find_by_id(user_model.id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _headers(context, role_or_alias: str) -> dict[str, str]:
    return _headers_for(context, context.users[role_or_alias])


def _post_escalate(context, headers: dict[str, str], group: str, reason: str, ticket_id=None) -> None:
    target_id = ticket_id or context.ticket_id
    context.response = context.client.post(
        f"/api/v1/tickets/{target_id}/escalate",
        json={"specialist_group": group, "reason": reason},
        headers=headers,
    )


def _post_return_to_l1(context, headers: dict[str, str], requested_info: str, ticket_id=None) -> None:
    target_id = ticket_id or context.ticket_id
    context.response = context.client.post(
        f"/api/v1/tickets/{target_id}/return-to-l1",
        json={"requested_info": requested_info},
        headers=headers,
    )


# --------------------------------------------------------------------------------------------------- preparación
@given('specialist L2 users for groups "{group_a}" and "{group_b}"')
def step_create_group_specialists(context, group_a: str, group_b: str):
    for group_name in (group_a, group_b):
        group = SpecialistGroup(group_name)
        alias = f"SPECIALIST_{group.value}"
        user = UserModel(
            id=uuid.uuid4(),
            workspace_id=context.workspace.id,
            full_name=f"Especialista {group.value}",
            email=f"l2-{group.value.lower()}-{uuid.uuid4().hex[:6]}@demo.pe",
            password_hash=FAKE_HASH,
            role=RoleName.SPECIALIST_L2,
            department="TI",
            specialist_group=group,
        )
        context.session.add(user)
        context.users[alias] = user
    context.session.flush()


@given("a specialist L2 of another workspace")
def step_foreign_specialist(context):
    workspace = getattr(context, "foreign_analyst", None)
    if workspace is not None:
        ws_id = workspace.workspace_id
    else:
        other = WorkspaceModel(id=uuid.uuid4(), name="Empresa Externa", subdomain=f"ext-{uuid.uuid4().hex[:6]}")
        context.session.add(other)
        context.session.flush()
        ws_id = other.id

    specialist = UserModel(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        full_name="Especialista Externo",
        email=f"ext-l2-{uuid.uuid4().hex[:6]}@otra.pe",
        password_hash=FAKE_HASH,
        role=RoleName.SPECIALIST_L2,
        department="TI",
        specialist_group=SpecialistGroup.REDES,
    )
    context.session.add(specialist)
    context.session.flush()
    context.foreign_specialist = specialist


@given('the ticket is classified with category "{category}", priority "{priority}" and module "{module}"')
def step_classify_ticket(context, category: str, priority: str, module: str):
    model = context.session.get(TicketModel, context.ticket_id)
    model.category = TicketCategory(category)
    model.priority = TicketPriority(priority)
    model.affected_module = module
    context.session.flush()


@given("the ticket has a triage diagnosis with OCR and cited sources")
def step_seed_triage_diagnosis(context):
    context.session.execute(
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
            "workspace_id": context.workspace.id,
            "ticket_id": context.ticket_id,
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
    context.session.flush()


@given('the ticket still holds a prior L2 claim by "{alias}"')
def step_seed_prior_l2_claim(context, alias: str):
    model = context.session.get(TicketModel, context.ticket_id)
    model.assigned_specialist_id = context.users[alias].id
    model.specialist_claimed_at = datetime(2026, 11, 20, 10, 0, tzinfo=UTC)
    context.session.flush()


@given('the ticket is in status "ESCALATED_L2" for group "{group}" claimed by "{alias}"')
def step_escalated_ticket_claimed(context, group: str, alias: str):
    model = context.session.get(TicketModel, context.ticket_id)
    model.status = TicketStatus.ESCALATED_L2
    model.current_tier = state_machine.TIER_BY_STATUS[TicketStatus.ESCALATED_L2]
    model.assigned_analyst_id = context.users["ANALYST_L1"].id
    model.escalated_group = SpecialistGroup(group)
    model.escalated_at = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    model.assigned_specialist_id = context.users[alias].id
    model.specialist_claimed_at = datetime(2026, 11, 20, 14, 15, tzinfo=UTC)
    context.session.flush()


@given('the ticket is in status "ESCALATED_L2" for group "{group}"')
def step_escalated_ticket_for_group(context, group: str):
    model = context.session.get(TicketModel, context.ticket_id)
    model.status = TicketStatus.ESCALATED_L2
    model.current_tier = SupportTier.TIER_L2
    model.assigned_analyst_id = context.users["ANALYST_L1"].id
    model.escalated_group = SpecialistGroup(group)
    model.escalated_at = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    context.session.flush()


@given('the ticket is in status "ESCALATED_L2" with null escalated group')
def step_escalated_ticket_legacy_null_group(context):
    model = context.session.get(TicketModel, context.ticket_id)
    model.status = TicketStatus.ESCALATED_L2
    model.current_tier = SupportTier.TIER_L2
    model.assigned_analyst_id = context.users["ANALYST_L1"].id
    model.escalated_group = None
    model.escalated_at = None
    context.session.flush()


@given('the ticket is in status "ESCALATED_L2" for group "{group}" without assigned analyst')
def step_escalated_ticket_without_analyst(context, group: str):
    model = context.session.get(TicketModel, context.ticket_id)
    model.status = TicketStatus.ESCALATED_L2
    model.current_tier = SupportTier.TIER_L2
    model.assigned_analyst_id = None
    model.escalated_group = SpecialistGroup(group)
    model.escalated_at = datetime(2026, 11, 20, 14, 0, tzinfo=UTC)
    context.session.flush()


@given("a subscriber is listening to TicketEscalated and MessagePosted events")
def step_listen_escalated_events(context):
    context.escalation_events = []
    context.message_events = []
    esc_handler = context.escalation_events.append
    msg_handler = context.message_events.append
    event_bus.subscribe(TicketEscalated, esc_handler)
    event_bus.subscribe(MessagePosted, msg_handler)
    context.add_cleanup(event_bus.unsubscribe, TicketEscalated, esc_handler)
    context.add_cleanup(event_bus.unsubscribe, MessagePosted, msg_handler)


@given("a subscriber is listening to TicketReturnedToL1 and MessagePosted events")
def step_listen_returned_events(context):
    context.return_events = []
    context.message_events = []
    ret_handler = context.return_events.append
    msg_handler = context.message_events.append
    event_bus.subscribe(TicketReturnedToL1, ret_handler)
    event_bus.subscribe(MessagePosted, msg_handler)
    context.add_cleanup(event_bus.unsubscribe, TicketReturnedToL1, ret_handler)
    context.add_cleanup(event_bus.unsubscribe, MessagePosted, msg_handler)


# --------------------------------------------------------------------------------------------------- acciones
@when('the "{role}" escalates the ticket to group "{group}" with reason "{reason}"')
def step_escalate(context, role: str, group: str, reason: str):
    _post_escalate(context, _headers(context, role), group, reason)


@when('the "{role}" escalates the ticket to group "{group}" with a reason of {length:d} characters')
def step_escalate_length(context, role: str, group: str, length: int):
    _post_escalate(context, _headers(context, role), group, "x" * length)


@when("the \"{role}\" sends raw escalation payload '{payload}'")
def step_escalate_raw(context, role: str, payload: str):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ticket_id}/escalate",
        content=payload,
        headers={**_headers(context, role), "Content-Type": "application/json"},
    )


@when('the "{role}" escalates a nonexistent ticket to group "{group}"')
def step_escalate_nonexistent(context, role: str, group: str):
    _post_escalate(context, _headers(context, role), group, "Motivo válido de escalamiento", ticket_id=uuid.uuid4())


@when('the analyst of another workspace escalates the ticket to group "{group}"')
def step_foreign_escalate(context, group: str):
    _post_escalate(context, _headers_for(context, context.foreign_analyst), group, "Intento cross-workspace")


@when('an anonymous user escalates the ticket to group "{group}"')
def step_anon_escalate(context, group: str):
    _post_escalate(context, {}, group, "Intento sin autenticación")


@when('a user with an invalid token escalates the ticket to group "{group}"')
def step_bad_token_escalate(context, group: str):
    _post_escalate(context, {"Authorization": "Bearer token.invalido.123"}, group, "Intento con token inválido")


@when('the "{role}" returns the ticket to L1 with requested info "{info}"')
def step_return_to_l1(context, role: str, info: str):
    _post_return_to_l1(context, _headers(context, role), info)


@when('the "{role}" returns the ticket to L1 with requested info of {length:d} characters')
def step_return_to_l1_length(context, role: str, length: int):
    _post_return_to_l1(context, _headers(context, role), "x" * length)


@when("the \"{role}\" sends raw return-to-l1 payload '{payload}'")
def step_return_to_l1_raw(context, role: str, payload: str):
    context.response = context.client.post(
        f"/api/v1/tickets/{context.ticket_id}/return-to-l1",
        content=payload,
        headers={**_headers(context, role), "Content-Type": "application/json"},
    )


@when("the \"{role}\" returns a nonexistent ticket to L1")
def step_return_nonexistent(context, role: str):
    _post_return_to_l1(context, _headers(context, role), "Solicitar información adicional", ticket_id=uuid.uuid4())


@when("the specialist L2 of another workspace returns the ticket to L1")
def step_foreign_return(context):
    _post_return_to_l1(context, _headers_for(context, context.foreign_specialist), "Intento cross-workspace")


@when("an anonymous user returns the ticket to L1")
def step_anon_return(context):
    _post_return_to_l1(context, {}, "Intento sin autenticación")


@when("a user with an invalid token returns the ticket to L1")
def step_bad_token_return(context):
    _post_return_to_l1(context, {"Authorization": "Bearer token.invalido.123"}, "Intento con token inválido")


# --------------------------------------------------------------------------------------------------- aserciones
@then('the response field "{field}" is not null')
def step_field_not_null(context, field: str):
    body = context.response.json()
    assert body.get(field) is not None, f"{field} fue None: {body}"


@then('the response field "{field}" matches the user "{alias}"')
def step_field_matches_user(context, field: str, alias: str):
    expected = str(context.users[alias].id)
    actual = context.response.json().get(field)
    assert actual == expected, f"{field}: esperado {expected}, obtenido {actual}"


@then("TicketEscalated was published once with has_triage_snapshot {expected}")
def step_escalated_event_published(context, expected: str):
    assert len(context.escalation_events) == 1, context.escalation_events
    event = context.escalation_events[0]
    assert str(event.has_triage_snapshot).lower() == expected.lower(), event


@then("TicketReturnedToL1 was published once")
def step_returned_event_published(context):
    assert len(context.return_events) == 1, context.return_events


@then("MessagePosted was not emitted during escalation")
def step_no_message_posted(context):
    assert context.message_events == [], context.message_events


@then("the first comment is an internal note containing:")
def step_first_comment_contains(context):
    comments = context.response.json()["comments"]
    assert comments, "No se encontraron comentarios en el detalle del ticket"
    note = comments[0]
    assert note["is_internal_note"] is True, note
    assert note["is_ai_generated"] is False, note
    content = note["content"]
    for row in context.table:
        fragment = row["fragment"].replace("\\|", "|")
        assert fragment in content, f"Falta {fragment!r} en:\n{content}"


@then("the queue includes the ticket")
def step_queue_includes_ticket(context):
    items = context.response.json()["items"]
    ids = [item["id"] for item in items]
    assert str(context.ticket_id) in ids, f"Ticket {context.ticket_id} no encontrado en {ids}"


@then('the workspace audit log holds a "TicketEscalated" entry acted by "{alias}" for group "{group}" with snapshot {flag}')
def step_audit_escalated(context, alias: str, group: str, flag: str):
    entry = context.session.scalars(
        select(AuditLogModel).where(
            AuditLogModel.ticket_id == context.ticket_id,
            AuditLogModel.event_type == "TicketEscalated",
        )
    ).one()
    assert entry.actor_id == context.users[alias].id, entry.actor_id
    assert entry.entity_type == "ticket", entry.entity_type
    assert entry.detail["specialist_group"] == group, entry.detail
    assert str(entry.detail["has_triage_snapshot"]).lower() == flag.lower(), entry.detail


@then('the workspace audit log holds a "TicketReturnedToL1" entry acted by "{alias}" for group "{group}"')
def step_audit_returned(context, alias: str, group: str):
    entry = context.session.scalars(
        select(AuditLogModel).where(
            AuditLogModel.ticket_id == context.ticket_id,
            AuditLogModel.event_type == "TicketReturnedToL1",
        )
    ).one()
    assert entry.actor_id == context.users[alias].id, entry.actor_id
    assert entry.entity_type == "ticket", entry.entity_type
    assert entry.detail["escalated_group"] == group, entry.detail
    assert entry.detail["assigned_analyst_id"] == str(context.users["ANALYST_L1"].id), entry.detail


@then('the workspace audit log entries do not contain "{secret}"')
def step_audit_masks_pii(context, secret: str):
    rows = context.session.scalars(
        select(AuditLogModel).where(AuditLogModel.workspace_id == context.workspace.id)
    ).all()
    assert rows, "Se esperaban filas en la bitácora de auditoría"
    dump = json.dumps([{"event_type": r.event_type, "detail": r.detail} for r in rows], default=str)
    assert secret not in dump, f"Se filtró {secret!r} en la auditoría: {dump}"
