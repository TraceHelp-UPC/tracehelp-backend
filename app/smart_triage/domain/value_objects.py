"""Value objects del contexto Smart Triage."""
import re
from dataclasses import dataclass, field

from app.smart_triage.domain.exceptions import ILLEGIBLE_IMAGE_MESSAGE

# Una captura es legible si el OCR reconoce al menos estas palabras con buena confianza
MIN_CONFIDENT_WORDS = 3
MIN_MEAN_CONFIDENCE = 55.0
CONFIDENT_WORD_THRESHOLD = 60.0

# Códigos de error frecuentes en capturas de soporte
_ERROR_CODE_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"\b0x[0-9A-Fa-f]{8}\b"),  # HRESULT de Windows: 0x80070005
    re.compile(r"\b[A-Z]{2,6}-\d{3,6}\b"),  # ORA-12541, ERR-404, SAP-1234
    re.compile(r"\bSQLSTATE\[?[0-9A-Z]{5}\]?"),
    re.compile(r"\b[A-Z][A-Za-z]+(?:Exception|Error)\b"),  # NullPointerException, AccessDeniedError
)
# "Error 809", "error code 1603", "Código de error: 5"
_NUMERIC_ERROR = re.compile(
    r"\b(?:error(?:\s+code)?|c[oó]digo(?:\s+de\s+error)?|code)\s*(?:n[°ºo]\.?\s*)?[:#]?\s*(\d{2,6})\b", re.I
)


def extract_error_codes(text: str) -> tuple[str, ...]:
    """Códigos de error encontrados en el texto, sin repetir y en el orden en que aparecen."""
    found: list[tuple[int, str]] = []
    for pattern in _ERROR_CODE_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if value.lower().startswith("0x"):
                value = "0x" + value[2:].upper()
            found.append((match.start(), value))
    for match in _NUMERIC_ERROR.finditer(text):
        found.append((match.start(), f"Error {match.group(1)}"))

    codes: list[str] = []
    for _, value in sorted(found):
        if value not in codes:
            codes.append(value)
    return tuple(codes)


@dataclass(frozen=True)
class OcrExtractionResult:
    """Texto y códigos de error extraídos de una captura de pantalla (US10)."""

    text: str
    mean_confidence: float
    confident_word_count: int
    error_codes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_text(cls, text: str, *, mean_confidence: float, confident_word_count: int) -> "OcrExtractionResult":
        text = re.sub(r"[ \t]+", " ", text or "")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return cls(
            text=text,
            mean_confidence=round(max(0.0, min(100.0, mean_confidence)), 1),
            confident_word_count=max(0, confident_word_count),
            error_codes=extract_error_codes(text),
        )

    @classmethod
    def empty(cls) -> "OcrExtractionResult":
        return cls(text="", mean_confidence=0.0, confident_word_count=0)

    @property
    def is_legible(self) -> bool:
        """False si la captura está borrosa o no tiene texto: se pide una mejor captura (US10, escenario 5)."""
        return self.confident_word_count >= MIN_CONFIDENT_WORDS and self.mean_confidence >= MIN_MEAN_CONFIDENCE

    @property
    def feedback_message(self) -> str | None:
        """Mensaje para el colaborador cuando la captura no se puede leer."""
        return None if self.is_legible else ILLEGIBLE_IMAGE_MESSAGE
