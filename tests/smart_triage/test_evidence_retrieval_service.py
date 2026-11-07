"""Pruebas unitarias de EvidenceRetrievalService con dobles (T30). No usan base de datos ni Gemini."""
import logging
import uuid

import pytest

from app.shared.domain.pii import SanitizedText
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.shared.infrastructure.pii_masker import RegexSpacyPiiMasker
from app.smart_triage.application.evidence_retrieval_service import (
    MAX_QUERY_CHARACTERS,
    EvidenceRetrievalService,
    RetrieveEvidenceCommand,
)
from app.smart_triage.application.ports import IKnowledgeRetriever
from app.smart_triage.domain.events import LowConfidenceAlertRaised
from app.smart_triage.domain.exceptions import EmptyTriageQueryError
from app.smart_triage.domain.grounding import ConfidenceLevel, GroundingThresholds
from tests.smart_triage.test_grounding import fragment

masker = RegexSpacyPiiMasker("clave-de-pruebas-del-sello-pii-0123456789", spacy_model=None)
WORKSPACE = uuid.uuid4()


class FakeRetriever(IKnowledgeRetriever):
    def __init__(self, *scores: float) -> None:
        self.scores = scores
        self.calls: list[tuple[uuid.UUID, SanitizedText, int]] = []

    def retrieve(self, workspace_id, query, *, top_k):
        self.calls.append((workspace_id, query, top_k))
        return [fragment(s) for s in self.scores]


@pytest.fixture()
def alerts():
    bus = InMemoryEventBus()
    received: list = []
    bus.subscribe(LowConfidenceAlertRaised, received.append)
    return bus, received


def service(retriever, bus, top_k=5) -> EvidenceRetrievalService:
    return EvidenceRetrievalService(
        retriever=retriever, masker=masker, events=bus, thresholds=GroundingThresholds(0.70, 0.85), top_k=top_k
    )


def test_query_is_anonymized_and_sealed_before_retrieval(alerts):
    bus, _ = alerts
    retriever = FakeRetriever(0.9)
    service(retriever, bus).retrieve_and_evaluate(
        RetrieveEvidenceCommand(WORKSPACE, "Soy juan.perez@empresa.pe y la VPN me da error 809 desde 10.0.0.15")
    )
    workspace_id, query, top_k = retriever.calls[0]
    assert workspace_id == WORKSPACE and top_k == 5
    assert "juan.perez@empresa.pe" not in query.text and "10.0.0.15" not in query.text
    assert masker.verify(query)


def test_grounded_evidence_does_not_raise_an_alert(alerts):
    bus, received = alerts
    result = service(FakeRetriever(0.88, 0.71), bus).retrieve_and_evaluate(RetrieveEvidenceCommand(WORKSPACE, "error 809"))
    assert result.level is ConfidenceLevel.SELF_SERVICE
    assert received == []


def test_low_confidence_publishes_the_alert_and_logs_a_warning(alerts, caplog):
    bus, received = alerts
    ticket_id = uuid.uuid4()
    with caplog.at_level(logging.WARNING, logger="app.smart_triage.application.evidence_retrieval_service"):
        result = service(FakeRetriever(0.52, 0.31), bus).retrieve_and_evaluate(
            RetrieveEvidenceCommand(WORKSPACE, "mi silla está rota", ticket_id=ticket_id)
        )
    assert result.level is ConfidenceLevel.LOW_CONFIDENCE
    [alert] = received
    assert (alert.workspace_id, alert.ticket_id, alert.best_score) == (WORKSPACE, ticket_id, 0.52)
    assert alert.similarity_threshold == 0.70 and alert.fragments_retrieved == 2
    assert "baja confianza" in caplog.text


def test_empty_knowledge_base_is_low_confidence(alerts):
    bus, received = alerts
    result = service(FakeRetriever(), bus).retrieve_and_evaluate(RetrieveEvidenceCommand(WORKSPACE, "error 809"))
    assert result.level is ConfidenceLevel.LOW_CONFIDENCE and len(received) == 1


def test_command_top_k_overrides_the_default(alerts):
    bus, _ = alerts
    retriever = FakeRetriever(0.9)
    service(retriever, bus, top_k=5).retrieve_and_evaluate(RetrieveEvidenceCommand(WORKSPACE, "vpn", top_k=2))
    assert retriever.calls[0][2] == 2


@pytest.mark.parametrize("text", ["", "   ", None])
def test_empty_query_is_rejected(alerts, text):
    bus, _ = alerts
    with pytest.raises(EmptyTriageQueryError):
        service(FakeRetriever(0.9), bus).retrieve_and_evaluate(RetrieveEvidenceCommand(WORKSPACE, text))


def test_long_queries_are_truncated(alerts):
    bus, _ = alerts
    retriever = FakeRetriever(0.9)
    service(retriever, bus).retrieve_and_evaluate(RetrieveEvidenceCommand(WORKSPACE, "vpn " * 3000))
    assert len(retriever.calls[0][1].text) <= MAX_QUERY_CHARACTERS
