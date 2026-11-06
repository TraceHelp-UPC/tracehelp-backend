"""Anonimización de datos personales antes de cualquier llamada a Gemini (T27, CON03, DRV-02).

Regla del equipo: ningún texto sale hacia Gemini sin pasar antes por el módulo PII, incluido el texto que se
convierte en embedding. Para que la regla se cumpla por diseño, los adaptadores de Gemini reciben SanitizedText
(no str) y llaman a ensure_sealed() antes de enviar: si el texto no trae un sello HMAC válido, se rechaza.

Está en el shared kernel porque lo usan Knowledge Management (vectorización de manuales, T23) y
Smart Triage (prompt fundamentado, T31).
"""
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from app.shared.domain.exceptions import DomainError


class PiiCategory(StrEnum):
    CREDENTIAL = "CREDENTIAL"
    TOKEN = "TOKEN"
    EMAIL = "EMAIL"
    IP_ADDRESS = "IP_ADDRESS"
    DNI = "DNI"
    PHONE = "PHONE"
    USERNAME = "USERNAME"
    PERSON = "PERSON"


# Etiquetas neutras que reemplazan el dato sensible
PLACEHOLDERS: Mapping[PiiCategory, str] = MappingProxyType(
    {
        PiiCategory.CREDENTIAL: "[REDACTED_CREDENTIAL]",
        PiiCategory.TOKEN: "[REDACTED_TOKEN]",
        PiiCategory.EMAIL: "[REDACTED_EMAIL]",
        PiiCategory.IP_ADDRESS: "[REDACTED_IP]",
        PiiCategory.DNI: "[REDACTED_DNI]",
        PiiCategory.PHONE: "[REDACTED_PHONE]",
        PiiCategory.USERNAME: "[REDACTED_USER]",
        PiiCategory.PERSON: "[REDACTED_PERSON]",
    }
)


class UnsealedTextError(DomainError):
    """Se intentó enviar a un servicio externo un texto sin sello de anonimización válido."""


@dataclass(frozen=True)
class SanitizedText:
    """Texto ya anonimizado con su sello de auditoría.

    No guarda los valores originales: solo cuántos datos de cada tipo se ocultaron.
    """

    text: str
    audit_seal: str
    redactions: Mapping[PiiCategory, int] = field(default_factory=dict)

    @property
    def redaction_count(self) -> int:
        return sum(self.redactions.values())

    @property
    def had_sensitive_data(self) -> bool:
        return self.redaction_count > 0


class IPiiMasker(ABC):
    """Puerto de anonimización. La implementación usa expresiones regulares y spaCy (NER)."""

    @abstractmethod
    def mask(self, text: str) -> SanitizedText:
        """Oculta credenciales, tokens, correos, IP, DNI, teléfonos, usuarios y nombres de personas."""

    def mask_many(self, texts: Sequence[str]) -> list[SanitizedText]:
        """Anonimiza varios textos (por ejemplo, los fragmentos de un manual)."""
        return [self.mask(t) for t in texts]

    @abstractmethod
    def verify(self, sanitized: SanitizedText) -> bool:
        """True si el sello corresponde exactamente a ese texto anonimizado."""


def ensure_sealed(sanitized: SanitizedText, masker: IPiiMasker) -> str:
    """Devuelve el texto listo para enviar a Gemini o lanza UnsealedTextError si el sello no es válido."""
    if not isinstance(sanitized, SanitizedText) or not masker.verify(sanitized):
        raise UnsealedTextError("El texto no pasó por el módulo de anonimización; no se puede enviar a la IA.")
    return sanitized.text
