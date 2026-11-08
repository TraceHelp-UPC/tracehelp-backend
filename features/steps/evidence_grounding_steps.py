"""Steps de la feature de fundamentación en evidencia y alerta de baja confianza (T34, US11)."""
from behave import given, then, when

from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.knowledge.application.knowledge_retrieval_service import KnowledgeRetrievalService
from app.knowledge.infrastructure.persistence.technical_document_repository import (
    SqlAlchemyTechnicalDocumentRepository,
)
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.evidence_retrieval_service import EvidenceRetrievalService
from app.smart_triage.domain.events import LowConfidenceAlertRaised
from app.smart_triage.domain.grounding import GroundingThresholds
from app.smart_triage.infrastructure.knowledge.knowledge_context_retriever import KnowledgeContextRetriever
from app.smart_triage.interfaces.rest.dependencies import (
    get_diagnosis_generation_service,
    get_evidence_retrieval_service,
)
from tests.knowledge.test_ingestion_pipeline import FakeEmbeddings, masker
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator

SEARCH_URL = "/api/v1/triage/evidence-search"
PREVIEW_URL = "/api/v1/triage/diagnosis-preview"
TEST_THRESHOLDS = GroundingThresholds(similarity=0.30, self_service=0.99)


def _headers(context, role: str) -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


@given("the evidence search and diagnosis preview services use simulated embeddings and LLM")
def step_simulated_evidence_and_preview(context):
    context.llm = FakeGenerator()
    context.triage_bus = InMemoryEventBus()
    context.low_confidence_alerts = []
    context.triage_bus.subscribe(LowConfidenceAlertRaised, context.low_confidence_alerts.append)

    retrieval = EvidenceRetrievalService(
        retriever=KnowledgeContextRetriever(
            KnowledgeRetrievalService(SqlAlchemyTechnicalDocumentRepository(context.session), FakeEmbeddings())
        ),
        masker=masker,
        events=context.triage_bus,
        thresholds=TEST_THRESHOLDS,
    )
    generation = DiagnosisGenerationService(generator=context.llm, masker=masker)
    context.app.dependency_overrides[get_evidence_retrieval_service] = lambda: retrieval
    context.app.dependency_overrides[get_diagnosis_generation_service] = lambda: generation


@when('the "{role}" searches the manuals for "{query}"')
def step_search_manuals(context, role, query):
    context.response = context.client.post(
        SEARCH_URL,
        json={"query": query},
        headers=_headers(context, role),
    )


@when('the "{role}" requests a diagnosis preview for "{incident}"')
def step_request_diagnosis_preview(context, role, incident):
    context.response = context.client.post(
        PREVIEW_URL,
        json={"incident": incident},
        headers=_headers(context, role),
    )


@then('the evidence search confidence level is "{level}"')
def step_evidence_confidence_level(context, level):
    body = context.response.json()
    assert body["confidence_level"] == level, body


@then('the top evidence fragment cites "{citation}" and supports the answer')
def step_top_fragment_citation(context, citation):
    fragments = context.response.json()["fragments"]
    assert fragments, "No se recuperaron fragmentos"
    top = fragments[0]
    assert top["citation"] == citation and top["supports_answer"] is True, top


@then("no low confidence alert was published")
def step_no_alert_published(context):
    assert context.low_confidence_alerts == [], context.low_confidence_alerts


@then("a low confidence alert was published for the workspace")
def step_alert_published(context):
    assert len(context.low_confidence_alerts) == 1, context.low_confidence_alerts
    assert context.low_confidence_alerts[0].workspace_id == context.workspace.id


@then('the preview status is "{status}"')
def step_preview_status(context, status):
    body = context.response.json()
    assert body["status"] == status, body
