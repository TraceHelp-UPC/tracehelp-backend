"""Value objects del contexto Knowledge Management."""
import math
from dataclasses import dataclass
from pathlib import PurePath

from app.knowledge.domain.enums import DocumentFormat
from app.knowledge.domain.exceptions import (
    FileSizeExceededError,
    InvalidDocumentDataError,
    InvalidEmbeddingError,
    UnsupportedDocumentFormatError,
)

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024  # 25 MB
MAX_FILE_NAME_LENGTH = 255
# Decisión del equipo: gemini-embedding-001 con output_dimensionality=768 (columna vector(768) en pgvector)
EMBEDDING_DIMENSIONS = 768

_EXTENSIONS = {
    ".pdf": DocumentFormat.PDF,
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
}
_MIME_TYPES = {DocumentFormat.PDF: "application/pdf", DocumentFormat.MARKDOWN: "text/markdown"}
PDF_SIGNATURE = b"%PDF-"


@dataclass(frozen=True)
class DocumentFileMetadata:
    """Nombre, formato y peso del manual cargado. Solo acepta PDF o Markdown de hasta 25 MB (US06, TS01)."""

    file_name: str
    format: DocumentFormat
    size_bytes: int

    def __post_init__(self) -> None:
        if not self.file_name or not self.file_name.strip():
            raise InvalidDocumentDataError("El archivo debe tener un nombre.")
        if len(self.file_name) > MAX_FILE_NAME_LENGTH:
            raise InvalidDocumentDataError(f"El nombre del archivo no puede superar los {MAX_FILE_NAME_LENGTH} caracteres.")
        if self.size_bytes <= 0:
            raise InvalidDocumentDataError("El archivo está vacío.")
        if self.size_bytes > MAX_DOCUMENT_BYTES:
            raise FileSizeExceededError("El archivo supera el tamaño máximo permitido de 25 MB.")

    @classmethod
    def from_upload(cls, file_name: str, content: bytes) -> "DocumentFileMetadata":
        """Valida el archivo recibido: extensión permitida, tamaño y que el contenido corresponda al formato."""
        name = PurePath((file_name or "").strip()).name
        document_format = _EXTENSIONS.get(PurePath(name).suffix.lower())
        if document_format is None:
            raise UnsupportedDocumentFormatError(
                f"Formato no soportado en '{name or 'archivo sin nombre'}'. Solo se aceptan manuales PDF (.pdf) o Markdown (.md)."
            )
        metadata = cls(file_name=name, format=document_format, size_bytes=len(content or b""))
        metadata._ensure_content_matches(content)
        return metadata

    def _ensure_content_matches(self, content: bytes) -> None:
        # La especificación PDF permite bytes previos a la firma dentro del primer kilobyte
        if self.format is DocumentFormat.PDF and PDF_SIGNATURE not in content[:1024]:
            raise UnsupportedDocumentFormatError(f"El archivo '{self.file_name}' no es un PDF válido.")
        if self.format is DocumentFormat.MARKDOWN:
            try:
                text = content.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise UnsupportedDocumentFormatError(
                    f"El archivo '{self.file_name}' no es un Markdown de texto en UTF-8."
                ) from exc
            if "\x00" in text:
                raise UnsupportedDocumentFormatError(f"El archivo '{self.file_name}' no es un Markdown de texto.")
            if not text.strip():
                raise InvalidDocumentDataError("El archivo está vacío.")

    @property
    def mime_type(self) -> str:
        return _MIME_TYPES[self.format]

    @property
    def stem(self) -> str:
        return PurePath(self.file_name).stem


@dataclass(frozen=True)
class CitationMetadata:
    """Ubicación exacta de un fragmento en el manual: archivo, página y párrafo (US11, DRV-04).

    page_number es None en los archivos Markdown, que no tienen páginas; en ese caso section_title indica la sección.
    """

    source_file: str
    paragraph_number: int
    page_number: int | None = None
    section_title: str | None = None

    def __post_init__(self) -> None:
        if not self.source_file or not self.source_file.strip():
            raise InvalidDocumentDataError("La cita debe indicar el archivo de origen.")
        if self.paragraph_number < 1:
            raise InvalidDocumentDataError("El número de párrafo debe ser mayor que cero.")
        if self.page_number is not None and self.page_number < 1:
            raise InvalidDocumentDataError("El número de página debe ser mayor que cero.")

    @property
    def label(self) -> str:
        """Texto de la cita, por ejemplo: Manual_AD_v2.pdf, pág. 14, párr. 3."""
        parts = [self.source_file]
        if self.page_number is not None:
            parts.append(f"pág. {self.page_number}")
        elif self.section_title:
            parts.append(f"sección «{self.section_title}»")
        parts.append(f"párr. {self.paragraph_number}")
        return ", ".join(parts)


@dataclass(frozen=True)
class VectorEmbedding:
    """Vector normalizado de un fragmento (norma 1), listo para similitud coseno en pgvector."""

    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.values) != EMBEDDING_DIMENSIONS:
            raise InvalidEmbeddingError(
                f"El vector debe tener {EMBEDDING_DIMENSIONS} dimensiones y tiene {len(self.values)}."
            )
        if not all(math.isfinite(v) for v in self.values):
            raise InvalidEmbeddingError("El vector contiene valores no numéricos.")
        if not math.isclose(self._norm(self.values), 1.0, abs_tol=1e-3):
            raise InvalidEmbeddingError("El vector debe estar normalizado; usa VectorEmbedding.normalized().")

    @staticmethod
    def _norm(values) -> float:
        return math.sqrt(sum(v * v for v in values))

    @classmethod
    def normalized(cls, values) -> "VectorEmbedding":
        """Crea el vector dividiendo cada valor entre la norma (gemini-embedding-001 no normaliza con 768 dimensiones)."""
        values = [float(v) for v in values]
        norm = cls._norm(values)
        if norm == 0 or not math.isfinite(norm):
            raise InvalidEmbeddingError("No se puede normalizar un vector nulo.")
        return cls(tuple(v / norm for v in values))

    @property
    def dimensions(self) -> int:
        return len(self.values)
