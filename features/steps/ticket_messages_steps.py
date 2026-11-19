"""Steps de la conversación dentro del ticket (T87, US26).

Reutilizan "a workspace with users for every role", "a ticket reported by the collaborator" y
'the ticket is in status' (ticket_status_steps), los steps de respuesta de common_steps y de
user_administration_steps, y la captura de logs de user_administration_steps.
"""
import json
import uuid
from datetime import UTC, datetime, timedelta

from behave import given, step, then, when
from sqlalchemy import select

from app.analytics.infrastructure.persistence.models import AuditLogModel
from app.helpdesk.domain.events import MessagePosted
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.shared.infrastructure.event_bus import event_bus

FAKE_HASH = "$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm"
AUDIT_DETAIL_KEYS = {"is_internal_note", "author_is_reporter", "ticket_status", "content_length"}


def _headers_for(context, user_model) -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(user_model.id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _headers(context, role: str) -> dict:
    return _headers_for(context, context.users[role])


def _messages_url(ticket_id) -> str:
    return f"/api/v1/tickets/{ticket_id}/messages"


def _post(context, headers: dict, text: str, internal: bool = False, ticket_id=None) -> None:
    context.last_text = text
    context.response = context.client.post(
        _messages_url(ticket_id or context.ticket_id),
        json={"content": text, "is_internal_note": internal},
        headers=headers,
    )


def _thread(context) -> list[dict]:
    return context.response.json()["items"]


# --------------------------------------------------------------------------------------------------- preparación
@given("the ticket already has {count:d} messages from the collaborator")
def step_seed_messages(context, count):
    repo = SqlAlchemyTicketRepository(context.session)
    ticket = repo.find_by_id(context.ticket_id)
    start = datetime.now(UTC) - timedelta(hours=1)
    for number in range(1, count + 1):
        comment = ticket.post_message(
            author_id=context.users["COLLABORATOR"].id,
            content=f"Mensaje {number:03d}",
            author_is_reporter=True,
        )
        # Marcas de tiempo distintas: el reloj de Windows tiene una resolución de ~15 ms y empataría el orden
        comment.created_at = start + timedelta(seconds=number)
    ticket.pull_events()
    repo.save(ticket)
    context.session.flush()


@given("the ticket has a validated AI reply of {count:d} characters")
def step_seed_ai_reply(context, count):
    # La respuesta HITL se guarda con add_comment, que no tiene el límite de 2000 caracteres
    repo = SqlAlchemyTicketRepository(context.session)
    ticket = repo.find_by_id(context.ticket_id)
    context.ai_reply = ("Paso de solución. " * (count // 17 + 1))[:count]
    ticket.add_comment(
        author_id=context.users["ANALYST_L1"].id, content=context.ai_reply, is_internal_note=False, is_ai_generated=True
    )
    repo.save(ticket)
    context.session.flush()


@given("an analyst of another workspace")
def step_analyst_other_workspace(context):
    other = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    context.session.add(other)
    context.session.flush()
    user = UserModel(
        id=uuid.uuid4(), workspace_id=other.id, full_name="Analista Externo",
        email=f"externo-{uuid.uuid4().hex[:6]}@otra.pe", password_hash=FAKE_HASH,
        role=RoleName.ANALYST_L1, department="TI",
    )
    context.session.add(user)
    context.session.flush()
    context.foreign_analyst = user


@given("a subscriber is listening to MessagePosted events")
def step_listen_events(context):
    context.posted_events = []
    handler = context.posted_events.append
    event_bus.subscribe(MessagePosted, handler)
    context.add_cleanup(event_bus.unsubscribe, MessagePosted, handler)


@given("the audit log of the workspace is empty")
def step_empty_audit(context):
    from sqlalchemy import delete

    context.session.execute(delete(AuditLogModel).where(AuditLogModel.workspace_id == context.workspace.id))
    context.session.flush()


# --------------------------------------------------------------------------------------------------- escribir
@step('the "{role}" posts the message "{text}"')
def step_post(context, role, text):
    _post(context, _headers(context, role), text)


@step('the "{role}" posts the internal note "{text}"')
def step_post_internal(context, role, text):
    _post(context, _headers(context, role), text, internal=True)


@when("the \"{role}\" posts a message with this text:")
def step_post_docstring(context, role):
    _post(context, _headers(context, role), context.text)


@when('the "{role}" posts a message of {count:d} characters')
def step_post_length(context, role, count):
    _post(context, _headers(context, role), "a" * count)


@when('the "{role}" posts a message of {count:d} emoji characters')
def step_post_emoji(context, role, count):
    # Se genera en el step para no depender de la codificación de la consola al imprimir la feature
    _post(context, _headers(context, role), "😀" * count)


@when('the "{role}" posts a message with accents and emoji')
def step_post_accents_emoji(context, role):
    _post(context, _headers(context, role), "Ñandú, café y señal ¿ok? 😀👍")


@when('the "{role}" posts a message of {count:d} spaces')
def step_post_spaces(context, role, count):
    _post(context, _headers(context, role), " " * count)


@when('the "{role}" posts a message of {count:d} characters padded with spaces')
def step_post_padded(context, role, count):
    _post(context, _headers(context, role), "  " + "a" * count + "  ")


@when('the "{role}" posts this raw payload:')
def step_post_raw(context, role):
    context.response = context.client.post(
        _messages_url(context.ticket_id),
        content=context.text,
        headers={**_headers(context, role), "Content-Type": "application/json"},
    )


@when('the other collaborator posts the message "{text}"')
def step_other_posts(context, text):
    _post(context, _headers_for(context, context.other_collaborator), text)


@when('the other collaborator posts the internal note "{text}"')
def step_other_posts_internal(context, text):
    _post(context, _headers_for(context, context.other_collaborator), text, internal=True)


@when('the analyst of another workspace posts the message "{text}"')
def step_foreign_posts(context, text):
    _post(context, _headers_for(context, context.foreign_analyst), text)


@when('an anonymous user posts the message "{text}"')
def step_anonymous_posts(context, text):
    _post(context, {}, text)


@when('a user with an invalid token posts the message "{text}"')
def step_bad_token_posts(context, text):
    _post(context, {"Authorization": "Bearer token.invalido.123"}, text)


@when('the "{role}" posts the message "{text}" on a nonexistent ticket')
def step_post_unknown(context, role, text):
    _post(context, _headers(context, role), text, ticket_id=uuid.uuid4())


# --------------------------------------------------------------------------------------------------- leer
@step('the "{role}" requests the messages of the ticket')
def step_get_thread(context, role):
    context.response = context.client.get(_messages_url(context.ticket_id), headers=_headers(context, role))


@when('the "{role}" requests the messages of the ticket page {page:d} with {size:d} messages per page')
def step_get_thread_page(context, role, page, size):
    context.response = context.client.get(
        f"{_messages_url(context.ticket_id)}?page={page}&size={size}", headers=_headers(context, role)
    )


@when("the other collaborator requests the messages of the ticket")
def step_other_gets(context):
    context.response = context.client.get(
        _messages_url(context.ticket_id), headers=_headers_for(context, context.other_collaborator)
    )


@when("the analyst of another workspace requests the messages of the ticket")
def step_foreign_gets(context):
    context.response = context.client.get(
        _messages_url(context.ticket_id), headers=_headers_for(context, context.foreign_analyst)
    )


@when("an anonymous user requests the messages of the ticket")
def step_anonymous_gets(context):
    context.response = context.client.get(_messages_url(context.ticket_id))


@when("a user with an invalid token requests the messages of the ticket")
def step_bad_token_gets(context):
    context.response = context.client.get(
        _messages_url(context.ticket_id), headers={"Authorization": "Bearer token.invalido.123"}
    )


@when('the "{role}" requests the messages of a nonexistent ticket')
def step_get_unknown(context, role):
    context.response = context.client.get(_messages_url(uuid.uuid4()), headers=_headers(context, role))


@when('the "{role}" opens the full detail of the ticket')
def step_open_detail(context, role):
    context.response = context.client.get(f"/api/v1/tickets/{context.ticket_id}", headers=_headers(context, role))


@when("the collaborator lists their ticket history")
def step_collab_history(context):
    context.response = context.client.get("/api/v1/tickets/my-history", headers=_headers(context, "COLLABORATOR"))


@when('the "{role}" requests the audit log of the ticket for "{event_type}"')
def step_get_audit(context, role, event_type):
    context.audit_response = context.client.get(
        f"/api/v1/audit-log?event_type={event_type}&ticket_id={context.ticket_id}", headers=_headers(context, role)
    )


# --------------------------------------------------------------------------------------------------- hilo
@then("the thread shows these messages in order:")
def step_thread_order(context):
    expected = [
        (row["content"], row["from_reporter"], row["is_internal_note"]) for row in context.table
    ]
    actual = [
        (m["content"], str(m["from_reporter"]).lower(), str(m["is_internal_note"]).lower()) for m in _thread(context)
    ]
    assert actual == expected, f"{actual} != {expected}"


@then("the thread reports {total:d} messages in {pages:d} pages")
def step_thread_totals(context, total, pages):
    body = context.response.json()
    assert (body["total"], body["total_pages"]) == (total, pages), body


@then("the thread page holds {count:d} messages")
def step_thread_count(context, count):
    assert len(_thread(context)) == count, context.response.text


@then('the thread page starts with "{content}" and ends with "{last}"')
def step_thread_edges(context, content, last):
    items = _thread(context)
    assert items[0]["content"] == content and items[-1]["content"] == last, [m["content"] for m in items]


@then('the thread does not contain "{text}"')
def step_thread_without(context, text):
    assert text not in context.response.text, f"El texto {text!r} aparece en la respuesta"
    assert all(not m["is_internal_note"] for m in _thread(context)), "Se filtró una nota interna"


@then('the response body does not contain "{text}"')
def step_body_without(context, text):
    assert text not in context.response.text, f"El texto {text!r} aparece en la respuesta"


@then('the response content is exactly "{expected}"')
def step_content_exact(context, expected):
    assert context.response.json()["content"] == expected, context.response.text


@then("the response content has {count:d} characters")
def step_content_length(context, count):
    assert len(context.response.json()["content"]) == count, context.response.text


@then("the response content equals the text that was sent")
def step_content_equals_sent(context):
    assert context.response.json()["content"] == context.last_text.strip(), context.response.json()["content"]


@then("the response lists these messages in order:")
def step_listing_matches(context):
    step_thread_order(context)


@then("the detail shows {count:d} comments")
def step_detail_comments(context, count):
    assert len(context.response.json()["comments"]) == count, context.response.text


@then('the thread contains the AI reply marked as "{flag}" with {count:d} characters')
def step_thread_ai_reply(context, flag, count):
    ai = [m for m in _thread(context) if m["is_ai_generated"]]
    assert ai and str(ai[0]["is_ai_generated"]).lower() == flag, context.response.text
    assert len(ai[0]["content"]) == count and ai[0]["content"] == context.ai_reply


# --------------------------------------------------------------------------------------------------- evento y auditoría
@then("MessagePosted was published once with author_is_reporter {reporter} and is_internal_note {internal}")
def step_event_published(context, reporter, internal):
    assert len(context.posted_events) == 1, context.posted_events
    event = context.posted_events[0]
    assert str(event.author_is_reporter).lower() == reporter, event
    assert str(event.is_internal_note).lower() == internal, event


@then("MessagePosted was not published")
def step_event_not_published(context):
    assert context.posted_events == [], context.posted_events


@then("the published event carries no message text")
def step_event_no_text(context):
    event = context.posted_events[0]
    fields = vars(event)
    assert "content" not in fields and "text" not in fields and "message" not in fields, sorted(fields)
    assert context.last_text not in json.dumps(fields, default=str), "El texto viaja en el evento"
    assert event.content_length == len(context.last_text.strip()), event


@then('the audit log holds a "MessagePosted" entry acted by the "{role}" without the message text')
def step_audit_entry(context, role):
    response = context.audit_response
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1, items
    entry = items[0]
    assert entry["actor_id"] == str(context.users[role].id), entry
    assert entry["entity_type"] == "ticket_message", entry
    assert entry["ticket_id"] == str(context.ticket_id), entry
    assert set(entry["detail"]) == AUDIT_DETAIL_KEYS, entry["detail"]
    assert context.last_text.strip() not in response.text, "El texto del mensaje aparece en la auditoría"
    context.audit_item = entry


@then('the audit entry says author_is_reporter {reporter} and is_internal_note {internal} in status "{status}"')
def step_audit_flags(context, reporter, internal, status):
    detail = context.audit_item["detail"]
    assert str(detail["author_is_reporter"]).lower() == reporter, detail
    assert str(detail["is_internal_note"]).lower() == internal, detail
    assert detail["ticket_status"] == status, detail
    assert detail["content_length"] == len(context.last_text.strip()), detail


@then("the audit log holds no MessagePosted entry")
def step_audit_none(context):
    rows = context.session.execute(
        select(AuditLogModel).where(
            AuditLogModel.workspace_id == context.workspace.id, AuditLogModel.event_type == "MessagePosted"
        )
    ).scalars().all()
    assert rows == [], [r.detail for r in rows]


@then("the raw audit rows do not contain the message text")
def step_raw_audit_clean(context):
    rows = context.session.execute(
        select(AuditLogModel).where(AuditLogModel.workspace_id == context.workspace.id)
    ).scalars().all()
    dump = json.dumps([{"detail": r.detail, "type": r.event_type} for r in rows], default=str)
    assert context.last_text.strip() not in dump, dump


@then('the captured logs do not contain "{text}"')
def step_logs_clean(context, text):
    assert context.log_handler.messages, "La captura de logs no recibió nada: la comprobación sería vacía"
    leaked = [m for m in context.log_handler.messages if text in m]
    assert not leaked, f"El texto aparece en {len(leaked)} mensajes de log"


@then("the stored message count of the ticket is {count:d}")
def step_stored_count(context, count):
    context.session.expire_all()
    ticket = SqlAlchemyTicketRepository(context.session).find_by_id(context.ticket_id)
    assert len(ticket.comments) == count, [c.content for c in ticket.comments]


@then('the response field "ticket_id" is the ticket id')
def step_ticket_id(context):
    assert context.response.json()["ticket_id"] == str(context.ticket_id), context.response.text


@then("the error detail mentions that the ticket is closed")
def step_closed_detail(context):
    detail = context.response.json()["detail"]
    assert detail.startswith("El ticket TK-") and detail.endswith("está cerrado y ya no admite mensajes."), detail
