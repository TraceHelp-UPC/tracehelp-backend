"""Excepciones de dominio del Bounded Context Analytics."""
from app.shared.domain.exceptions import DomainValidationError


class InvalidAuditLogDataError(DomainValidationError):
    """Los datos del registro de auditoría o los parámetros de paginación no son válidos."""
