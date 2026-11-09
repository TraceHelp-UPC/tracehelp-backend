"""Steps de la feature de seguimiento y autoservicio del colaborador (T51, US13)."""
import io

from behave import given, then, when
from PIL import Image

from app.helpdesk.domain.enums import ImpactLevel
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.domain.value_objects import VisualEvidence
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider


def _collab_headers(context) -> dict[str, str]:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users["COLLABORATOR"].id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (120, 80), (40, 80, 120)).save(buf, format="PNG")
    return buf.getvalue()


@when('the collaborator searches their ticket history by the code of "{title}"')
def step_search_history_by_code(context, title: str):
    ticket = context.query_tickets[title]
    context.response = context.client.get(
        f"/api/v1/tickets/my-history?search={ticket.code}",
        headers=_collab_headers(context),
    )


@given('a ticket reported by the collaborator with a screenshot "{file_name}"')
def step_ticket_with_screenshot(context, file_name: str):
    raw = _png_bytes()
    evidence = VisualEvidence(
        file_name=file_name,
        mime_type="image/png",
        content=raw,
    )
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title="Error de certificado VPN",
        description="Aparece ventana de certificado inválido",
        impact_level=ImpactLevel.MEDIUM,
        evidences=[evidence],
    )
    saved = SqlAlchemyTicketRepository(context.session).save(ticket)
    context.ticket_id = saved.id
    context.evidence_id = saved.evidences[0].id


@given("a ticket reported by the collaborator with a public comment and an internal note")
def step_ticket_with_public_and_internal_comments(context):
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title="Fallo de acceso a correo",
        description="No sincroniza la bandeja de entrada",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.add_comment(
        author_id=context.users["ANALYST_L1"].id,
        content="Estamos revisando tu caso",
        is_internal_note=False,
    )
    ticket.add_comment(
        author_id=context.users["ANALYST_L1"].id,
        content="Nota interna: revisar servidor Exchange L2",
        is_internal_note=True,
    )
    saved = SqlAlchemyTicketRepository(context.session).save(ticket)
    context.ticket_id = saved.id


@when("the collaborator opens the detail of their reported ticket")
def step_collab_opens_own_ticket_detail(context):
    context.response = context.client.get(
        f"/api/v1/tickets/{context.ticket_id}",
        headers=_collab_headers(context),
    )


@then('the ticket detail includes the screenshot "{file_name}"')
def step_detail_includes_screenshot(context, file_name: str):
    evidences = context.response.json()["evidences"]
    assert len(evidences) == 1, evidences
    assert evidences[0]["file_name"] == file_name, evidences


@when("the collaborator requests the screenshot content of their reported ticket")
def step_collab_requests_screenshot_content(context):
    context.response = context.client.get(
        f"/api/v1/tickets/{context.ticket_id}/evidences/{context.evidence_id}",
        headers=_collab_headers(context),
    )


@then('the evidence response contains a PNG data URL for "{file_name}"')
def step_evidence_contains_data_url(context, file_name: str):
    body = context.response.json()
    assert body["file_name"] == file_name, body
    assert body["mime_type"] == "image/png", body
    assert body["data_url"].startswith("data:image/png;base64,"), body["data_url"][:40]


@then('the ticket detail shows only the public comment "{content}"')
def step_detail_shows_only_public_comment(context, content: str):
    comments = context.response.json()["comments"]
    assert [c["content"] for c in comments] == [content], comments


@then("the ticket detail does not include any internal notes")
def step_detail_no_internal_notes(context):
    comments = context.response.json()["comments"]
    assert all(not c["is_internal_note"] for c in comments), comments
