"""Excepciones del contexto Helpdesk."""
from app.shared.domain.exceptions import DomainError, DomainValidationError, ResourceNotFoundError


class InvalidVisualEvidenceError(DomainValidationError):
    """La captura adjunta no es PNG/JPG o supera el tamaño permitido (US10)."""


class InvalidTicketDataError(DomainValidationError):
    """Faltan datos obligatorios del incidente o no son válidos (US10)."""


class InvalidTicketStateTransitionError(DomainError):
    """El cambio de estado no está permitido por la máquina de estados del ticket (TS04). Se traduce a HTTP 422."""


class TicketNotFoundError(ResourceNotFoundError):
    """El ticket no existe o pertenece a otro workspace (HTTP 404)."""


class TicketStatusChangeForbiddenError(DomainError):
    """El usuario no tiene permiso para hacer ese cambio de estado (HTTP 403)."""


class TicketAccessDeniedError(DomainError):
    """El ticket existe en el workspace, pero el usuario no es quien lo reportó ni pertenece a soporte (HTTP 403)."""


class EvidenceNotFoundError(ResourceNotFoundError):
    """La captura no existe o no pertenece al ticket (HTTP 404)."""


class InternalNoteNotAllowedError(DomainError):
    """Solo el equipo de soporte puede registrar notas internas (HTTP 403)."""


class TicketClosedError(DomainError):
    """El ticket está RESOLVED o CLOSED y no admite nuevos mensajes (HTTP 409, D30)."""


class NotificationNotFoundError(ResourceNotFoundError):
    """La notificación no existe o pertenece a otro usuario (HTTP 404)."""
