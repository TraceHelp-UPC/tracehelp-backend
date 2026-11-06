"""Puertos que la capa de aplicación de Knowledge Management necesita de la infraestructura."""
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.knowledge.domain.chunking import ExtractedParagraph
from app.knowledge.domain.enums import DocumentFormat
from app.knowledge.domain.value_objects import VectorEmbedding
from app.shared.domain.exceptions import DomainError
from app.shared.domain.pii import SanitizedText


class DocumentParsingError(DomainError):
    """No se pudo extraer el texto del manual (PDF protegido, escaneado o dañado). El mensaje se muestra al líder de TI."""


class EmbeddingProviderError(Exception):
    """El proveedor de embeddings no respondió o no está configurado."""


class EmbeddingProviderNotConfiguredError(EmbeddingProviderError):
    """Falta la clave del proveedor de embeddings (GEMINI_API_KEY)."""


class IDocumentParser(ABC):
    @abstractmethod
    def parse(self, content: bytes, document_format: DocumentFormat) -> list[ExtractedParagraph]:
        """Extrae los párrafos del manual con su número de página (PDF) o sección (Markdown)."""


class IEmbeddingGenerator(ABC):
    """Genera vectores normalizados de 768 dimensiones. Solo acepta texto anonimizado y sellado (T27)."""

    @abstractmethod
    def embed_documents(self, texts: Sequence[SanitizedText]) -> list[VectorEmbedding]:
        """Vectores de los fragmentos de un manual (tarea RETRIEVAL_DOCUMENT)."""

    @abstractmethod
    def embed_query(self, text: SanitizedText) -> VectorEmbedding:
        """Vector de la consulta de un ticket (tarea RETRIEVAL_QUERY), para la búsqueda de T30."""


class IDocumentStorage(ABC):
    """Almacenamiento del archivo original del manual."""

    @abstractmethod
    def save(self, *, file_name: str, mime_type: str, content: bytes) -> str:
        """Guarda el archivo y devuelve su ubicación (storage_uri)."""

    @abstractmethod
    def load(self, storage_uri: str) -> bytes:
        """Devuelve el contenido del archivo guardado."""
