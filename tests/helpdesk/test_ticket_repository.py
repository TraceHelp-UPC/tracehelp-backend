"""Pruebas de integración del repositorio de tickets contra PostgreSQL (requieren TEST_DATABASE_URL)."""
from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.domain.value_objects import VisualEvidence
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 2048


def test_save_assigns_number_and_persists_evidence_and_comments(db_session, workspace_and_users):
    workspace, collaborator, analyst = workspace_and_users
    repo = SqlAlchemyTicketRepository(db_session)

    ticket = Ticket.register(
        workspace_id=workspace.id,
        reporter_id=collaborator.id,
        title="VPN no conecta",
        description="Error 809 al conectar la VPN desde casa.",
        impact_level=ImpactLevel.MEDIUM,
        evidences=[VisualEvidence("vpn.png", "image/png", PNG)],
    )
    repo.save(ticket)
    assert ticket.number is not None and ticket.code.startswith("TK-")

    ticket.add_comment(author_id=analyst.id, content="Nota interna de prueba", is_internal_note=True)
    repo.save(ticket)
    db_session.expire_all()

    loaded = repo.find_by_id(ticket.id)
    assert loaded is not None
    assert loaded.status is TicketStatus.OPEN
    assert loaded.code == ticket.code
    assert len(loaded.evidences) == 1 and loaded.evidences[0].content == PNG
    assert len(loaded.comments) == 1 and loaded.comments[0].is_internal_note is True


def test_ticket_numbers_are_sequential(db_session, workspace_and_users):
    workspace, collaborator, _ = workspace_and_users
    repo = SqlAlchemyTicketRepository(db_session)
    first = repo.save(Ticket.register(workspace_id=workspace.id, reporter_id=collaborator.id, title="A", description="a", impact_level=ImpactLevel.LOW))
    second = repo.save(Ticket.register(workspace_id=workspace.id, reporter_id=collaborator.id, title="B", description="b", impact_level=ImpactLevel.LOW))
    assert second.number == first.number + 1


def test_find_by_id_returns_none_for_unknown_ticket(db_session):
    import uuid

    assert SqlAlchemyTicketRepository(db_session).find_by_id(uuid.uuid4()) is None
