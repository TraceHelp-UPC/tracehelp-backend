"""Pruebas de integración de la recuperación de evidencia con pgvector y del endpoint (T30).

Requieren TEST_DATABASE_URL. Gemini se reemplaza por el generador de vectores por palabras de las pruebas de
ingesta, así la similitud coseno de pgvector tiene resultados con sentido sin llamar a la API real.
"""
import uuid

import pytest

from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel
from app.knowledge.application.knowledge_retrieval_service import KnowledgeRetrievalService
from app.knowledge.infrastructure.persistence.technical_document_repository import (
    SqlAlchemyTechnicalDocumentRepository,
)
from app.main import app
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.evidence_retrieval_service import EvidenceRetrievalService, RetrieveEvidenceCommand
from app.smart_triage.domain.events import LowConfidenceAlertRaised
from app.smart_triage.domain.grounding import ConfidenceLevel, GroundingThresholds
from app.smart_triage.infrastructure.knowledge.knowledge_context_retriever import KnowledgeContextRetriever
from app.smart_triage.interfaces.rest.dependencies import get_evidence_retrieval_service
from tests.conftest import FAKE_HASH
from tests.knowledge.test_ingestion_pipeline import MANUAL_MD, FakeEmbeddings, _pipeline, _upload, masker

URL = "/api/v1/triage/evidence-search"
# Los vectores por palabras dan similitudes más bajas que Gemini; estos umbrales separan bien los casos de prueba
TEST_THRESHOLDS = GroundingThresholds(similarity=0.30, self_service=0.60)


class RecordingEmbeddings(FakeEmbeddings):
    def __init__(self) -> None:
        super().__init__()
        self.queries: list[str] = []

    def embed_query(self, text):
        from app.shared.domain.pii import ensure_sealed

        self.queries.append(ensure_sealed(text, masker))
        return super().embed_query(text)


@pytest.fixture()
def kb(db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    leader = UserModel(
        id=uuid.uuid4(), workspace_id=workspace.id, full_name="Líder Demo", email=f"lider-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH, role=RoleName.IT_LEADER, department="TI",
    )
    db_session.add(leader)
    db_session.flush()
    setup = {"workspace": workspace, "leader": leader, "bus": InMemoryEventBus(), "events": []}
    document = _upload(db_session, setup, "guia-vpn.md", MANUAL_MD.encode())
    _pipeline(db_session, setup, FakeEmbeddings()).process(document.id)

    bus = InMemoryEventBus()
    alerts: list = []
    bus.subscribe(LowConfidenceAlertRaised, alerts.append)
    embeddings = RecordingEmbeddings()
    service = EvidenceRetrievalService(
        retriever=KnowledgeContextRetriever(
            KnowledgeRetrievalService(SqlAlchemyTechnicalDocumentRepository(db_session), embeddings)
        ),
        masker=masker,
        events=bus,
        thresholds=TEST_THRESHOLDS,
        top_k=3,
    )
    return {
        "workspace": workspace,
        "service": service,
        "embeddings": embeddings,
        "alerts": alerts,
        "headers": {
            "analyst": auth_headers(db_session, analyst),
            "leader": auth_headers(db_session, leader),
            "collaborator": auth_headers(db_session, collaborator),
        },
    }


@pytest.fixture()
def client_with_fake_gemini(api_client, kb):
    app.dependency_overrides[get_evidence_retrieval_service] = lambda: kb["service"]
    yield api_client
    app.dependency_overrides.pop(get_evidence_retrieval_service, None)


def test_relevant_section_is_retrieved_first_with_its_citation(kb):
    result = kb["service"].retrieve_and_evaluate(
        RetrieveEvidenceCommand(kb["workspace"].id, "me sale el error 809 en la vpn, los puertos udp 500 y 4500")
    )
    best = result.retrieved[0]
    assert best.citation.section_title == "Error 809"
    assert best.citation.label == "guia-vpn.md, sección «Error 809», párr. 1"
    assert "puertos UDP 500 y 4500" in best.content
    assert result.is_grounded and kb["alerts"] == []


def test_unrelated_question_raises_a_low_confidence_alert(kb):
    ticket_id = uuid.uuid4()
    result = kb["service"].retrieve_and_evaluate(
        RetrieveEvidenceCommand(kb["workspace"].id, "la silla ergonómica rechina mucho", ticket_id=ticket_id)
    )
    assert result.level is ConfidenceLevel.LOW_CONFIDENCE and result.supporting == ()
    assert [a.ticket_id for a in kb["alerts"]] == [ticket_id]


def test_other_workspaces_have_no_evidence(kb):
    result = kb["service"].retrieve_and_evaluate(RetrieveEvidenceCommand(uuid.uuid4(), "error 809 vpn"))
    assert result.retrieved == () and result.level is ConfidenceLevel.LOW_CONFIDENCE


def test_endpoint_returns_the_evaluation(client_with_fake_gemini, kb):
    response = client_with_fake_gemini.post(
        URL, json={"query": "error 809 vpn puertos udp, escríbeme a ana.diaz@empresa.pe"}, headers=kb["headers"]["analyst"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["confidence_level"] in {"GROUNDED", "SELF_SERVICE"}
    assert (body["similarity_threshold"], body["self_service_threshold"]) == (0.30, 0.60)
    assert len(body["fragments"]) == 3
    first = body["fragments"][0]
    assert first["section_title"] == "Error 809" and first["supports_answer"] is True
    assert first["similarity"] == body["best_score"]
    assert not any("ana.diaz@empresa.pe" in q for q in kb["embeddings"].queries)


def test_endpoint_reports_low_confidence(client_with_fake_gemini, kb):
    body = client_with_fake_gemini.post(URL, json={"query": "la silla rechina"}, headers=kb["headers"]["leader"]).json()
    assert body["confidence_level"] == "LOW_CONFIDENCE" and body["low_confidence_alert"] is True
    assert all(not f["supports_answer"] for f in body["fragments"])


def test_collaborators_cannot_search_the_manuals(client_with_fake_gemini, kb):
    response = client_with_fake_gemini.post(URL, json={"query": "vpn"}, headers=kb["headers"]["collaborator"])
    assert response.status_code == 403


@pytest.mark.parametrize(("payload", "status"), [({"query": "   "}, 400), ({"query": ""}, 422), ({"query": "vpn", "top_k": 50}, 422)])
def test_invalid_queries_are_rejected(client_with_fake_gemini, kb, payload, status):
    assert client_with_fake_gemini.post(URL, json=payload, headers=kb["headers"]["analyst"]).status_code == status


def test_missing_gemini_key_returns_503(api_client, kb, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "gemini_api_key", "")
    response = api_client.post(URL, json={"query": "error 809"}, headers=kb["headers"]["analyst"])
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]
