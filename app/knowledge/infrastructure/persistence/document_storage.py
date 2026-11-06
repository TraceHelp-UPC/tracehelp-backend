"""Almacenamiento de archivos de manuales en PostgreSQL (tabla kb_document_files).

Ubicación devuelta: db://kb_document_files/<uuid>. Si más adelante se usa almacenamiento de objetos,
basta con otra implementación de IDocumentStorage con su propio esquema de URI.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.knowledge.application.ports import IDocumentStorage
from app.knowledge.domain.exceptions import DocumentNotFoundError
from app.knowledge.infrastructure.persistence.models import KbDocumentFileModel

URI_PREFIX = "db://kb_document_files/"


class DatabaseDocumentStorage(IDocumentStorage):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, *, file_name: str, mime_type: str, content: bytes) -> str:
        model = KbDocumentFileModel(
            id=uuid.uuid4(), file_name=file_name, mime_type=mime_type, size_bytes=len(content), content=content
        )
        self._session.add(model)
        self._session.flush()
        return f"{URI_PREFIX}{model.id}"

    def load(self, storage_uri: str) -> bytes:
        if not storage_uri.startswith(URI_PREFIX):
            raise DocumentNotFoundError(f"Ubicación de archivo no soportada: {storage_uri}")
        try:
            file_id = uuid.UUID(storage_uri.removeprefix(URI_PREFIX))
        except ValueError as exc:
            raise DocumentNotFoundError("La ubicación del archivo no es válida.") from exc
        # Seleccionar la columna directamente evita cargar la fila completa del modelo
        content = self._session.scalar(select(KbDocumentFileModel.content).where(KbDocumentFileModel.id == file_id))
        if content is None:
            raise DocumentNotFoundError("El archivo del documento ya no está disponible.")
        return content
