"""Excepciones del contexto Helpdesk."""
from app.shared.domain.exceptions import DomainValidationError


class InvalidVisualEvidenceError(DomainValidationError):
    """La captura adjunta no es PNG/JPG o supera el tamaño permitido (US10)."""


class InvalidTicketDataError(DomainValidationError):
    """Faltan datos obligatorios del incidente o no son válidos (US10)."""
