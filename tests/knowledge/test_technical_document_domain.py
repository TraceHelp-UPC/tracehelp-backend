"""Pruebas unitarias del agregado TechnicalDocument y sus value objects (T21, TS01)."""
import math
import uuid

import pytest

from app.knowledge.domain.enums import DocumentFormat, IngestionStatus
from app.knowledge.domain.events import (
    TechnicalDocumentIngestionFailed,
    TechnicalDocumentUploaded,
    TechnicalDocumentVectorized,
)
from app.knowledge.domain.exceptions import (
    FileSizeExceededError,
    InvalidDocumentDataError,
    InvalidEmbeddingError,
    InvalidIngestionTransitionError,
    UnsupportedDocumentFormatError,
)
from app.knowledge.domain.technical_document import KnowledgeChunk, TechnicalDocument
from app.knowledge.domain.value_objects import (
    EMBEDDING_DIMENSIONS,
    MAX_DOCUMENT_BYTES,
    CitationMetadata,
    DocumentFileMetadata,
    VectorEmbedding,
)

PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n"
MARKDOWN = "# Manual VPN\n\nPaso 1: abre el cliente.".encode()


def _document(file_name="Manual_VPN.pdf", content=PDF, title=None) -> TechnicalDocument:
    return TechnicalDocument.upload(
        workspace_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        file=DocumentFileMetadata.from_upload(file_name, content),
        storage_uri="db://kb_document_files/123",
        title=title,
    )


def _vector(seed: float = 1.0) -> VectorEmbedding:
    return VectorEmbedding.normalized([seed] + [0.5] * (EMBEDDING_DIMENSIONS - 1))


def _chunk(index: int, with_vector: bool = True) -> KnowledgeChunk:
    return KnowledgeChunk(
        chunk_index=index,
        content=f"Fragmento {index} del manual.",
        citation=CitationMetadata(source_file="Manual_VPN.pdf", page_number=1, paragraph_number=index + 1),
        embedding=_vector(index + 1) if with_vector else None,
    )


# ----------------------------------------------------------------------------- DocumentFileMetadata
@pytest.mark.parametrize(
    ("file_name", "content", "expected"),
    [
        ("Manual_VPN.pdf", PDF, DocumentFormat.PDF),
        ("MANUAL.PDF", PDF, DocumentFormat.PDF),
        ("guia.md", MARKDOWN, DocumentFormat.MARKDOWN),
        ("guia.markdown", MARKDOWN, DocumentFormat.MARKDOWN),
    ],
)
def test_accepts_pdf_and_markdown(file_name, content, expected):
    metadata = DocumentFileMetadata.from_upload(file_name, content)
    assert metadata.format is expected
    assert metadata.size_bytes == len(content)


@pytest.mark.parametrize("file_name", ["manual.docx", "manual.txt", "captura.png", "manual"])
def test_rejects_unsupported_extensions(file_name):
    with pytest.raises(UnsupportedDocumentFormatError):
        DocumentFileMetadata.from_upload(file_name, PDF)


def test_rejects_pdf_without_pdf_signature():
    with pytest.raises(UnsupportedDocumentFormatError):
        DocumentFileMetadata.from_upload("manual.pdf", b"esto no es un pdf")


def test_rejects_binary_markdown():
    with pytest.raises(UnsupportedDocumentFormatError):
        DocumentFileMetadata.from_upload("manual.md", b"\xff\xfe\x00\x01binario")


def test_rejects_empty_files():
    with pytest.raises(InvalidDocumentDataError):
        DocumentFileMetadata.from_upload("manual.pdf", b"")
    with pytest.raises(InvalidDocumentDataError):
        DocumentFileMetadata.from_upload("manual.md", b"   \n")


def test_rejects_files_over_25_mb():
    with pytest.raises(FileSizeExceededError):
        DocumentFileMetadata(file_name="enorme.pdf", format=DocumentFormat.PDF, size_bytes=MAX_DOCUMENT_BYTES + 1)


def test_file_name_keeps_only_the_base_name():
    assert DocumentFileMetadata.from_upload("C:/temp/../Manual.pdf", PDF).file_name == "Manual.pdf"


# ----------------------------------------------------------------------------- CitationMetadata y VectorEmbedding
def test_citation_label_for_pdf_and_markdown():
    pdf = CitationMetadata(source_file="Manual_AD_v2.pdf", page_number=14, paragraph_number=3)
    md = CitationMetadata(source_file="guia.md", paragraph_number=2, section_title="Reinstalar VPN")
    assert pdf.label == "Manual_AD_v2.pdf, pág. 14, párr. 3"
    assert md.label == "guia.md, sección «Reinstalar VPN», párr. 2"


@pytest.mark.parametrize("kwargs", [{"paragraph_number": 0}, {"paragraph_number": 1, "page_number": 0}])
def test_citation_requires_positive_positions(kwargs):
    with pytest.raises(InvalidDocumentDataError):
        CitationMetadata(source_file="Manual.pdf", **kwargs)


def test_embedding_is_normalized():
    vector = VectorEmbedding.normalized([3.0, 4.0] + [0.0] * (EMBEDDING_DIMENSIONS - 2))
    assert math.isclose(sum(v * v for v in vector.values), 1.0, rel_tol=1e-9)
    assert vector.values[:2] == (0.6, 0.8)


def test_embedding_requires_expected_dimensions_and_norm():
    with pytest.raises(InvalidEmbeddingError):
        VectorEmbedding.normalized([1.0] * 10)
    with pytest.raises(InvalidEmbeddingError):
        VectorEmbedding(tuple([1.0] * EMBEDDING_DIMENSIONS))
    with pytest.raises(InvalidEmbeddingError):
        VectorEmbedding.normalized([0.0] * EMBEDDING_DIMENSIONS)


# ----------------------------------------------------------------------------- TechnicalDocument
def test_upload_creates_pending_document_and_event():
    document = _document()
    assert document.status is IngestionStatus.PENDING
    assert document.title == "Manual_VPN"
    assert document.job_id != document.id
    events = document.pull_events()
    assert len(events) == 1 and isinstance(events[0], TechnicalDocumentUploaded)
    assert events[0].job_id == document.job_id


def test_upload_uses_custom_title():
    assert _document(title="  Guía de la VPN corporativa ").title == "Guía de la VPN corporativa"


def test_full_lifecycle_until_vectorized():
    document = _document()
    document.pull_events()
    document.start_processing()
    assert document.status is IngestionStatus.PROCESSING and document.processing_started_at is not None

    document.complete_vectorization([_chunk(1), _chunk(0)])

    assert document.status is IngestionStatus.VECTORIZED
    assert document.chunk_count == 2
    assert [c.chunk_index for c in document.chunks] == [0, 1]
    events = document.pull_events()
    assert isinstance(events[0], TechnicalDocumentVectorized) and events[0].chunk_count == 2


def test_cannot_vectorize_with_chunks_missing_vectors():
    document = _document()
    document.start_processing()
    with pytest.raises(InvalidDocumentDataError):
        document.complete_vectorization([_chunk(0), _chunk(1, with_vector=False)])
    assert document.status is IngestionStatus.PROCESSING


def test_cannot_vectorize_without_chunks():
    document = _document()
    document.start_processing()
    with pytest.raises(InvalidDocumentDataError):
        document.complete_vectorization([])


def test_cannot_vectorize_without_processing_first():
    with pytest.raises(InvalidIngestionTransitionError):
        _document().complete_vectorization([_chunk(0)])


def test_mark_failed_keeps_the_reason_and_emits_event():
    document = _document()
    document.pull_events()
    document.start_processing()
    document.mark_failed("El PDF está protegido con contraseña.")
    assert document.status is IngestionStatus.FAILED
    assert document.error_message == "El PDF está protegido con contraseña."
    assert isinstance(document.pull_events()[0], TechnicalDocumentIngestionFailed)


def test_failed_document_can_be_requeued():
    document = _document()
    document.start_processing()
    document.mark_failed("Gemini no respondió.")
    document.requeue()
    assert document.status is IngestionStatus.PENDING and document.error_message is None


@pytest.mark.parametrize("action", ["start_processing", "requeue"])
def test_vectorized_is_final(action):
    document = _document()
    document.start_processing()
    document.complete_vectorization([_chunk(0)])
    with pytest.raises(InvalidIngestionTransitionError):
        getattr(document, action)()


def test_chunk_requires_content():
    with pytest.raises(InvalidDocumentDataError):
        KnowledgeChunk(chunk_index=0, content="   ", citation=CitationMetadata(source_file="a.md", paragraph_number=1))
