"""Excepciones del dominio de Analytics (TS06, US21)."""
from app.shared.domain.exceptions import DomainValidationError, ResourceNotFoundError


class InvalidDateRangeError(DomainValidationError):
    """La fecha inicial es posterior a la final (HTTP 400, type invalid-date-range)."""


class AuditEntryNotFoundError(ResourceNotFoundError):
    """La entrada de auditoría no existe o pertenece a otro workspace (HTTP 404, type audit-entry-not-found)."""


class TicketNotFoundError(ResourceNotFoundError):
    """El ticket no existe o pertenece a otro workspace (HTTP 404, type ticket-not-found)."""
