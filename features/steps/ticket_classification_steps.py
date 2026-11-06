"""Steps de la feature de clasificación y priorización automática del incidente (US27, T41, T42, T43)."""
import uuid

from behave import given, then, when

from app.helpdesk.domain.enums import ImpactLevel, TicketPriority
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.smart_triage.domain.classification import TriageClassification


def _token(context, role: str) -> str:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    return token


@when(
    'the collaborator reports an incident titled "{title}" with description "{description}" and impact "{impact}"'
)
def step_report_incident_for_classification(context, title, description, impact):
    context.response = context.client.post(
        "/api/v1/tickets",
        data={"title": title, "description": description, "impact_level": impact},
        headers={"Authorization": f"Bearer {_token(context, 'COLLABORATOR')}"},
    )
    if context.response.status_code == 201:
        context.ticket_id = uuid.UUID(context.response.json()["id"])


@given('a classified ticket in category "{category}" with priority "{priority}"')
def step_classified_ticket(context, category, priority):
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title="Problema de conexión VPN",
        description="Error al conectar a la red corporativa",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.apply_triage_classification(
        TriageClassification(category=category, priority=TicketPriority(priority))
    )
    SqlAlchemyTicketRepository(context.session).save(ticket)
    context.session.flush()
    context.ticket_id = ticket.id


@when('the "{role}" updates the ticket classification to category "{category}" and priority "{priority}"')
def step_update_classification(context, role, category, priority):
    context.response = context.client.patch(
        f"/api/v1/tickets/{context.ticket_id}/classification",
        json={"category": category, "priority": priority},
        headers={"Authorization": f"Bearer {_token(context, role)}"},
    )


@then('the ticket category is "{expected_category}"')
def step_verify_category(context, expected_category):
    body = context.response.json()
    assert body["category"] == expected_category, f"Esperado {expected_category}, obtenido {body['category']}"


@then('the ticket priority is "{expected_priority}"')
def step_verify_priority(context, expected_priority):
    body = context.response.json()
    assert body["priority"] == expected_priority, f"Esperado {expected_priority}, obtenido {body['priority']}"


@then('the suggested classification is "{expected_category}" with priority "{expected_priority}"')
def step_verify_suggested_classification(context, expected_category, expected_priority):
    body = context.response.json()
    assert body["suggested_category"] == expected_category
    assert body["suggested_priority"] == expected_priority
