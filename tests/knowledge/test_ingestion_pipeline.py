"""Pruebas de integración del pipeline de ingesta (T23). Requieren TEST_DATABASE_URL.

Gemini se reemplaza por un generador falso que arma vectores por palabras compartidas: así la búsqueda por
similitud coseno de pgvector tiene resultados con sentido sin llamar a la API real.
"""
import contextlib
import hashlib
import re
import uuid

import pytest

from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel
from app.knowledge.application.document_ingestion_service import EMBEDDING_FAILURE, DocumentIngestionService
from app.knowledge.application.knowledge_command_service import (
    KnowledgeCommandService,
    UploadTechnicalDocumentCommand,
)
from app.knowledge.application.ports import EmbeddingProviderError, IEmbeddingGenerator
from app.knowledge.domain.enums import IngestionStatus
from app.knowledge.domain.events import TechnicalDocumentIngestionFailed, TechnicalDocumentVectorized
from app.knowledge.domain.value_objects import EMBEDDING_DIMENSIONS, VectorEmbedding
from app.knowledge.infrastructure.ingestion_worker import BackgroundIngestionWorker
from app.knowledge.infrastructure.parsing.pdf_markdown_parser import PdfMarkdownParserAdapter
from app.knowledge.infrastructure.persistence.document_storage import DatabaseDocumentStorage
from app.knowledge.infrastructure.persistence.models import KbKnowledgeChunkModel
from app.knowledge.infrastructure.persistence.technical_document_repository import (
    SqlAlchemyTechnicalDocumentRepository,
)
from app.shared.domain.pii import ensure_sealed
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.shared.infrastructure.pii_masker import RegexSpacyPiiMasker
from tests.conftest import FAKE_HASH
from tests.knowledge.test_document_parser import build_pdf

masker = RegexSpacyPiiMasker("clave-de-pruebas-del-sello-pii-0123456789", spacy_model=None)


def _bag_of_words(text: str) -> VectorEmbedding:
    values = [0.0] * EMBEDDING_DIMENSIONS
    for word in re.findall(r"\w+", text.lower()):
        values[int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_DIMENSIONS] += 1.0
    values[0] += 0.01  # evita vectores nulos
    return VectorEmbedding.normalized(values)


class FakeEmbeddings(IEmbeddingGenerator):
    def __init__(self, fail: bool = False) -> None:
        self.received: list[str] = []
        self._fail = fail

    def embed_documents(self, texts):
        plain = [ensure_sealed(t, masker) for t in texts]  # igual que el adaptador real
        self.received.extend(plain)
        if self._fail:
            raise EmbeddingProviderError("Gemini respondió 503")
        return [_bag_of_words(t) for t in plain]

    def embed_query(self, text):
        return _bag_of_words(ensure_sealed(text, masker))


MANUAL_MD = """# Guía de VPN corporativa

Para conectarte abre el cliente VPN e ingresa con tu cuenta de red.
Si tienes dudas escribe a soporte.vpn@empresa.pe.

## Error 809

El error 809 aparece cuando el firewall de casa bloquea los puertos UDP 500 y 4500.
Abre esos puertos en el router o conéctate desde otra red.

## Impresoras

Para instalar una impresora de red usa el portal de software y busca el modelo del piso.
"""


@pytest.fixture()
def setup(db_session, workspace_and_users):
    workspace, _, _ = workspace_and_users
    leader = UserModel(
        id=uuid.uuid4(), workspace_id=workspace.id, full_name="Líder Demo", email=f"lider-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH, role=RoleName.IT_LEADER, department="TI",
    )
    db_session.add(leader)
    db_session.flush()
    bus = InMemoryEventBus()
    received_events: list = []
    bus.subscribe(TechnicalDocumentVectorized, received_events.append)
    bus.subscribe(TechnicalDocumentIngestionFailed, received_events.append)
    return {"workspace": workspace, "leader": leader, "bus": bus, "events": received_events}


def _upload(db_session, setup, file_name: str, content: bytes):
    service = KnowledgeCommandService(
        session=db_session,
        documents=SqlAlchemyTechnicalDocumentRepository(db_session),
        storage=DatabaseDocumentStorage(db_session),
        events=setup["bus"],
    )
    return service.upload(
        UploadTechnicalDocumentCommand(
            workspace_id=setup["workspace"].id, uploaded_by=setup["leader"].id, file_name=file_name, content=content
        )
    )


def _pipeline(db_session, setup, embeddings: IEmbeddingGenerator) -> DocumentIngestionService:
    return DocumentIngestionService(
        session=db_session,
        documents=SqlAlchemyTechnicalDocumentRepository(db_session),
        storage=DatabaseDocumentStorage(db_session),
        parser=PdfMarkdownParserAdapter(),
        masker=masker,
        embeddings=embeddings,
        events=setup["bus"],
    )


def test_markdown_manual_is_vectorized_with_citations(db_session, setup):
    document = _upload(db_session, setup, "guia-vpn.md", MANUAL_MD.encode())
    result = _pipeline(db_session, setup, FakeEmbeddings()).process(document.id)

    assert result.status is IngestionStatus.VECTORIZED
    stored = SqlAlchemyTechnicalDocumentRepository(db_session).find_by_id(document.id, with_chunks=True)
    assert stored.status is IngestionStatus.VECTORIZED and stored.vectorized_at is not None
    assert stored.chunk_count == len(stored.chunks) == 3
    assert [c.citation.section_title for c in stored.chunks] == ["Guía de VPN corporativa", "Error 809", "Impresoras"]
    assert all(c.embedding.dimensions == 768 for c in stored.chunks)
    assert isinstance(setup["events"][-1], TechnicalDocumentVectorized)


def test_pdf_manual_keeps_page_numbers(db_session, setup):
    pdf = build_pdf([["Para conectar la VPN abre el cliente corporativo."], ["El error 809 indica puertos UDP bloqueados."]])
    document = _upload(db_session, setup, "Manual_VPN.pdf", pdf)
    _pipeline(db_session, setup, FakeEmbeddings()).process(document.id)

    chunks = SqlAlchemyTechnicalDocumentRepository(db_session).find_by_id(document.id, with_chunks=True).chunks
    assert [c.citation.label for c in chunks] == ["Manual_VPN.pdf, pág. 1, párr. 1", "Manual_VPN.pdf, pág. 2, párr. 1"]


def test_text_is_anonymized_before_embedding_but_stored_intact(db_session, setup):
    document = _upload(db_session, setup, "guia-vpn.md", MANUAL_MD.encode())
    embeddings = FakeEmbeddings()
    _pipeline(db_session, setup, embeddings).process(document.id)

    assert not any("soporte.vpn@empresa.pe" in text for text in embeddings.received)
    assert any("[REDACTED_EMAIL]" in text for text in embeddings.received)
    # El fragmento guardado conserva el texto original para mostrarlo en la cita al analista
    chunks = SqlAlchemyTechnicalDocumentRepository(db_session).find_by_id(document.id, with_chunks=True).chunks
    assert "soporte.vpn@empresa.pe" in chunks[0].content


def test_similarity_search_returns_the_relevant_section_first(db_session, setup):
    document = _upload(db_session, setup, "guia-vpn.md", MANUAL_MD.encode())
    _pipeline(db_session, setup, FakeEmbeddings()).process(document.id)

    query = FakeEmbeddings().embed_query(masker.mask("me sale el error 809 en la vpn, los puertos udp"))
    results = SqlAlchemyTechnicalDocumentRepository(db_session).search_similar_chunks(setup["workspace"].id, query, top_k=2)

    assert results[0].chunk.citation.section_title == "Error 809"
    assert results[0].document_title == "guia-vpn"
    assert 0 < results[1].score < results[0].score <= 1


def test_search_only_sees_the_own_workspace(db_session, setup):
    document = _upload(db_session, setup, "guia-vpn.md", MANUAL_MD.encode())
    _pipeline(db_session, setup, FakeEmbeddings()).process(document.id)
    query = FakeEmbeddings().embed_query(masker.mask("error 809"))
    assert SqlAlchemyTechnicalDocumentRepository(db_session).search_similar_chunks(uuid.uuid4(), query) == []


def test_unreadable_manual_ends_failed_with_a_reason(db_session, setup):
    document = _upload(db_session, setup, "solo-titulo.md", b"# Solo un titulo\n")
    result = _pipeline(db_session, setup, FakeEmbeddings()).process(document.id)

    assert result.status is IngestionStatus.FAILED
    assert result.error_message == "El Markdown no tiene texto que se pueda indexar."
    assert isinstance(setup["events"][-1], TechnicalDocumentIngestionFailed)


def test_embedding_failure_ends_failed_without_partial_chunks(db_session, setup):
    document = _upload(db_session, setup, "guia-vpn.md", MANUAL_MD.encode())
    result = _pipeline(db_session, setup, FakeEmbeddings(fail=True)).process(document.id)

    assert result.status is IngestionStatus.FAILED and result.error_message == EMBEDDING_FAILURE
    assert db_session.query(KbKnowledgeChunkModel).filter_by(document_id=document.id).count() == 0


def test_processing_is_idempotent(db_session, setup):
    document = _upload(db_session, setup, "guia-vpn.md", MANUAL_MD.encode())
    embeddings = FakeEmbeddings()
    _pipeline(db_session, setup, embeddings).process(document.id)
    calls = len(embeddings.received)
    again = _pipeline(db_session, setup, embeddings).process(document.id)

    assert again.status is IngestionStatus.VECTORIZED
    assert len(embeddings.received) == calls  # no se vuelve a vectorizar


def test_unknown_document_is_ignored(db_session, setup):
    assert _pipeline(db_session, setup, FakeEmbeddings()).process(uuid.uuid4()) is None


def test_worker_resumes_interrupted_ingestions(db_session, setup):
    pending = _upload(db_session, setup, "pendiente.md", MANUAL_MD.encode())
    interrupted = _upload(db_session, setup, "interrumpido.md", MANUAL_MD.encode())
    repo = SqlAlchemyTechnicalDocumentRepository(db_session)
    document = repo.find_by_id(interrupted.id)
    document.start_processing()
    repo.save(document)
    db_session.flush()

    processed: list[uuid.UUID] = []
    worker = BackgroundIngestionWorker(
        max_workers=1,
        session_factory=lambda: contextlib.nullcontext(db_session),
        service_factory=lambda session: type("S", (), {"process": lambda self, i: processed.append(i)})(),
    )
    assert worker.resume_pending() >= 2
    worker._executor.shutdown(wait=True)

    assert {pending.id, interrupted.id} <= set(processed)
    assert repo.find_by_id(interrupted.id).status is IngestionStatus.PENDING
