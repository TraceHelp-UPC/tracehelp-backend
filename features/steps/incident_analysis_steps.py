"""Steps de la feature de análisis multimodal y triaje automático (T29, TS02).

Gemini se simula con un generador falso y los vectores se calculan por palabras (como en las pruebas de
ingesta), así la búsqueda en pgvector es real pero ninguna llamada sale a la API de Google.
"""
import contextlib
import shutil
import uuid

from behave import given, then, when

from app.helpdesk.domain.enums import ImpactLevel
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.helpdesk.infrastructure.triage_routing import TriageRoutingHandler
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
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
from app.smart_triage.domain.events import TriageCompleted
from app.smart_triage.domain.grounding import GroundingThresholds
from app.smart_triage.infrastructure.helpdesk.helpdesk_ticket_reader import HelpdeskTicketReader
from app.smart_triage.infrastructure.knowledge.knowledge_context_retriever import KnowledgeContextRetriever
from app.smart_triage.infrastructure.ocr.tesseract_ocr_adapter import TesseractOcrAdapter
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)
from app.smart_triage.interfaces.rest.dependencies import get_triage_analysis_service
from tests.knowledge.test_ingestion_pipeline import MANUAL_MD, FakeEmbeddings, _pipeline, _upload, masker
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator
from tests.smart_triage.test_ocr_adapter import _screenshot

ANALYZE_URL = "/api/v1/triage/analyze"
# Con vectores por palabras las similitudes son más bajas que con Gemini; estos umbrales separan los casos
TEST_THRESHOLDS = GroundingThresholds(similarity=0.30, self_service=0.99)


def _headers(context, role: str) -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _analysis_service(context) -> TriageAnalysisService:
    retrieval = EvidenceRetrievalService(
        retriever=KnowledgeContextRetriever(
            KnowledgeRetrievalService(SqlAlchemyTechnicalDocumentRepository(context.session), FakeEmbeddings())
        ),
        masker=masker,
        events=context.triage_bus,
        thresholds=TEST_THRESHOLDS,
    )
    return TriageAnalysisService(
        ocr=TesseractOcrAdapter(),
        retrieval=retrieval,
        generation=DiagnosisGenerationService(generator=context.llm, masker=masker),
    )


# --- Preparación ---------------------------------------------------------------------------------------------

@given("the knowledge base of the workspace has the VPN troubleshooting guide")
def step_vpn_guide(context):
    """Sube e indexa guia-vpn.md con el mismo flujo de ingesta de T22/T23 (vectores por palabras)."""
    setup = {"workspace": context.workspace, "leader": context.users["IT_LEADER"], "bus": InMemoryEventBus()}
    document = _upload(context.session, setup, "guia-vpn.md", MANUAL_MD.encode())
    _pipeline(context.session, setup, FakeEmbeddings()).process(document.id)


@given("the language model is simulated")
def step_simulated_llm(context):
    context.llm = FakeGenerator()
    context.triage_bus = InMemoryEventBus()
    context.app.dependency_overrides[get_triage_analysis_service] = lambda: _analysis_service(context)


@given("the language model is unavailable")
def step_llm_down(context):
    context.llm = FakeGenerator(error=LlmProviderError("Gemini respondió 503: servicio no disponible"))


@given('the collaborator registered the ticket "{title}" with the description "{description}"')
def step_registered_ticket(context, title, description):
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title=title,
        description=description,
        impact_level=ImpactLevel.MEDIUM,
    )
    context.triage_ticket = SqlAlchemyTicketRepository(context.session).save(ticket)


# --- Acciones ------------------------------------------------------------------------------------------------

def _analyze(context, role: str, *, description=None, files=None, workspace_id="own") -> None:
    data = {}
    if workspace_id == "own":
        data["workspace_id"] = str(context.workspace.id)
    elif workspace_id is not None:
        data["workspace_id"] = workspace_id
    if description:
        data["description"] = description
    context.response = context.client.post(ANALYZE_URL, data=data, files=files, headers=_headers(context, role))


@when('the "{role}" analyzes the incident "{description}" with a screenshot of the error')
def step_analyze_with_screenshot(context, role, description):
    assert shutil.which("tesseract"), "Este escenario necesita Tesseract (corre dentro de Docker)."
    _analyze(context, role, description=description, files={"screenshot": ("error.png", _screenshot(), "image/png")})


@when('the "{role}" analyzes the incident "{description}" in a workspace that does not exist')
def step_analyze_unknown_workspace(context, role, description):
    _analyze(context, role, description=description, workspace_id=str(uuid.uuid4()))


@when('the "{role}" analyzes the incident "{description}"')
def step_analyze(context, role, description):
    _analyze(context, role, description=description)


@when('the "{role}" analyzes the incident ""')
def step_analyze_empty(context, role):
    _analyze(context, role)


@when('the "{role}" analyzes an incident without the workspace id')
def step_analyze_without_workspace(context, role):
    _analyze(context, role, description="La vpn me da el error 809", workspace_id=None)


@when("the automatic triage processes the ticket")
def step_automatic_triage(context):
    # Helpdesk escucha TriageCompleted y mueve el ticket, igual que en producción (pero en la sesión del escenario)
    context.triage_bus.subscribe(
        TriageCompleted,
        TriageRoutingHandler(session_factory=lambda: contextlib.nullcontext(context.session), events=context.triage_bus),
    )
    AutomaticTriageService(
        session=context.session,
        tickets=HelpdeskTicketReader(context.session),
        diagnoses=SqlAlchemyTriageDiagnosisRepository(context.session),
        analysis=_analysis_service(context),
        masker=masker,
        events=context.triage_bus,
    ).triage(context.triage_ticket.id)


# --- Verificaciones ------------------------------------------------------------------------------------------

@then('the analysis status is "{status}" with confidence level "{level}"')
def step_analysis_status(context, status, level):
    body = context.response.json()
    assert (body["status"], body["confidence_level"]) == (status, level), body


@then("the confidence score is above the similarity threshold")
def step_confidence(context):
    body = context.response.json()
    assert body["confidence_score"] >= body["similarity_threshold"], body


@then('the diagnosis cites "{citation}"')
def step_cites(context, citation):
    sources = [s["citation"] for s in context.response.json()["diagnosis"]["sources"]]
    assert citation in sources, sources


@then("every step of the diagnosis cites a source")
def step_steps_cited(context):
    steps = context.response.json()["diagnosis"]["steps"]
    assert steps and all("[F" in step for step in steps), steps


@then('the screenshot was read with the error codes "{codes}"')
def step_ocr_codes(context, codes):
    ocr = context.response.json()["ocr"]
    assert ocr["screenshot_received"] and ocr["legible"], ocr
    for code in codes.split(", "):
        assert code in ocr["error_codes"], ocr


@then('the language model did not receive "{text}"')
def step_llm_without(context, text):
    assert context.llm.prompts, "Se esperaba una llamada al modelo"
    prompt = context.llm.prompts[0].render(masker)
    assert text not in prompt


@then("the language model was not called")
def step_llm_not_called(context):
    assert context.llm.prompts == []


@then('the ticket "{title}" is in status "{status}"')
def step_ticket_status(context, title, status):
    context.session.expire_all()
    ticket = SqlAlchemyTicketRepository(context.session).find_by_id(context.triage_ticket.id)
    assert ticket.title == title and ticket.status.value == status, ticket.status


@then("the diagnosis of the ticket is waiting for an analyst review")
def step_diagnosis_pending(context):
    diagnosis = SqlAlchemyTriageDiagnosisRepository(context.session).find_by_ticket_id(context.triage_ticket.id)
    assert diagnosis.outcome.value == "ANSWERED" and diagnosis.review_status.value == "PENDING_REVIEW", diagnosis
    assert diagnosis.sources and diagnosis.sources[0].citation == "guia-vpn.md, sección «Error 809», párr. 1"


@then("the diagnosis of the ticket records that the AI was unavailable")
def step_diagnosis_failed(context):
    diagnosis = SqlAlchemyTriageDiagnosisRepository(context.session).find_by_ticket_id(context.triage_ticket.id)
    assert diagnosis.outcome.value == "PROVIDER_ERROR" and "503" in diagnosis.outcome_reason, diagnosis
