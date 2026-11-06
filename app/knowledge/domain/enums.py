"""Enumeraciones del contexto Knowledge Management."""
from enum import StrEnum


class DocumentFormat(StrEnum):
    """Formatos de manual técnico que se pueden cargar (US06, TS01)."""

    PDF = "PDF"
    MARKDOWN = "MARKDOWN"


class IngestionStatus(StrEnum):
    """Estado del pipeline de ingesta. Las transiciones válidas están en TechnicalDocument."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    VECTORIZED = "VECTORIZED"
    FAILED = "FAILED"
