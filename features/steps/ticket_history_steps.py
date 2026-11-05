"""Steps de la feature de historial y detalle de tickets (US13, T51)."""
import uuid
from behave import given, then, when

from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketPriority, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.domain.enums import RoleName
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PlainPassword
from app.iam.infrastructure.persistence.models import WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher

HASHER = BcryptPasswordHasher(rounds=4)


def _get_or_create_workspace(context):
    if not hasattr(context, "workspace_id") or context.workspace_id is None:
        workspace = WorkspaceModel(
            id=uuid.uuid4(),
            name="Empresa BDD US13",
            subdomain=f"us13-{uuid.uuid4().hex[:6]}",
        )
        context.session.add(workspace)
        context.session.flush()
        context.workspace_id = workspace.id
    return context.workspace_id


def _create_user_and_login(context, email, role=RoleName.COLLABORATOR):
    workspace_id = _get_or_create_workspace(context)
    user_repo = SqlAlchemyUserRepository(context.session)
    user = user_repo.find_by_email(EmailAddress(email))
    if user is None:
        user = User.register(
            workspace_id=workspace_id,
            full_name="Usuario Pruebas",
            email=EmailAddress(email),
            password_hash=HASHER.hash(PlainPassword("Segura123")),
            role=role,
            department="Operaciones",
        )
        user_repo.save(user)
        context.session.flush()

    login_res = context.client.post("/api/v1/auth/login", json={"email": email, "password": "Segura123"})
    assert login_res.status_code == 200, login_res.text
    token = login_res.json()["access_token"]
    return user, token


@given('an authenticated collaborator "{email}" with {count:d} reported tickets')
def step_collab_with_tickets(context, email, count):
    user, token = _create_user_and_login(context, email)
    context.current_user = user
    context.auth_token = token
    context.headers = {"Authorization": f"Bearer {token}"}

    ticket_repo = SqlAlchemyTicketRepository(context.session)
    context.created_tickets = []
    for i in range(count):
        ticket = Ticket(
            id=uuid.uuid4(),
            workspace_id=context.workspace_id,
            reporter_id=user.id,
            title=f"Incidente {i+1} de {email}",
            description=f"Descripción detallada del problema {i+1}",
            impact_level=ImpactLevel.MEDIUM,
            affected_module="VPN",
            status=TicketStatus.OPEN,
            priority=TicketPriority.MEDIUM,
            current_tier=SupportTier.SELF_SERVICE,
        )
        ticket_repo.save(ticket)
        context.created_tickets.append(ticket)
    context.session.flush()


@given('an authenticated collaborator "{email}" with no reported tickets')
def step_collab_no_tickets(context, email):
    user, token = _create_user_and_login(context, email)
    context.current_user = user
    context.auth_token = token
    context.headers = {"Authorization": f"Bearer {token}"}


@given('an authenticated collaborator "{email}"')
def step_collab_auth(context, email):
    user, token = _create_user_and_login(context, email)
    context.current_user = user
    context.auth_token = token
    context.headers = {"Authorization": f"Bearer {token}"}


@given('a ticket reported by collaborator "{email}"')
def step_other_collab_ticket(context, email):
    other_user, _ = _create_user_and_login(context, email)
    ticket_repo = SqlAlchemyTicketRepository(context.session)
    ticket = Ticket(
        id=uuid.uuid4(),
        workspace_id=context.workspace_id,
        reporter_id=other_user.id,
        title=f"Ticket ajeno de {email}",
        description="Información sensible de otro departamento",
        impact_level=ImpactLevel.HIGH,
        affected_module="Finanzas",
        status=TicketStatus.OPEN,
        priority=TicketPriority.HIGH,
        current_tier=SupportTier.SELF_SERVICE,
    )
    ticket_repo.save(ticket)
    context.session.flush()
    context.target_ticket_id = ticket.id


@given('a ticket reported by the collaborator with a validated public comment "{comment}"')
def step_ticket_with_comment(context, comment):
    ticket_repo = SqlAlchemyTicketRepository(context.session)
    ticket = Ticket(
        id=uuid.uuid4(),
        workspace_id=context.workspace_id,
        reporter_id=context.current_user.id,
        title="Problema con respuesta validada",
        description="No puedo acceder a la unidad compartida",
        impact_level=ImpactLevel.MEDIUM,
        affected_module="Red",
        status=TicketStatus.RESOLVED,
        priority=TicketPriority.MEDIUM,
        current_tier=SupportTier.TIER_L1,
    )
    ticket.add_comment(
        author_id=context.current_user.id,
        content=comment,
        is_internal_note=False,
    )
    ticket_repo.save(ticket)
    context.session.flush()
    context.target_ticket_id = ticket.id


@when("the collaborator requests their ticket history")
def step_get_history(context):
    context.response = context.client.get("/api/v1/tickets/my-history", headers=context.headers)


@when('collaborator "{email}" attempts to view the ticket details')
def step_attempt_view_other_ticket(context, email):
    context.response = context.client.get(
        f"/api/v1/tickets/{context.target_ticket_id}",
        headers=context.headers,
    )


@when("the collaborator requests the ticket details")
def step_request_ticket_details(context):
    context.response = context.client.get(
        f"/api/v1/tickets/{context.target_ticket_id}",
        headers=context.headers,
    )


@then("the history response contains {count:d} tickets")
def step_verify_history_count(context, count):
    body = context.response.json()
    assert isinstance(body, list), f"Se esperaba una lista y se obtuvo: {body}"
    assert len(body) == count, f"Se esperaban {count} tickets y llegaron {len(body)}"


@then("the ticket history is empty")
def step_verify_empty_history(context):
    body = context.response.json()
    assert isinstance(body, list), f"Se esperaba una lista y se obtuvo: {body}"
    assert len(body) == 0, f"Se esperaba lista vacía y tiene {len(body)} elementos"


@then("the response contains an access forbidden message")
def step_verify_forbidden_message(context):
    body = context.response.json()
    assert "detail" in body, f"No se encontró 'detail' en: {body}"
    assert "permiso" in body["detail"].lower() or "forbidden" in body["detail"].lower()


@then('the response contains the comment "{comment}"')
def step_verify_comment_present(context, comment):
    body = context.response.json()
    assert "comments" in body, f"No se encontró campo comments en la respuesta: {body}"
    comments_content = [c["content"] for c in body["comments"]]
    assert comment in comments_content, f"Comentario '{comment}' no encontrado en {comments_content}"
