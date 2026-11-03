"""Value objects del contexto Helpdesk."""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.helpdesk.domain.exceptions import InvalidVisualEvidenceError

ALLOWED_IMAGE_TYPES = frozenset({"image/png", "image/jpeg"})
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024  # 10 MB


@dataclass(frozen=True)
class VisualEvidence:
    """Captura de pantalla del error adjunta al ticket (US10). Solo PNG/JPG de hasta 10 MB."""

    file_name: str
    mime_type: str
    content: bytes = field(repr=False)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    uploaded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if self.mime_type not in ALLOWED_IMAGE_TYPES:
            raise InvalidVisualEvidenceError(
                f"Formato de imagen no permitido: {self.mime_type}. Solo se aceptan PNG o JPG."
            )
        if not self.content:
            raise InvalidVisualEvidenceError("La imagen adjunta está vacía.")
        if len(self.content) > MAX_EVIDENCE_BYTES:
            raise InvalidVisualEvidenceError("La imagen supera el tamaño máximo permitido de 10 MB.")
        if not self.file_name or not self.file_name.strip():
            raise InvalidVisualEvidenceError("La imagen debe tener un nombre de archivo.")

    @property
    def size_bytes(self) -> int:
        return len(self.content)
