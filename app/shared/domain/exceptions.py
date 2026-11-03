"""Excepciones base del dominio. La T02 las traduce al formato RFC 7807."""


class DomainError(Exception):
    """Error de reglas de negocio."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class DomainValidationError(DomainError):
    """Datos que no cumplen las invariantes del dominio (se traduce a HTTP 400)."""


class ResourceNotFoundError(DomainError):
    """El recurso solicitado no existe (se traduce a HTTP 404)."""
