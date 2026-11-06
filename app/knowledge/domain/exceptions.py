"""Excepciones del contexto Knowledge Management."""
from app.shared.domain.exceptions import DomainError, DomainValidationError, ResourceNotFoundError


class UnsupportedDocumentFormatError(DomainValidationError):
    """El archivo no es PDF ni Markdown, o su contenido no corresponde a la extensión (HTTP 400)."""


class FileSizeExceededError(DomainValidationError):
    """El archivo supera el tamaño máximo de 25 MB (HTTP 400)."""


class InvalidDocumentDataError(DomainValidationError):
    """Faltan datos del documento o del fragmento, o no son válidos (HTTP 400)."""


class InvalidEmbeddingError(DomainValidationError):
    """El vector no tiene la dimensión esperada o contiene valores no válidos."""


class InvalidIngestionTransitionError(DomainError):
    """El cambio de estado del pipeline de ingesta no está permitido (HTTP 422)."""


class DocumentNotFoundError(ResourceNotFoundError):
    """El documento o el trabajo de ingesta no existe o pertenece a otro workspace (HTTP 404)."""
