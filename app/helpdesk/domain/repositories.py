"""Contrato de persistencia del agregado Ticket."""
import uuid
from abc import ABC, abstractmethod

from app.helpdesk.domain.ticket import Ticket


class ITicketRepository(ABC):
    @abstractmethod
    def save(self, ticket: Ticket) -> Ticket:
        """Inserta o actualiza el ticket con sus evidencias y comentarios. Asigna el número público si es nuevo."""

    @abstractmethod
    def find_by_id(self, ticket_id: uuid.UUID) -> Ticket | None:
        """Devuelve el ticket o None si no existe."""

    @abstractmethod
    def find_by_reporter(self, reporter_id: uuid.UUID, workspace_id: uuid.UUID) -> list[Ticket]:
        """Devuelve los tickets creados por un colaborador en su workspace ordenados descendentemente (US13)."""
