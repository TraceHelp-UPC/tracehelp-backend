"""Value objects del contexto Smart Triage."""
import re
from dataclasses import dataclass, field

from app.smart_triage.domain.enums import ConfidenceLevel
from app.smart_triage.domain.exceptions import ILLEGIBLE_IMAGE_MESSAGE, InvalidConfidenceThresholdError

DEFAULT_MIN_EVIDENCE_THRESHOLD = 0.70
DEFAULT_SELF_SERVICE_THRESHOLD = 0.85

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


@dataclass(frozen=True)
class SimilarityThresholds:
    """Parámetros calibrados de decisión semántica RAG (US11, T33).

    - min_evidence_threshold (0.70): puntaje mínimo para permitir la síntesis generativa con citas.
    - self_service_threshold (0.85): puntaje mínimo para proponer autoservicio directo al colaborador.
    """

    min_evidence_threshold: float = DEFAULT_MIN_EVIDENCE_THRESHOLD
    self_service_threshold: float = DEFAULT_SELF_SERVICE_THRESHOLD

    def __post_init__(self) -> None:
        if not (0.0 <= self.min_evidence_threshold <= 1.0):
            raise InvalidConfidenceThresholdError("El umbral mínimo de evidencia debe estar entre 0.0 y 1.0.")
        if not (0.0 <= self.self_service_threshold <= 1.0):
            raise InvalidConfidenceThresholdError("El umbral de autoservicio debe estar entre 0.0 y 1.0.")
        if self.min_evidence_threshold > self.self_service_threshold:
            raise InvalidConfidenceThresholdError(
                "El umbral mínimo de evidencia no puede superar al umbral de autoservicio."
            )


@dataclass(frozen=True)
class ConfidenceScore:
    """Puntaje probabilístico de similitud coseno en [0.0, 1.0] (US11, QAS-04)."""

    value: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.value <= 1.0):
            raise InvalidConfidenceThresholdError("El puntaje de confianza debe estar entre 0.0 y 1.0.")
        object.__setattr__(self, "value", round(float(self.value), 4))

    def meets_minimum_evidence(
        self, thresholds: SimilarityThresholds = SimilarityThresholds()
    ) -> bool:
        return self.value >= thresholds.min_evidence_threshold

    def qualifies_for_self_service(
        self, thresholds: SimilarityThresholds = SimilarityThresholds()
    ) -> bool:
        return self.value >= thresholds.self_service_threshold

    def classify(
        self, thresholds: SimilarityThresholds = SimilarityThresholds()
    ) -> ConfidenceLevel:
        if self.value >= thresholds.self_service_threshold:
            return ConfidenceLevel.HIGH_SELF_SERVICE
        if self.value >= thresholds.min_evidence_threshold:
            return ConfidenceLevel.MEDIUM_ASSISTED
        return ConfidenceLevel.LOW_CONFIDENCE_ALERT


@dataclass(frozen=True)
class SourceCitation:
    """Referencia bibliográfica inmutable al manual, página y párrafo utilizado por RAG (US11, DRV-04)."""

    source_file: str
    page_number: int
    paragraph_number: int
    similarity_score: float = DEFAULT_MIN_EVIDENCE_THRESHOLD

    def __post_init__(self) -> None:
        cleaned_file = (self.source_file or "").strip()
        if not cleaned_file:
            raise InvalidConfidenceThresholdError("El nombre del archivo fuente es obligatorio en la cita.")
        if self.page_number < 1 or self.paragraph_number < 1:
            raise InvalidConfidenceThresholdError("El número de página y párrafo deben ser mayores o iguales a 1.")
        if not (0.0 <= self.similarity_score <= 1.0):
            raise InvalidConfidenceThresholdError("El puntaje de similitud de la cita debe estar entre 0.0 y 1.0.")
        object.__setattr__(self, "source_file", cleaned_file)
