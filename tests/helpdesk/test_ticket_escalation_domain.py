"""Pruebas unitarias de escalamiento L2, devolución a L1, guardas y auditoría (US17, T79)."""
import ast
import pathlib
import uuid
from datetime import UTC, datetime

import pytest

from app.analytics.application.audit_log_service import AuditEventHandler
from app.helpdesk.application.ports import TriageContextSnapshot, TriageContextSource
from app.helpdesk.application.status_change_policy import Actor, ensure_can_work_escalated
from app.helpdesk.application.ticket_command_service import (
    MAX_SNAPSHOT_OCR_LENGTH,
    _format_escalation_snapshot,
    _format_return_to_l1_note,
)
from app.helpdesk.domain.enums import ImpactLevel, SupportTier, TicketCategory, TicketPriority, TicketStatus
from app.helpdesk.domain.events import MessagePosted, TicketEscalated, TicketReturnedToL1, TicketStatusChanged
from app.helpdesk.domain.exceptions import (
    InvalidTicketDataError,
    InvalidTicketStateTransitionError,
    TicketStatusChangeForbiddenError,
)
from app.helpdesk.domain.ticket import MAX_MESSAGE_LENGTH, MAX_REASON_LENGTH, Ticket
from app.iam.domain.permissions import Permission
from app.shared.domain.specialist_group import SpecialistGroup


def _ticket(
    status: TicketStatus = TicketStatus.ASSIGNED_L1,
    *,
    assigned_analyst_id: uuid.UUID | None = None,
    with_analyst: bool = True,
    escalated_group: SpecialistGroup | None = None,
    escalated_at: datetime | None = None,
    assigned_specialist_id: uuid.UUID | None = None,
    specialist_claimed_at: datetime | None = None,
) -> Ticket:
    ticket = Ticket.register(
        workspace_id=uuid.uuid4(),
        reporter_id=uuid.uuid4(),
        title="VPN error 809",
        description="No conecta a la VPN corporativa.",
        impact_level=ImpactLevel.MEDIUM,
        affected_module="VPN corporativa",
    )
    ticket.pull_events()
    ticket.number = 42
    ticket.status = status
    ticket.category = TicketCategory.NETWORK_VPN
    ticket.priority = TicketPriority.HIGH
    ticket.current_tier = SupportTier.TIER_L2 if status is TicketStatus.ESCALATED_L2 else SupportTier.TIER_L1
    ticket.assigned_analyst_id = assigned_analyst_id if assigned_analyst_id is not None else (uuid.uuid4() if with_analyst else None)
    ticket.escalated_group = escalated_group
    ticket.escalated_at = escalated_at
    ticket.assigned_specialist_id = assigned_specialist_id
    ticket.specialist_claimed_at = specialist_claimed_at
    return ticket


def _actor(*permissions: Permission) -> Actor:
    return Actor(
        id=uuid.uuid4(),
        workspace_id=uuid.uuid4(),
        permissions=frozenset(p.value for p in permissions),
    )


# --- Dominio: escalate --------------------------------------------------------------------------------------

def test_escalate_transitions_clears_claim_keeps_l1_adds_internal_note_and_emits_events():
    old_specialist = uuid.uuid4()
    ticket = _ticket(
        status=TicketStatus.ASSIGNED_L1,
        assigned_specialist_id=old_specialist,
        specialist_claimed_at=datetime(2026, 11, 20, 10, 0, tzinfo=UTC),
    )
    original_analyst = ticket.assigned_analyst_id
    escalator = uuid.uuid4()
    long_snapshot = "[ESCALAMIENTO A L2 · REDES]\n" + ("detalle técnico " * 200)
    assert len(long_snapshot) > MAX_MESSAGE_LENGTH

    comment = ticket.escalate(
        escalated_by=escalator,
        specialist_group=SpecialistGroup.REDES,
        reason="  Error 809 persiste tras reiniciar perfil VPN  ",
        context_snapshot=long_snapshot,
        has_triage_snapshot=True,
    )

    assert ticket.status is TicketStatus.ESCALATED_L2
    assert ticket.current_tier is SupportTier.TIER_L2
    assert ticket.escalated_group is SpecialistGroup.REDES
    assert ticket.escalated_at is not None
    assert ticket.assigned_analyst_id == original_analyst
    assert ticket.assigned_specialist_id is None
    assert ticket.specialist_claimed_at is None
    assert comment.is_internal_note is True
    assert comment.is_ai_generated is False
    assert comment.content == long_snapshot.strip()
    assert comment in ticket.comments

    events = ticket.pull_events()
    assert [type(e) for e in events] == [TicketStatusChanged, TicketEscalated]
    assert not any(isinstance(e, MessagePosted) for e in events)
    escalated_event = events[1]
    assert escalated_event.ticket_id == ticket.id
    assert escalated_event.workspace_id == ticket.workspace_id
    assert escalated_event.escalated_by == escalator
    assert escalated_event.specialist_group == "REDES"
    assert escalated_event.assigned_analyst_id == original_analyst
    assert escalated_event.has_triage_snapshot is True
    assert escalated_event.reason == "Error 809 persiste tras reiniciar perfil VPN"


@pytest.mark.parametrize(
    "status",
    [s for s in TicketStatus if s is not TicketStatus.ASSIGNED_L1],
)
def test_escalate_rejects_statuses_other_than_assigned_l1(status):
    ticket = _ticket(status=status)
    with pytest.raises(InvalidTicketStateTransitionError):
        ticket.escalate(
            escalated_by=uuid.uuid4(),
            specialist_group=SpecialistGroup.REDES,
            reason="Requiere soporte de nivel 2",
            context_snapshot="[ESCALAMIENTO]",
            has_triage_snapshot=False,
        )
    assert ticket.status is status
    assert ticket.comments == []
    assert ticket.pull_events() == []


def test_escalate_rejects_empty_or_too_long_reason_without_side_effects():
    ticket = _ticket(status=TicketStatus.ASSIGNED_L1)
    with pytest.raises(InvalidTicketDataError):
        ticket.escalate(
            escalated_by=uuid.uuid4(),
            specialist_group=SpecialistGroup.REDES,
            reason="   ",
            context_snapshot="[ESCALAMIENTO]",
            has_triage_snapshot=False,
        )
    with pytest.raises(InvalidTicketDataError):
        ticket.escalate(
            escalated_by=uuid.uuid4(),
            specialist_group=SpecialistGroup.REDES,
            reason="x" * (MAX_REASON_LENGTH + 1),
            context_snapshot="[ESCALAMIENTO]",
            has_triage_snapshot=False,
        )
    assert ticket.status is TicketStatus.ASSIGNED_L1
    assert ticket.escalated_group is None
    assert ticket.comments == []
    assert ticket.pull_events() == []


# --- Dominio: return_to_l1 ----------------------------------------------------------------------------------

def test_return_to_l1_restores_original_l1_clears_claim_keeps_escalation_metadata_and_truncates_history_reason():
    escalated_at = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    original_analyst = uuid.uuid4()
    specialist = uuid.uuid4()
    ticket = _ticket(
        status=TicketStatus.ESCALATED_L2,
        assigned_analyst_id=original_analyst,
        escalated_group=SpecialistGroup.REDES,
        escalated_at=escalated_at,
        assigned_specialist_id=specialist,
        specialist_claimed_at=datetime(2026, 11, 20, 12, 30, tzinfo=UTC),
    )
    long_request = "A" * 750

    comment = ticket.return_to_l1(
        returned_by=specialist,
        requested_info=long_request,
        internal_note=f"[DEVOLUCIÓN DE L2 A L1 · REDES]\nInformación adicional solicitada: {long_request}",
    )

    assert ticket.status is TicketStatus.ASSIGNED_L1
    assert ticket.current_tier is SupportTier.TIER_L1
    assert ticket.assigned_analyst_id == original_analyst
    assert ticket.assigned_specialist_id is None
    assert ticket.specialist_claimed_at is None
    # Historial y FCR (T103) exigen conservar escalated_group y escalated_at
    assert ticket.escalated_group is SpecialistGroup.REDES
    assert ticket.escalated_at == escalated_at
    assert comment.is_internal_note is True
    assert comment.is_ai_generated is False
    assert ticket.status_history[-1].reason == long_request[:MAX_REASON_LENGTH]
    assert len(ticket.status_history[-1].reason) == MAX_REASON_LENGTH

    events = ticket.pull_events()
    assert [type(e) for e in events] == [TicketStatusChanged, TicketReturnedToL1]
    assert not any(isinstance(e, MessagePosted) for e in events)
    returned_event = events[1]
    assert returned_event.returned_by == specialist
    assert returned_event.assigned_analyst_id == original_analyst
    assert returned_event.escalated_group == "REDES"
    assert returned_event.reason == long_request


@pytest.mark.parametrize(
    "status",
    [s for s in TicketStatus if s is not TicketStatus.ESCALATED_L2],
)
def test_return_to_l1_rejects_any_status_other_than_escalated_l2(status):
    ticket = _ticket(status=status)
    with pytest.raises(InvalidTicketStateTransitionError):
        ticket.return_to_l1(
            returned_by=uuid.uuid4(),
            requested_info="Solicitar ipconfig /all al usuario",
            internal_note="[DEVOLUCIÓN]\nSolicitar ipconfig /all al usuario",
        )
    assert ticket.status is status
    assert ticket.pull_events() == []


def test_return_to_l1_rejects_legacy_ticket_without_original_analyst():
    ticket = _ticket(status=TicketStatus.ESCALATED_L2, with_analyst=False, escalated_group=SpecialistGroup.REDES)
    with pytest.raises(InvalidTicketDataError) as exc_info:
        ticket.return_to_l1(
            returned_by=uuid.uuid4(),
            requested_info="Necesitamos captura del comando ipconfig /all",
            internal_note="[DEVOLUCIÓN]\nNecesitamos captura del comando ipconfig /all",
        )
    assert exc_info.value.detail == "El ticket no tiene un analista L1 original asignado para devolverlo."
    assert ticket.status is TicketStatus.ESCALATED_L2
    assert ticket.pull_events() == []


def test_return_to_l1_rejects_empty_or_too_long_requested_info():
    ticket = _ticket(status=TicketStatus.ESCALATED_L2, escalated_group=SpecialistGroup.REDES)
    with pytest.raises(InvalidTicketDataError):
        ticket.return_to_l1(returned_by=uuid.uuid4(), requested_info="  ", internal_note="[DEVOLUCIÓN]")
    with pytest.raises(InvalidTicketDataError):
        ticket.return_to_l1(
            returned_by=uuid.uuid4(),
            requested_info="x" * (MAX_MESSAGE_LENGTH + 1),
            internal_note="[DEVOLUCIÓN]",
        )
    assert ticket.status is TicketStatus.ESCALATED_L2


# --- Guarda ensure_can_work_escalated (D20 / D30) -----------------------------------------------------------

def test_ensure_can_work_escalated_requires_permission():
    ticket = _ticket(status=TicketStatus.ESCALATED_L2, escalated_group=SpecialistGroup.REDES)
    l1_actor = _actor(Permission.TICKETS_MANAGE, Permission.TICKETS_ESCALATE)
    with pytest.raises(TicketStatusChangeForbiddenError):
        ensure_can_work_escalated(l1_actor, ticket, SpecialistGroup.REDES)


def test_ensure_can_work_escalated_checks_group_and_allows_null_group_for_any_l2():
    l2_actor = _actor(Permission.TICKETS_MANAGE, Permission.TICKETS_RESOLVE_ESCALATED)
    redes_ticket = _ticket(status=TicketStatus.ESCALATED_L2, escalated_group=SpecialistGroup.REDES)
    legacy_ticket = _ticket(status=TicketStatus.ESCALATED_L2, escalated_group=None)

    ensure_can_work_escalated(l2_actor, redes_ticket, SpecialistGroup.REDES)
    ensure_can_work_escalated(l2_actor, legacy_ticket, SpecialistGroup.SEGURIDAD)
    ensure_can_work_escalated(l2_actor, legacy_ticket, None)

    with pytest.raises(TicketStatusChangeForbiddenError) as exc_other:
        ensure_can_work_escalated(l2_actor, redes_ticket, SpecialistGroup.SEGURIDAD)
    assert exc_other.value.detail == "El ticket está escalado al grupo REDES."

    with pytest.raises(TicketStatusChangeForbiddenError) as exc_none:
        ensure_can_work_escalated(l2_actor, redes_ticket, None)
    assert exc_none.value.detail == "El ticket está escalado al grupo REDES."


# --- Formateo determinístico del snapshot y nota de devolución ----------------------------------------------

def test_format_escalation_snapshot_with_full_triage_and_truncated_ocr():
    ticket = _ticket(status=TicketStatus.ASSIGNED_L1)
    triage = TriageContextSnapshot(
        outcome="ANSWERED",
        confidence_level="GROUNDED",
        best_score=0.742,
        summary="Revisar puerto UDP 4500 bloqueado en firewall.",
        steps=("Verificar perfil VPN", "Revisar regla UDP 4500"),
        suggested_category="Red/VPN",
        suggested_priority="HIGH",
        ocr_legible=True,
        ocr_error_codes=("ERR_809", "VPN_TIMEOUT"),
        ocr_masked_text="B" * (MAX_SNAPSHOT_OCR_LENGTH + 50),
        sources=(
            TriageContextSource(
                reference="F1",
                document_title="Manual VPN Corporativa v2",
                citation="Sección 4.2 · Error 809",
                similarity=0.742,
            ),
        ),
    )

    text = _format_escalation_snapshot(
        ticket=ticket,
        specialist_group=SpecialistGroup.REDES,
        reason="Persiste el error 809 en Windows 11",
        triage=triage,
    )

    assert "[ESCALAMIENTO A L2 · REDES]" in text
    assert "Motivo del escalamiento: Persiste el error 809 en Windows 11" in text
    assert "Clasificación: Categoría=Red/VPN | Prioridad=HIGH | Impacto=MEDIUM | Módulo=VPN corporativa" in text
    assert "Triaje IA: Revisar puerto UDP 4500 bloqueado en firewall. (resultado=ANSWERED, confianza=GROUNDED, score=0.74)" in text
    assert "OCR (anonimizado): Códigos: ERR_809, VPN_TIMEOUT | " + ("B" * MAX_SNAPSHOT_OCR_LENGTH) + "…" in text
    assert "- [F1] Sección 4.2 · Error 809 (Manual VPN Corporativa v2)" in text


def test_format_escalation_snapshot_without_triage_and_with_illegible_ocr():
    ticket = _ticket(status=TicketStatus.ASSIGNED_L1)
    ticket.category = None
    ticket.affected_module = None

    no_triage = _format_escalation_snapshot(
        ticket=ticket,
        specialist_group=SpecialistGroup.INFRAESTRUCTURA,
        reason="Servidor sin respuesta",
        triage=None,
    )
    assert "Clasificación: Categoría=Sin categoría | Prioridad=HIGH | Impacto=MEDIUM | Módulo=No especificado" in no_triage
    assert "Triaje IA: Sin diagnóstico automático registrado al momento del escalamiento.\n" in no_triage
    assert "OCR (anonimizado): Sin evidencia OCR" in no_triage
    assert "Fuentes consultadas:\n- Sin fuentes consultadas" in no_triage

    illegible = _format_escalation_snapshot(
        ticket=ticket,
        specialist_group=SpecialistGroup.APLICACIONES,
        reason="Error al emitir factura",
        triage=TriageContextSnapshot(
            outcome="LOW_CONFIDENCE",
            confidence_level="LOW",
            best_score=0.41,
            summary=None,
            steps=(),
            suggested_category=None,
            suggested_priority=None,
            ocr_legible=False,
            ocr_error_codes=(),
            ocr_masked_text=None,
            sources=(),
        ),
    )
    assert "OCR (anonimizado): Captura adjunta no legible" in illegible
    assert "- Sin fuentes consultadas" in illegible


def test_format_return_to_l1_note_with_and_without_group():
    ticket_with_group = _ticket(status=TicketStatus.ESCALATED_L2, escalated_group=SpecialistGroup.SEGURIDAD)
    note = _format_return_to_l1_note(ticket=ticket_with_group, requested_info="  Adjuntar log de acceso  ")
    assert note == "[DEVOLUCIÓN DE L2 A L1 · SEGURIDAD]\nInformación adicional solicitada: Adjuntar log de acceso"

    ticket_legacy = _ticket(status=TicketStatus.ESCALATED_L2, escalated_group=None)
    legacy_note = _format_return_to_l1_note(ticket=ticket_legacy, requested_info="Confirmar red usada")
    assert legacy_note == "[DEVOLUCIÓN DE L2 A L1 · L2]\nInformación adicional solicitada: Confirmar red usada"


# --- Auditoría: ramas explícitas para TicketEscalated y TicketReturnedToL1 ----------------------------------

def test_audit_entry_for_ticket_escalated_and_returned_has_explicit_branch_and_masks_pii():
    analyst_id = uuid.uuid4()
    specialist_id = uuid.uuid4()
    ticket = _ticket(status=TicketStatus.ASSIGNED_L1, assigned_analyst_id=analyst_id)

    ticket.escalate(
        escalated_by=analyst_id,
        specialist_group=SpecialistGroup.REDES,
        reason="El correo del afectado es maria.lopez@empresa.pe y falla la VPN",
        context_snapshot="[ESCALAMIENTO A L2 · REDES]\nDetalle",
        has_triage_snapshot=True,
    )
    escalated_event = [e for e in ticket.pull_events() if isinstance(e, TicketEscalated)][0]

    handler = AuditEventHandler()
    escalated_entry = handler.to_audit_entry(escalated_event)

    assert escalated_entry is not None
    assert escalated_entry.event_type == "TicketEscalated"
    assert escalated_entry.actor_id == analyst_id
    assert escalated_entry.entity_type == "ticket"
    assert escalated_entry.entity_id == ticket.id
    assert escalated_entry.ticket_id == ticket.id
    assert escalated_entry.detail["specialist_group"] == "REDES"
    assert escalated_entry.detail["assigned_analyst_id"] == str(analyst_id)
    assert escalated_entry.detail["has_triage_snapshot"] is True
    assert "maria.lopez@empresa.pe" not in escalated_entry.detail["reason"]
    assert escalated_entry.verify_integrity()

    ticket.return_to_l1(
        returned_by=specialist_id,
        requested_info="Pedir ipconfig al correo maria.lopez@empresa.pe",
        internal_note="[DEVOLUCIÓN DE L2 A L1 · REDES]\nPedir ipconfig",
    )
    returned_event = [e for e in ticket.pull_events() if isinstance(e, TicketReturnedToL1)][0]
    returned_entry = handler.to_audit_entry(returned_event)

    assert returned_entry is not None
    assert returned_entry.event_type == "TicketReturnedToL1"
    assert returned_entry.actor_id == specialist_id
    assert returned_entry.entity_type == "ticket"
    assert returned_entry.entity_id == ticket.id
    assert returned_entry.ticket_id == ticket.id
    assert returned_entry.detail["assigned_analyst_id"] == str(analyst_id)
    assert returned_entry.detail["escalated_group"] == "REDES"
    assert "maria.lopez@empresa.pe" not in returned_entry.detail["reason"]
    assert returned_entry.verify_integrity()


# --- Aislamiento ACL (helpdesk no importa app.smart_triage) -------------------------------------------------

def test_triage_context_reader_does_not_import_smart_triage():
    reader_path = pathlib.Path("app/helpdesk/infrastructure/persistence/triage_context_reader.py")
    tree = ast.parse(reader_path.read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(mod.startswith("app.smart_triage") for mod in imported), imported
