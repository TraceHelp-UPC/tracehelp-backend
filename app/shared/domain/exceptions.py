"""Excepciones base del dominio.

Los manejadores globales (app/shared/interfaces/rest/problem_details.py, T02) las traducen al formato RFC 7807:
ResourceNotFoundError -> 404, DomainValidationError -> 400 y cualquier otro DomainError -> 422.
Los códigos especiales (401, 403...) se declaran en app/core/error_handlers.py.
"""


class DomainError(Exception):
    """Error de reglas de negocio."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class DomainValidationError(DomainError):
    """Datos que no cumplen las invariantes del dominio (se traduce a HTTP 400)."""


class ResourceNotFoundError(DomainError):
    """El recurso solicitado no existe (se traduce a HTTP 404)."""
