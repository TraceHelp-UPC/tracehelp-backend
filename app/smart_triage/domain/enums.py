"""Enumeraciones del Bounded Context Smart Triage."""
from enum import StrEnum


class ConfidenceLevel(StrEnum):
    """Clasifica la certeza del diagnóstico frente a los umbrales configurados (US11, T33)."""

    HIGH_SELF_SERVICE = "HIGH_SELF_SERVICE"
    MEDIUM_ASSISTED = "MEDIUM_ASSISTED"
    LOW_CONFIDENCE_ALERT = "LOW_CONFIDENCE_ALERT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ValidationStatus(StrEnum):
    """Estados de revisión humana (HITL) de una recomendación generada (US15)."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"
    MANUAL_ONLY = "MANUAL_ONLY"
