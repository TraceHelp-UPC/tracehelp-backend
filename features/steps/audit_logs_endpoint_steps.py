"""Steps de la feature del endpoint de bitácora de auditoría (T95, TS06).

Reutilizan "a workspace with users for every role" y "a ticket reported by the collaborator"
(ticket_status_steps), "the response status is {n}" (common_steps), "the error is reported as problem
details" (ticket_query_steps), 'the problem type is "{slug}"' y "the client requests the OpenAPI document"
(user_administration_steps).
"""
import uuid
from datetime import datetime, timedelta

from behave import given, then, when
from sqlalchemy import func, select, text

from app.analytics.domain.audit_entry import compute_integrity_hash
from app.analytics.infrastructure.persistence.models import AuditLogModel
from app.helpdesk.domain.enums import ImpactLevel
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.infrastructure.persistence.models import WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider

CANONICAL = "/api/v1/audit/logs"
LEGACY = "/api/v1/audit-log"
ENTRY_FIELDS = {
    "id", "workspace_id", "event_type", "actor_id", "actor_name", "entity_type", "entity_id",
    "ticket_id", "detail", "integrity_hash", "occurred_at",
}
PAGE_FIELDS = {"items", "page", "size", "total", "total_pages"}


def _headers(context, role: str) -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _resolve(context, query: str) -> str:
    """Sustituye <ticket>, <other_ticket> y <actor:ROL> por los ids reales del escenario."""
    query = query.replace("<ticket>", str(context.ticket_id))
    if "<other_ticket>" in query:
        query = query.replace("<other_ticket>", str(context.other_ticket_id))
    for role, user in context.users.items():
        query = query.replace(f"<actor:{role}>", str(user.id))
    return query


def _url(base: str, query: str) -> str:
    return f"{base}?{query}" if query else base


def _count(context) -> int:
    return context.session.execute(
        select(func.count()).select_from(AuditLogModel).where(AuditLogModel.workspace_id == context.workspace.id)
    ).scalar_one()


def _ensure_labels(context) -> None:
    if not hasattr(context, "audit_labels"):
        context.audit_labels = {}


def _parse(moment: str) -> datetime:
    return datetime.fromisoformat(moment.replace("Z", "+00:00"))


def _add_entry(context, workspace_id, label, event_type, actor_id, ticket_id, occurred_at: datetime) -> None:
    _ensure_labels(context)
    entity_id = uuid.uuid4()
    detail = {"label": label}
    context.session.add(
        AuditLogModel(
            id=uuid.uuid4(), workspace_id=workspace_id, event_type=event_type, actor_id=actor_id,
            entity_type="ticket", entity_id=entity_id, ticket_id=ticket_id, detail=detail,
            integrity_hash=compute_integrity_hash(
                event_type=event_type, workspace_id=workspace_id, actor_id=actor_id, entity_type="ticket",
                entity_id=entity_id, ticket_id=ticket_id, occurred_at=occurred_at, detail=detail,
            ),
            occurred_at=occurred_at,
        )
    )
    context.session.flush()
    context.audit_labels[str(entity_id)] = label


def _labels(context) -> list[str]:
    return [context.audit_labels[i["entity_id"]] for i in context.response.json()["items"]]


# --------------------------------------------------------------------------------------------------- preparación
@given("a second ticket reported by the collaborator")
def step_second_ticket(context):
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title="La impresora no responde",
        description="Cola de impresión bloqueada",
        impact_level=ImpactLevel.LOW,
    )
    SqlAlchemyTicketRepository(context.session).save(ticket)
    context.other_ticket_id = ticket.id


@given("the workspace audit log is empty")
def step_empty_audit(context):
    _ensure_labels(context)
    context.session.execute(text("DELETE FROM analytics_audit_log WHERE workspace_id = :w"), {"w": context.workspace.id})
    context.session.flush()


@given('the workspace audit log holds {count:d} "{event_type}" entries, one per minute, the newest at "{newest}"')
def step_bulk_entries(context, count, event_type, newest):
    start = _parse(newest)
    for i in range(count):
        _add_entry(context, context.workspace.id, f"E{i:02d}", event_type, None, None, start - timedelta(minutes=i))


@given("these audit entries exist in the workspace:")
def step_entries_table(context):
    for row in context.table:
        actor = row["actor"].strip()
        ticket = row["ticket"].strip()
        _add_entry(
            context,
            context.workspace.id,
            row["label"].strip(),
            row["event_type"].strip(),
            context.users[actor].id if actor != "-" else None,
            {"-": None, "ticket": context.ticket_id, "other ticket": getattr(context, "other_ticket_id", None)}[ticket],
            _parse(row["occurred_at"].strip()),
        )


@given('an audit entry "{label}" of type "{event_type}" exists in another workspace')
def step_other_workspace_entry(context, label, event_type):
    other = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    context.session.add(other)
    context.session.flush()
    _add_entry(context, other.id, label, event_type, None, None, _parse("2026-11-10T12:00:00Z"))


@given('the database session time zone is "{zone}"')
def step_session_zone(context, zone):
    context.session.execute(text(f"SET LOCAL TIME ZONE '{zone}'"))


@given("the audit entries are counted")
def step_count_entries(context):
    context.audit_count = _count(context)


@when('a new "{event_type}" entry "{label}" is recorded at "{moment}"')
def step_new_entry(context, event_type, label, moment):
    _add_entry(context, context.workspace.id, label, event_type, None, None, _parse(moment))


# --------------------------------------------------------------------------------------------------- peticiones
@when('the "{role}" requests the audit logs with query "{query}"')
def step_request_logs(context, role, query):
    context.response = context.client.get(_url(CANONICAL, _resolve(context, query)), headers=_headers(context, role))


@when('the "{role}" requests the audit logs without query')
def step_request_logs_plain(context, role):
    context.response = context.client.get(CANONICAL, headers=_headers(context, role))


@when('the "{role}" requests the legacy audit log with query "{query}"')
def step_request_legacy(context, role, query):
    context.response = context.client.get(_url(LEGACY, _resolve(context, query)), headers=_headers(context, role))


@when('the "{role}" requests the legacy audit log without query')
def step_request_legacy_plain(context, role):
    context.response = context.client.get(LEGACY, headers=_headers(context, role))


@when('the "{role}" requests both audit endpoints with query "{query}"')
def step_request_both(context, role, query):
    query = _resolve(context, query)
    context.canonical_response = context.client.get(_url(CANONICAL, query), headers=_headers(context, role))
    context.legacy_response = context.client.get(_url(LEGACY, query), headers=_headers(context, role))
    context.response = context.legacy_response


@when("an unauthenticated client requests the audit logs without query")
def step_unauthenticated_plain(context):
    context.response = context.client.get(CANONICAL)


@when('an unauthenticated client requests the audit logs with query "{query}"')
def step_unauthenticated(context, query):
    context.response = context.client.get(_url(CANONICAL, query))


@when('a client requests the audit logs with the token "{token}"')
def step_bad_token(context, token):
    context.response = context.client.get(CANONICAL, headers={"Authorization": f"Bearer {token}"})


@when('the "{role}" sends "{method}" to the audit logs')
def step_mutating_method(context, role, method):
    context.response = context.client.request(method, CANONICAL, headers=_headers(context, role), json={})


@when('the "{role}" sends "{method}" to the audit entry "{label}"')
def step_mutating_entry(context, role, method, label):
    entity_id = next(k for k, v in context.audit_labels.items() if v == label)
    entry_id = context.session.execute(
        select(AuditLogModel.id).where(AuditLogModel.entity_id == uuid.UUID(entity_id))
    ).scalar_one()
    context.response = context.client.request(
        method, f"{CANONICAL}/{entry_id}", headers=_headers(context, role), json={}
    )


@when('the "{role}" sends "{method}" to the legacy audit log')
def step_mutating_legacy(context, role, method):
    context.response = context.client.request(method, LEGACY, headers=_headers(context, role), json={})


# --------------------------------------------------------------------------------------------------- respuesta
@then("the audit page has {count:d} items, total {total:d}, page {page:d} of {pages:d} with size {size:d}")
def step_page_metadata(context, count, total, page, pages, size):
    body = context.response.json()
    assert set(body) == PAGE_FIELDS, body.keys()
    actual = (len(body["items"]), body["total"], body["page"], body["total_pages"], body["size"])
    assert actual == (count, total, page, pages, size), f"se obtuvo {actual}: {context.response.text}"


@then("the audit items are ordered from newest to oldest")
def step_ordered(context):
    stamps = [_parse(i["occurred_at"]) for i in context.response.json()["items"]]
    assert stamps == sorted(stamps, reverse=True), stamps


@then("the audit items are exactly: {labels}")
def step_labels_exact(context, labels):
    expected = [x.strip() for x in labels.split(",") if x.strip()]
    assert _labels(context) == expected, f"se esperaba {expected} y se obtuvo {_labels(context)}"


@then("the audit items are empty")
def step_empty(context):
    body = context.response.json()
    assert body["items"] == [] and body["total"] == 0 and body["total_pages"] == 0, body


@then("every audit item belongs to the workspace of the token")
def step_same_workspace(context):
    for item in context.response.json()["items"]:
        assert item["workspace_id"] == str(context.workspace.id), item


@then('the audit item "{label}" shows the actor name "{name}"')
def step_actor_name(context, label, name):
    item = next(i for i in context.response.json()["items"] if context.audit_labels[i["entity_id"]] == label)
    assert item["actor_name"] == name, item


@then("every audit item exposes only the documented fields")
def step_documented_fields(context):
    for item in context.response.json()["items"]:
        assert set(item) == ENTRY_FIELDS, set(item) ^ ENTRY_FIELDS
        assert len(item["integrity_hash"]) == 64


@then("the audit response does not expose credentials or personal data")
def step_no_pii(context):
    body = context.response.text.lower()
    for forbidden in ("password", "token", "secret", "@demo.pe", "$2b$"):
        assert forbidden not in body, f"La respuesta contiene {forbidden!r}"


@then('the response header "{name}" is "{value}"')
def step_header_is(context, name, value):
    assert context.response.headers.get(name) == value, dict(context.response.headers)


@then('the response Link header points to the successor "{path}"')
def step_link_header(context, path):
    assert context.response.headers.get("Link") == f'<{path}>; rel="successor-version"', dict(context.response.headers)


@then('the response has no header "{name}"')
def step_no_header(context, name):
    assert name not in context.response.headers, dict(context.response.headers)


@then("both audit responses have status 200 and the same body")
def step_same_body(context):
    assert context.canonical_response.status_code == 200, context.canonical_response.text
    assert context.legacy_response.status_code == 200, context.legacy_response.text
    assert context.canonical_response.json() == context.legacy_response.json()


@then("the canonical audit response has no deprecation headers")
def step_canonical_clean(context):
    for name in ("Deprecation", "Link"):
        assert name not in context.canonical_response.headers, dict(context.canonical_response.headers)


@then("the audit entry count is unchanged")
def step_count_unchanged(context):
    assert _count(context) == context.audit_count, "La petición modificó la bitácora"


# --------------------------------------------------------------------------------------------------- OpenAPI
def _path_item(context, path: str) -> dict:
    return context.response.json()["paths"][path]


@then('the OpenAPI path "{path}" only allows the methods "{methods}"')
def step_only_methods(context, path, methods):
    expected = {m.strip().lower() for m in methods.split(",")}
    assert set(_path_item(context, path)) == expected, set(_path_item(context, path))


@then('the OpenAPI operation GET "{path}" is marked deprecated')
def step_deprecated(context, path):
    assert _path_item(context, path)["get"].get("deprecated") is True


@then('the OpenAPI operation GET "{path}" is not marked deprecated')
def step_not_deprecated(context, path):
    assert not _path_item(context, path)["get"].get("deprecated")


@then('the OpenAPI operation GET "{path}" declares the query parameters "{names}"')
def step_params(context, path, names):
    declared = {p["name"] for p in _path_item(context, path)["get"]["parameters"] if p["in"] == "query"}
    expected = {n.strip() for n in names.split(",")}
    assert expected <= declared, f"faltan {expected - declared}"


@then('the OpenAPI operation GET "{path}" documents the responses "{codes}"')
def step_documented_responses(context, path, codes):
    declared = set(_path_item(context, path)["get"]["responses"])
    expected = {c.strip() for c in codes.split(",")}
    assert expected <= declared, f"faltan {expected - declared}"


@then('the OpenAPI operation GET "{path}" has the summary "{summary}"')
def step_summary(context, path, summary):
    assert _path_item(context, path)["get"]["summary"] == summary
