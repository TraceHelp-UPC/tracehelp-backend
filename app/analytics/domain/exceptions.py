"""Excepciones del dominio de Analytics (TS06)."""
from app.shared.domain.exceptions import DomainValidationError


class InvalidDateRangeError(DomainValidationError):
    """La fecha inicial es posterior a la final (HTTP 400, type invalid-date-range)."""
