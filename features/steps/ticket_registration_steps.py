"""Steps de la feature de registro multimodal de incidentes (T12, US10)."""
import io
import json
import os

from behave import given, then, when
from PIL import Image
from sqlalchemy import func, select

from app.helpdesk.domain.events import TicketRegistered
from app.helpdesk.infrastructure.persistence.models import TicketEvidenceModel, TicketModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.shared.infrastructure.event_bus import event_bus

TICKETS_URL = "/api/v1/tickets"
DEFAULT_FORM = {
    "title": "No puedo ingresar al ERP",
    "description": "Error 0x80070005 al iniciar sesión",
    "impact_level": "MEDIUM",
}


def _image(fmt: str, size=(800, 600)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 60, 90)).save(buffer, format=fmt)
    return buffer.getvalue()


def _noise_png(min_bytes: int) -> bytes:
    """PNG de ruido aleatorio (no se puede comprimir), así su peso supera min_bytes."""
    side = int((min_bytes / 3) ** 0.5) + 50
    image = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=0)
    return buffer.getvalue()


def _files_for(description: str) -> list[tuple[str, bytes, str]]:
    if description == "a PNG screenshot of the error":
        return [("error.png", _image("PNG"), "image/png")]
    if description == "a JPEG screenshot of 4000 by 3000 pixels":
        return [("captura.jpg", _image("JPEG", (4000, 3000)), "image/jpeg")]
    if description == "a GIF image":
        return [("error.gif", _image("GIF"), "image/gif")]
    if description == "a text file renamed as PNG":
        return [("virus.png", b"esto no es una imagen", "image/png")]
    if description == "a PNG image larger than 10 MB":
        return [("enorme.png", _noise_png(10 * 1024 * 1024 + 1), "image/png")]
    if description == "6 PNG screenshots":
        return [(f"captura-{i}.png", _image("PNG", (200, 150)), "image/png") for i in range(6)]
    raise AssertionError(f"Archivo de prueba no definido: {description}")


def _headers(context, role: str = "COLLABORATOR") -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _register(context, form: dict, files=None, headers=None) -> None:
    """Envía POST /tickets y guarda los eventos TicketRegistered publicados durante la petición."""
    received: list[TicketRegistered] = []
    event_bus.subscribe(TicketRegistered, received.append)
    try:
        context.response = context.client.post(
            TICKETS_URL,
            data=form,
            files=[("screenshots", f) for f in (files or [])],
            headers=headers if headers is not None else _headers(context),
        )
    finally:
        event_bus.unsubscribe(TicketRegistered, received.append)
    context.registered_events = received


def _blank(value: str) -> str:
    return "   " if value == "(blank)" else value


# ----------------------------------------------------------------------------- Given
@given("the collaborator has {file}")
def step_collaborator_has_file(context, file):
    context.files = _files_for(file)


# ----------------------------------------------------------------------------- When
@when('the collaborator registers an incident with title "{title}" and description "{description}"')
def step_register_text(context, title, description):
    _register(context, {**DEFAULT_FORM, "title": _blank(title), "description": _blank(description)})


@when("the collaborator registers the incident with the screenshots")
def step_register_with_screenshots(context):
    _register(context, DEFAULT_FORM, files=context.files)


@when('the collaborator registers an incident without the "{field}" field')
def step_register_without_field(context, field):
    _register(context, {k: v for k, v in DEFAULT_FORM.items() if k != field})


@when("an anonymous user registers an incident")
def step_register_anonymous(context):
    _register(context, DEFAULT_FORM, headers={})


# ----------------------------------------------------------------------------- Then
@then('the ticket is created in status "{status}" with a public code')
def step_ticket_created(context, status):
    body = context.response.json()
    assert body["status"] == status, body
    assert body["code"].startswith("TK-"), body
    assert body["reporter_id"] == str(context.users["COLLABORATOR"].id)
    assert context.session.get(TicketModel, body["id"]) is not None


@then("the ticket has {count:d} screenshots stored")
def step_screenshots_stored(context, count):
    ticket_id = context.response.json()["id"]
    stored = context.session.scalar(
        select(func.count()).select_from(TicketEvidenceModel).where(TicketEvidenceModel.ticket_id == ticket_id)
    )
    assert stored == count, f"Se esperaban {count} capturas y hay {stored}"
    assert len(context.response.json()["evidences"]) == count


@then('the stored screenshot is an "{mime_type}" file')
def step_stored_mime(context, mime_type):
    assert context.response.json()["evidences"][0]["mime_type"] == mime_type


@then("the stored screenshot is smaller than the original file")
def step_stored_smaller(context):
    original_size = len(context.files[0][1])
    assert context.response.json()["evidences"][0]["size_bytes"] < original_size


@then("the triage is notified about the new ticket")
def step_triage_notified(context):
    ticket_id = context.response.json()["id"]
    assert [str(e.ticket_id) for e in context.registered_events] == [ticket_id]


@then('the error detail mentions "{text}"')
def step_error_mentions(context, text):
    detail = context.response.json()["detail"]
    rendered = detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)
    assert text in rendered, f"'{text}' no aparece en: {rendered}"


@then("no ticket was created")
def step_no_ticket(context):
    total = context.session.scalar(
        select(func.count()).select_from(TicketModel).where(TicketModel.workspace_id == context.workspace.id)
    )
    assert total == 0, f"Se crearon {total} tickets"
