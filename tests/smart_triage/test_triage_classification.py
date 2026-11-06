"""Pruebas unitarias y de integración de clasificación automática y corrección por el analista (US27, T41, T42, T43)."""
import uuid

import pytest

from app.helpdesk.domain.enums import ImpactLevel, TicketPriority
from app.helpdesk.domain.events import TicketClassificationOverridden
from app.helpdesk.domain.exceptions import InvalidTicketDataError
from app.helpdesk.domain.ticket import Ticket
from app.smart_triage.domain.classification import DEFAULT_CATEGORY, TriageClassification


def test_infer_classification_from_clear_description():
    classification = TriageClassification.infer_from_incident(
        title="No conecta la VPN",
        description="Error de gateway TLS al intentar conectar a la red corporativa",
        impact_level=ImpactLevel.HIGH,
    )
    assert classification.category == "Conectividad y Red"
    assert classification.priority is TicketPriority.HIGH
    assert classification.is_fallback is False


def test_infer_critical_priority_when_high_impact_and_outage_keywords():
    classification = TriageClassification.infer_from_incident(
        title="Sistema ERP caído en toda la empresa",
        description="Bloqueo total en producción del módulo SAP",
        impact_level=ImpactLevel.HIGH,
    )
    assert classification.category == "Software Corporativo y ERP"
    assert classification.priority is TicketPriority.CRITICAL


def test_unidentifiable_description_falls_back_to_general_and_declared_impact():
    classification = TriageClassification.infer_from_incident(
        title="Consulta administrativa",
        description="Necesito información sobre un trámite",
        impact_level=ImpactLevel.LOW,
    )
    assert classification.category == DEFAULT_CATEGORY
    assert classification.priority is TicketPriority.LOW
    assert classification.is_fallback is True


def test_from_structured_output_falls_back_when_category_invalid():
    classification = TriageClassification.from_structured_output(
        "Categoría Inventada",
        "CRITICAL",
        impact_level=ImpactLevel.MEDIUM,
    )
    assert classification.category == DEFAULT_CATEGORY
    assert classification.priority is TicketPriority.MEDIUM
    assert classification.is_fallback is True


def test_override_classification_updates_ticket_and_preserves_suggested():
    ticket = Ticket.register(
        workspace_id=uuid.uuid4(),
        reporter_id=uuid.uuid4(),
        title="Fallo de login en correo Outlook",
        description="Mi contraseña no funciona en el buzón",
        impact_level=ImpactLevel.MEDIUM,
    )
    ticket.pull_events()
    original_suggested_cat = ticket.suggested_category
    original_suggested_prio = ticket.suggested_priority
    analyst_id = uuid.uuid4()

    ticket.override_classification(
        category="Correo y Colaboración",
        priority=TicketPriority.HIGH,
        analyst_id=analyst_id,
    )

    assert ticket.category == "Correo y Colaboración"
    assert ticket.priority is TicketPriority.HIGH
    assert ticket.suggested_category == original_suggested_cat
    assert ticket.suggested_priority == original_suggested_prio
    events = ticket.pull_events()
    assert len(events) == 1
    assert isinstance(events[0], TicketClassificationOverridden)
    assert events[0].new_category == "Correo y Colaboración"


def test_override_with_invalid_category_raises_error():
    ticket = Ticket.register(
        workspace_id=uuid.uuid4(),
        reporter_id=uuid.uuid4(),
        title="Error VPN",
        description="Sin red",
        impact_level=ImpactLevel.LOW,
    )
    with pytest.raises(InvalidTicketDataError):
        ticket.override_classification(
            category="Categoría No Existente",
            priority=TicketPriority.HIGH,
            analyst_id=uuid.uuid4(),
        )


def test_override_classification_endpoint_api(db_session, workspace_and_users, api_client, auth_headers):
    _, collaborator, analyst = workspace_and_users

    create_resp = api_client.post(
        "/api/v1/tickets",
        data={
            "title": "Fallo en red WiFi",
            "description": "No tengo conexión a internet en el piso 3",
            "impact_level": "MEDIUM",
        },
        headers=auth_headers(db_session, collaborator),
    )
    assert create_resp.status_code == 201
    created = create_resp.json()
    ticket_id = created["id"]
    assert created["category"] == "Conectividad y Red"
    assert created["suggested_category"] == "Conectividad y Red"

    patch_resp = api_client.patch(
        f"/api/v1/tickets/{ticket_id}/classification",
        json={"category": "Hardware y Periféricos", "priority": "HIGH"},
        headers=auth_headers(db_session, analyst),
    )
    assert patch_resp.status_code == 200, patch_resp.text
    updated = patch_resp.json()
    assert updated["category"] == "Hardware y Periféricos"
    assert updated["priority"] == "HIGH"
    assert updated["suggested_category"] == "Conectividad y Red"
    assert updated["suggested_priority"] == "MEDIUM"

    forbidden_resp = api_client.patch(
        f"/api/v1/tickets/{ticket_id}/classification",
        json={"category": "General", "priority": "LOW"},
        headers=auth_headers(db_session, collaborator),
    )
    assert forbidden_resp.status_code == 403
