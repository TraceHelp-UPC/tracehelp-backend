"""Steps BDD del módulo de notificaciones y preferencias (T93, US19).

Reutiliza los steps compartidos de ticket_status_steps, ticket_messages_steps,
user_administration_steps y common_steps.
"""
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from behave import given, step, then, when
from sqlalchemy import select

from app.analytics.infrastructure.persistence.models import AuditLogModel
from app.helpdesk.application.ports import EmailMessage, IEmailSender
from app.helpdesk.domain.enums import TicketStatus
from app.helpdesk.domain.events import EscalatedTicketResolved, MessagePosted, TicketStatusChanged
from app.helpdesk.domain.notification import NotificationType
from app.helpdesk.infrastructure.email import LogEmailSender, mask_email, reset_email_sender, set_email_sender
from app.helpdesk.infrastructure.persistence.models import NotificationModel, TicketModel
from app.iam.domain.enums import UserStatus
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.shared.infrastructure.event_bus import event_bus

NOTIFICATIONS_URL = "/api/v1/notifications"
PREFERENCES_URL = "/api/v1/users/me/notification-preferences"


class _FakeEmailSender(IEmailSender):
    """Doble en memoria para capturar correos salientes sin red ni SMTP."""

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


def _headers_for_user(context, user_model) -> dict[str, str]:
    user = SqlAlchemyUserRepository(context.session).find_by_id(user_model.id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _headers(context, role: str) -> dict[str, str]:
    return _headers_for_user(context, context.users[role])


def _ticket_code(context) -> str:
    ticket = context.session.get(TicketModel, context.ticket_id)
    return f"TK-{ticket.ticket_number:04d}"


def _ensure_seeded_map(context) -> dict[str, uuid.UUID]:
    if not hasattr(context, "seeded_notifications"):
        context.seeded_notifications = {}
    return context.seeded_notifications


# --------------------------------------------------------------------------------------------------- preparación
@given("a fake email sender is capturing outgoing emails")
def step_install_fake_email_sender(context):
    sender = _FakeEmailSender()
    set_email_sender(sender)
    context.fake_email_sender = sender
    context.add_cleanup(reset_email_sender)


@given("the default log email sender is active")
def step_use_log_email_sender(context):
    set_email_sender(LogEmailSender())
    context.add_cleanup(reset_email_sender)


@given('the "{role}" account is marked inactive')
def step_mark_user_inactive(context, role):
    context.users[role].status = UserStatus.INACTIVE
    context.session.flush()


@given("the ticket has no assigned analyst")
def step_unassign_ticket(context):
    ticket = context.session.get(TicketModel, context.ticket_id)
    ticket.assigned_analyst_id = None
    context.session.flush()


@given('a valid token is cached for the "{role}"')
def step_cache_token(context, role):
    context.cached_headers = _headers(context, role)


@given('the "{role}" has 3 seeded notifications where the newest is already read')
def step_seed_three_notifications(context, role):
    seeded = _ensure_seeded_map(context)
    user = context.users[role]
    code = _ticket_code(context)
    base = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    specs = [
        ("Notif 1", NotificationType.TICKET_STATUS_CHANGED.value, None, base),
        ("Notif 2", NotificationType.MESSAGE_POSTED.value, None, base + timedelta(minutes=1)),
        ("Notif 3", NotificationType.TICKET_STATUS_CHANGED.value, base + timedelta(minutes=5), base + timedelta(minutes=2)),
    ]
    for title, ntype, read_at, created_at in specs:
        row = NotificationModel(
            id=uuid.uuid4(),
            workspace_id=user.workspace_id,
            recipient_id=user.id,
            ticket_id=context.ticket_id,
            type=ntype,
            title=title,
            body=f"Cuerpo de {title}",
            data={"ticket_code": code},
            read_at=read_at,
            created_at=created_at,
        )
        context.session.add(row)
        seeded[title] = row.id
    context.session.flush()


def _seed_single_notification(context, user, name: str) -> None:
    seeded = _ensure_seeded_map(context)
    row = NotificationModel(
        id=uuid.uuid4(),
        workspace_id=user.workspace_id,
        recipient_id=user.id,
        ticket_id=context.ticket_id,
        type=NotificationType.MESSAGE_POSTED.value,
        title=name,
        body=f"Cuerpo de {name}",
        data={"ticket_code": _ticket_code(context)},
        created_at=datetime.now(UTC),
    )
    context.session.add(row)
    context.session.flush()
    seeded[name] = row.id


@given('the "{role}" has 1 seeded notification named "{name}"')
def step_seed_one_for_role(context, role, name):
    _seed_single_notification(context, context.users[role], name)


@given('the other collaborator has 1 seeded notification named "{name}"')
def step_seed_one_for_other_collab(context, name):
    _seed_single_notification(context, context.other_collaborator, name)


@given('the foreign analyst has 1 seeded notification named "{name}"')
def step_seed_one_for_foreign_analyst(context, name):
    _seed_single_notification(context, context.foreign_analyst, name)


# --------------------------------------------------------------------------------------------------- acciones
@when('the specialist resolves the escalated ticket in group "{group}"')
def step_resolve_escalated_via_bus(context, group):
    # Simula T82: en ESCALATED_L2 -> RESOLVED el agregado emite TicketStatusChanged y EscalatedTicketResolved
    event_bus.publish(
        TicketStatusChanged(
            ticket_id=context.ticket_id,
            workspace_id=context.workspace.id,
            reporter_id=context.users["COLLABORATOR"].id,
            previous_status=TicketStatus.ESCALATED_L2,
            new_status=TicketStatus.RESOLVED,
            changed_by=context.users["SPECIALIST_L2"].id,
        )
    )
    event_bus.publish(
        EscalatedTicketResolved(
            ticket_id=context.ticket_id,
            workspace_id=context.workspace.id,
            reporter_id=context.users["COLLABORATOR"].id,
            resolved_by=context.users["SPECIALIST_L2"].id,
            escalated_group=group,
        )
    )


@when("a collaborator MessagePosted event arrives with assigned_specialist_id set to the specialist")
def step_publish_message_with_specialist(context):
    @dataclass(frozen=True, kw_only=True)
    class _MessagePostedWithSpecialist(MessagePosted):
        assigned_specialist_id: uuid.UUID | None = None

    event_bus.publish(
        _MessagePostedWithSpecialist(
            ticket_id=context.ticket_id,
            workspace_id=context.workspace.id,
            message_id=uuid.uuid4(),
            ticket_code=_ticket_code(context),
            author_id=context.users["COLLABORATOR"].id,
            reporter_id=context.users["COLLABORATOR"].id,
            assigned_analyst_id=context.users["ANALYST_L1"].id,
            assigned_specialist_id=context.users["SPECIALIST_L2"].id,
            author_is_reporter=True,
            is_internal_note=False,
            ticket_status=TicketStatus.ESCALATED_L2,
            content_length=24,
        )
    )


@step('the "{role}" requests their notifications')
def step_get_notifications(context, role):
    context.response = context.client.get(NOTIFICATIONS_URL, headers=_headers(context, role))


@step('the "{role}" requests their notifications with query "{query}"')
def step_get_notifications_query(context, role, query):
    context.response = context.client.get(f"{NOTIFICATIONS_URL}?{query}", headers=_headers(context, role))


@when('the "{role}" marks seeded notification "{name}" as read')
def step_mark_seeded_read(context, role, name):
    notif_id = context.seeded_notifications[name]
    context.response = context.client.patch(f"{NOTIFICATIONS_URL}/{notif_id}/read", headers=_headers(context, role))


@when('the "{role}" marks a nonexistent notification as read')
def step_mark_missing_read(context, role):
    context.response = context.client.patch(f"{NOTIFICATIONS_URL}/{uuid.uuid4()}/read", headers=_headers(context, role))


@when('the "{role}" marks notification id "{raw_id}" as read')
def step_mark_raw_id_read(context, role, raw_id):
    context.response = context.client.patch(f"{NOTIFICATIONS_URL}/{raw_id}/read", headers=_headers(context, role))


@when('the "{role}" requests their notification preferences')
def step_get_preferences(context, role):
    context.response = context.client.get(PREFERENCES_URL, headers=_headers(context, role))


@when("the \"{role}\" updates their notification preferences with '{payload}'")
def step_patch_preferences(context, role, payload):
    context.response = context.client.patch(
        PREFERENCES_URL,
        content=payload,
        headers={**_headers(context, role), "Content-Type": "application/json"},
    )


@when('an unauthenticated client calls "{method}" "{path}"')
def step_unauth_call(context, method, path):
    context.response = context.client.request(method, path)


@when("an unauthenticated client calls \"{method}\" \"{path}\" with '{payload}'")
def step_unauth_call_body(context, method, path, payload):
    context.response = context.client.request(
        method, path, content=payload, headers={"Content-Type": "application/json"}
    )


@when('an unauthenticated client marks seeded notification "{name}" as read')
def step_unauth_mark_read(context, name):
    notif_id = context.seeded_notifications[name]
    context.response = context.client.patch(f"{NOTIFICATIONS_URL}/{notif_id}/read")


@when('a client with an invalid token calls "{method}" "{path}"')
def step_invalid_token_call(context, method, path):
    context.response = context.client.request(method, path, headers={"Authorization": "Bearer token-invalido"})


@when("the cached token requests GET notification preferences")
def step_cached_get_prefs(context):
    context.response = context.client.get(PREFERENCES_URL, headers=context.cached_headers)


@when("the cached token requests PATCH notification preferences with '{payload}'")
def step_cached_patch_prefs(context, payload):
    context.response = context.client.patch(
        PREFERENCES_URL,
        content=payload,
        headers={**context.cached_headers, "Content-Type": "application/json"},
    )


# --------------------------------------------------------------------------------------------------- aserciones
@then("the notification listing reports total {total:d}, total_pages {pages:d} and unread_count {unread:d}")
def step_assert_listing_totals(context, total, pages, unread):
    body = context.response.json()
    assert body["total"] == total, body
    assert body["total_pages"] == pages, body
    assert body["unread_count"] == unread, body


@then('the first notification has type "{expected_type}", read "{expected_read}" and the ticket code')
def step_assert_first_notification(context, expected_type, expected_read):
    items = context.response.json()["items"]
    assert items, context.response.text
    first = items[0]
    code = _ticket_code(context)
    assert first["type"] == expected_type, first
    assert str(first["read"]).lower() == expected_read, first
    assert first["ticket_id"] == str(context.ticket_id), first
    assert first["ticket_code"] == code, first
    assert first["data"].get("ticket_code") == code, first
    if expected_read == "false":
        assert first["read_at"] is None, first


@then('the first notification data has previous_status "{prev_status}" and new_status "{new_status}"')
def step_assert_first_status_data(context, prev_status, new_status):
    data = context.response.json()["items"][0]["data"]
    assert data["previous_status"] == prev_status, data
    assert data["new_status"] == new_status, data


@then('the first notification data has escalated_group "{group}"')
def step_assert_first_escalated_group(context, group):
    data = context.response.json()["items"][0]["data"]
    assert data["escalated_group"] == group, data


@then('the first notification title contains "{snippet}"')
def step_assert_first_title_contains(context, snippet):
    title = context.response.json()["items"][0]["title"]
    assert snippet in title, title


@then('the first notification title starts with "{prefix}"')
def step_assert_first_title_starts(context, prefix):
    title = context.response.json()["items"][0]["title"]
    assert title.startswith(prefix), title


@then('the first notification does not contain "{secret}"')
def step_assert_first_omits(context, secret):
    first = context.response.json()["items"][0]
    serialized = json.dumps(first, ensure_ascii=False)
    assert secret not in serialized, serialized


@then('the listed notification titles in order are "{titles}"')
def step_assert_listed_titles(context, titles):
    expected = [t.strip() for t in titles.split(",")]
    actual = [item["title"] for item in context.response.json()["items"]]
    assert actual == expected, f"{actual} != {expected}"


@then("the read_at timestamp is remembered")
def step_remember_read_at(context):
    read_at = context.response.json()["read_at"]
    assert read_at is not None, context.response.text
    context.remembered_read_at = read_at


@then("the read_at timestamp matches the remembered value")
def step_match_read_at(context):
    assert context.response.json()["read_at"] == context.remembered_read_at, context.response.text


@then('{count:d} fake email was sent to the "{role}"')
def step_assert_fake_email_count_to_role(context, count, role):
    sent = context.fake_email_sender.sent
    assert len(sent) == count, sent
    assert sent[-1].to == context.users[role].email, sent[-1]


@then("0 fake emails were sent")
def step_assert_zero_fake_emails(context):
    assert context.fake_email_sender.sent == [], context.fake_email_sender.sent


@then('the last fake email subject starts with "{prefix}" and contains "{snippet}"')
def step_assert_last_email_subject(context, prefix, snippet):
    subject = context.fake_email_sender.sent[-1].subject
    assert subject.startswith(prefix), subject
    assert snippet in subject, subject


@then('the last fake email body includes the no-reply footer and omits "{secret}"')
def step_assert_last_email_body(context, secret):
    body = context.fake_email_sender.sent[-1].text_body
    assert "No respondas a este correo." in body, body
    assert secret not in body, body


@then('the database has {count:d} notifications for the "{role}"')
def step_assert_db_notif_count(context, count, role):
    context.session.expire_all()
    rows = context.session.scalars(
        select(NotificationModel).where(NotificationModel.recipient_id == context.users[role].id)
    ).all()
    assert len(rows) == count, rows


@then("the audit log has {count:d} \"UserProfileUpdated\" entry for the \"{role}\" with changes '{expected_json}'")
def step_assert_profile_audit(context, count, role, expected_json):
    rows = context.session.scalars(
        select(AuditLogModel).where(
            AuditLogModel.event_type == "UserProfileUpdated",
            AuditLogModel.entity_id == context.users[role].id,
        )
    ).all()
    assert len(rows) == count, [r.detail for r in rows]
    assert rows[-1].detail == {"changes": json.loads(expected_json)}, rows[-1].detail


@then('the audit log still has {count:d} "UserProfileUpdated" entry for the "{role}"')
def step_assert_profile_audit_count(context, count, role):
    rows = context.session.scalars(
        select(AuditLogModel).where(
            AuditLogModel.event_type == "UserProfileUpdated",
            AuditLogModel.entity_id == context.users[role].id,
        )
    ).all()
    assert len(rows) == count, [r.detail for r in rows]


@then('the captured logs mask the "{role}" email address')
def step_assert_logs_mask_email(context, role):
    raw_email = context.users[role].email
    masked = mask_email(raw_email)
    messages = context.log_handler.messages
    assert any(masked in m for m in messages), f"No se encontró {masked!r} en logs"
    assert not any(raw_email in m for m in messages), f"Correo sin enmascarar {raw_email!r} filtrado en logs"


@then("the audit log contains no notification event entries")
def step_assert_no_notification_audit(context):
    rows = context.session.scalars(
        select(AuditLogModel).where(AuditLogModel.workspace_id == context.workspace.id)
    ).all()
    notif_rows = [r for r in rows if "notification" in r.entity_type.lower() or "notification" in r.event_type.lower()]
    assert notif_rows == [], [(r.event_type, r.entity_type) for r in notif_rows]


@then("the OpenAPI document declares preferences endpoints with summary, description, examples and unique tags")
def step_assert_openapi_preferences(context):
    schema = context.response.json()
    paths = schema["paths"]

    # Verificar que no existan tags duplicados en los endpoints de notificaciones
    for path, method in (
        (NOTIFICATIONS_URL, "get"),
        (f"{NOTIFICATIONS_URL}/{{notification_id}}/read", "patch"),
        (PREFERENCES_URL, "get"),
        (PREFERENCES_URL, "patch"),
    ):
        op = paths[path][method]
        tags = op.get("tags", [])
        assert len(tags) == len(set(tags)), f"Tags duplicados en {method.upper()} {path}: {tags}"

    get_pref = paths[PREFERENCES_URL]["get"]
    assert get_pref.get("summary") and get_pref.get("description")
    assert "200" in get_pref["responses"] and "401" in get_pref["responses"]
    assert "example" in get_pref["responses"]["200"]["content"]["application/json"]

    patch_pref = paths[PREFERENCES_URL]["patch"]
    assert patch_pref.get("summary") and patch_pref.get("description")
    assert all(code in patch_pref["responses"] for code in ("200", "401", "422"))
    assert "example" in patch_pref["responses"]["200"]["content"]["application/json"]
