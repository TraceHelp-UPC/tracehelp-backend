"""Excepciones del contexto Smart Triage."""
from app.shared.domain.exceptions import DomainValidationError

ILLEGIBLE_IMAGE_MESSAGE = (
    "No pudimos leer el texto de la captura. Sube una captura más nítida o describe el problema con más detalle."
)


class InvalidScreenshotError(DomainValidationError):
    """El archivo enviado al OCR no es una imagen PNG o JPG válida (HTTP 400)."""


class IllegibleImageError(DomainValidationError):
    """La captura está borrosa o no tiene texto legible y no hay descripción suficiente (US10, escenario 5)."""

    def __init__(self, detail: str = ILLEGIBLE_IMAGE_MESSAGE) -> None:
        super().__init__(detail)


class EmptyTriageQueryError(DomainValidationError):
    """No hay texto para buscar en los manuales (HTTP 400)."""


class MissingIncidentDataError(DomainValidationError):
    """No hay descripción ni captura para analizar (HTTP 400)."""
