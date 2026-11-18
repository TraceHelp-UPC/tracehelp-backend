"""Pruebas de integración del triaje automático (T28). Requieren TEST_DATABASE_URL.

Recorren el flujo real: ticket guardado en Helpdesk, búsqueda en pgvector, diagnóstico guardado en
triage_diagnoses y Helpdesk moviendo el ticket al recibir TriageCompleted. Gemini y el OCR se simulan.
"""
import contextlib
import uuid

import pytest

from app.helpdesk.domain.enums import ImpactLevel, TicketStatus
from app.helpdesk.domain.events import TicketRegistered, TicketStatusChanged
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.domain.value_objects import VisualEvidence
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.helpdesk.infrastructure.triage_routing import TriageRoutingHandler
from app.knowledge.application.knowledge_retrieval_service import KnowledgeRetrievalService
from app.knowledge.infrastructure.persistence.technical_document_repository import (
    SqlAlchemyTechnicalDocumentRepository,
)
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.automatic_triage_service import AutomaticTriageService
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.evidence_retrieval_service import EvidenceRetrievalService
from app.smart_triage.application.ports import LlmProviderError
from app.smart_triage.application.triage_analysis_service import TriageAnalysisService
from app.smart_triage.domain.diagnosis import DiagnosisStatus
from app.smart_triage.domain.events import TriageCompleted
from app.smart_triage.domain.grounding import GroundingThresholds
from app.smart_triage.domain.triage_diagnosis import ReviewStatus
from app.smart_triage.infrastructure.helpdesk.helpdesk_ticket_reader import HelpdeskTicketReader
from app.smart_triage.infrastructure.knowledge.knowledge_context_retriever import KnowledgeContextRetriever
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)
from app.smart_triage.infrastructure.triage_worker import BackgroundTriageWorker
from tests.helpdesk.test_ticket_query_api import _png
from tests.knowledge.test_ingestion_pipeline import FakeEmbeddings, masker
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator
from tests.smart_triage.test_evidence_search_api import kb  # noqa: F401 - fixture reutilizada
from tests.smart_triage.test_triage_analysis_service import LEGIBLE, FakeOcr

GROUNDED_ONLY = GroundingThresholds(0.30, 0.99)  # con vectores por palabras: evidencia media, nunca autoservicio
SELF_SERVICE = GroundingThresholds(0.30, 0.31)  # cualquier evidencia suficiente es autoservicio


@pytest.fixture()
def triage(db_session, kb):  # noqa: F811
    bus = InMemoryEventBus()
    changes: list = []
    completed: list = []
    bus.subscribe(TicketStatusChanged, changes.append)
    bus.subscribe(TriageCompleted, completed.append)
    bus.subscribe(TriageCompleted, TriageRoutingHandler(session_factory=lambda: contextlib.nullcontext(db_session), events=bus))

    def build(thresholds=GROUNDED_ONLY, generator=None, ocr=None):
        generator = generator or FakeGenerator()
        retrieval = EvidenceRetrievalService(
            retriever=KnowledgeContextRetriever(
                KnowledgeRetrievalService(SqlAlchemyTechnicalDocumentRepository(db_session), FakeEmbeddings())
            ),
            masker=masker,
            events=bus,
            thresholds=thresholds,
        )
        service = AutomaticTriageService(
            session=db_session,
            tickets=HelpdeskTicketReader(db_session),
            diagnoses=SqlAlchemyTriageDiagnosisRepository(db_session),
            analysis=TriageAnalysisService(
                ocr=ocr or FakeOcr(), retrieval=retrieval, generation=DiagnosisGenerationService(generator=generator, masker=masker)
            ),
            masker=masker,
            events=bus,
        )
        return service, generator

    def ticket(title, description, *, screenshots=0, status=TicketStatus.OPEN):
        from app.iam.infrastructure.persistence.models import UserModel

        reporter = db_session.query(UserModel).filter_by(workspace_id=kb["workspace"].id, role="COLLABORATOR").first()
        created = Ticket.register(
            workspace_id=kb["workspace"].id,
            reporter_id=reporter.id,
            title=title,
            description=description,
            impact_level=ImpactLevel.MEDIUM,
            evidences=[VisualEvidence(file_name="error.png", mime_type="image/png", content=_png()) for _ in range(screenshots)],
        )
        created.status = status
        return SqlAlchemyTicketRepository(db_session).save(created)

    return {"build": build, "ticket": ticket, "changes": changes, "completed": completed, "db": db_session}


def _status(db_session, ticket_id):
    db_session.expire_all()
    return SqlAlchemyTicketRepository(db_session).find_by_id(ticket_id).status


def test_answered_with_medium_evidence_waits_for_an_analyst(triage):
    ticket = triage["ticket"]("VPN", "Me sale el error 809 en la vpn, los puertos udp 500 y 4500")
    service, _ = triage["build"]()

    diagnosis = service.triage(ticket.id)

    assert diagnosis.outcome is DiagnosisStatus.ANSWERED
    assert diagnosis.review_status is ReviewStatus.PENDING_REVIEW
    assert _status(triage["db"], ticket.id) is TicketStatus.PENDING_ASSIGNMENT
    [change] = triage["changes"]
    assert change.changed_by is None and "validación de un analista" in change.reason

    stored = SqlAlchemyTriageDiagnosisRepository(triage["db"]).find_by_ticket_id(ticket.id)
    assert stored.summary and stored.steps and stored.model == "modelo-falso"
    assert stored.sources[0].reference == "F1"
    assert stored.sources[0].citation == "guia-vpn.md, sección «Error 809», párr. 1"


def test_strong_evidence_is_proposed_to_the_collaborator(triage):
    ticket = triage["ticket"]("VPN", "Me sale el error 809 en la vpn, los puertos udp 500 y 4500")
    service, _ = triage["build"](thresholds=SELF_SERVICE)
    diagnosis = service.triage(ticket.id)
    assert diagnosis.review_status is ReviewStatus.SELF_SERVICE_PROPOSED
    assert _status(triage["db"], ticket.id) is TicketStatus.SELF_SERVICE_PROPOSED


def test_unrelated_incidents_go_to_the_queue_without_calling_the_model(triage):
    ticket = triage["ticket"]("Silla", "La silla ergonómica de mi escritorio rechina mucho")
    service, generator = triage["build"]()
    diagnosis = service.triage(ticket.id)
    assert diagnosis.outcome is DiagnosisStatus.INSUFFICIENT_EVIDENCE and generator.prompts == []
    assert diagnosis.review_status is ReviewStatus.NOT_APPLICABLE
    assert _status(triage["db"], ticket.id) is TicketStatus.PENDING_ASSIGNMENT


def test_provider_errors_never_leave_the_ticket_untriaged(triage):
    ticket = triage["ticket"]("VPN", "Me sale el error 809 en la vpn, los puertos udp 500 y 4500")
    service, _ = triage["build"](generator=FakeGenerator(error=LlmProviderError("Gemini respondió 503")))
    diagnosis = service.triage(ticket.id)
    assert diagnosis.outcome is DiagnosisStatus.PROVIDER_ERROR and "503" in diagnosis.outcome_reason
    assert _status(triage["db"], ticket.id) is TicketStatus.PENDING_ASSIGNMENT
    assert "no estuvo disponible" in triage["changes"][0].reason


def test_screenshot_text_is_stored_anonymized(triage):
    ticket = triage["ticket"]("VPN", "No puedo conectarme a la red de la empresa", screenshots=1)
    leaky = LEGIBLE.__class__.from_text(
        "VPN Error 809: escribe a soporte.vpn@empresa.pe", mean_confidence=90, confident_word_count=8
    )
    service, _ = triage["build"](ocr=FakeOcr(leaky))
    service.triage(ticket.id)
    stored = SqlAlchemyTriageDiagnosisRepository(triage["db"]).find_by_ticket_id(ticket.id)
    assert stored.ocr.legible and stored.ocr.error_codes == ("Error 809",)
    assert "soporte.vpn@empresa.pe" not in stored.ocr.masked_text


def test_each_ticket_is_triaged_only_once(triage):
    ticket = triage["ticket"]("VPN", "Me sale el error 809 en la vpn, los puertos udp 500 y 4500")
    service, _ = triage["build"]()
    assert service.triage(ticket.id) is not None
    assert service.triage(ticket.id) is None
    assert len(triage["completed"]) == 1


def test_a_ticket_moved_by_an_analyst_is_not_moved_again(triage):
    ticket = triage["ticket"]("VPN", "Me sale el error 809 en la vpn, los puertos udp 500 y 4500")
    service, _ = triage["build"]()
    ticket.status = TicketStatus.PENDING_ASSIGNMENT  # un analista lo pasó a la cola antes de que termine el triaje
    SqlAlchemyTicketRepository(triage["db"]).save(ticket)
    service.triage(ticket.id)
    assert triage["changes"] == []
    assert SqlAlchemyTriageDiagnosisRepository(triage["db"]).find_by_ticket_id(ticket.id) is not None


def test_unknown_tickets_are_ignored(triage):
    service, _ = triage["build"]()
    assert service.triage(uuid.uuid4()) is None


def test_pending_tickets_are_found_for_resumption(triage):
    pending = triage["ticket"]("VPN", "Me sale el error 809 en la vpn")
    triage["ticket"]("Ya en cola", "Ticket que ya pasó el triaje", status=TicketStatus.PENDING_ASSIGNMENT)
    done = triage["ticket"]("VPN 2", "Me sale el error 809 en la vpn, los puertos udp")
    triage["build"]()[0].triage(done.id)
    assert HelpdeskTicketReader(triage["db"]).find_untriaged_open_ticket_ids() == [pending.id]


def test_worker_triages_registered_tickets_and_resumes_pending_ones(triage):
    pending = triage["ticket"]("VPN", "Me sale el error 809 en la vpn")
    processed: list = []

    class RecordingService:
        def triage(self, ticket_id):
            processed.append(ticket_id)

    worker = BackgroundTriageWorker(
        max_workers=1,
        session_factory=lambda: contextlib.nullcontext(triage["db"]),
        service_factory=lambda session: RecordingService(),
    )
    registered = uuid.uuid4()
    worker.on_ticket_registered(
        TicketRegistered(ticket_id=registered, workspace_id=uuid.uuid4(), reporter_id=uuid.uuid4(), has_evidence=False)
    )
    assert worker.resume_pending() == 1
    worker._executor.shutdown(wait=True)  # espera a que el hilo termine los dos triajes encolados
    assert processed == [registered, pending.id]
