"""Steps BDD para configuración de parámetros RAG por workspace (US07, T65)."""
import json
import uuid

from behave import given, then, when
from sqlalchemy import select

from app.analytics.infrastructure.persistence.models import AuditLogModel
from app.helpdesk.domain.enums import ImpactLevel
from app.helpdesk.domain.ticket import Ticket
from app.helpdesk.infrastructure.persistence.ticket_repository import SqlAlchemyTicketRepository
from app.iam.application.workspace_settings_reader import WorkspaceSettingsReader
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.infrastructure.persistence.workspace_settings_cache import get_workspace_settings_cache
from app.iam.infrastructure.persistence.workspace_settings_repository import SqlAlchemyWorkspaceSettingsRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.automatic_triage_service import AutomaticTriageService
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.evidence_retrieval_service import EvidenceRetrievalService
from app.smart_triage.application.triage_analysis_service import TriageAnalysisService
from app.smart_triage.domain.diagnosis import DiagnosisDraft
from app.smart_triage.infrastructure.helpdesk.helpdesk_ticket_reader import HelpdeskTicketReader
from app.smart_triage.infrastructure.iam.iam_rag_parameters import IamRagParametersProvider
from app.smart_triage.infrastructure.ocr.tesseract_ocr_adapter import TesseractOcrAdapter
from app.smart_triage.infrastructure.persistence.triage_diagnosis_repository import (
    SqlAlchemyTriageDiagnosisRepository,
)
from app.smart_triage.interfaces.rest.dependencies import (
    get_diagnosis_generation_service,
    get_evidence_retrieval_service,
)
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator
from tests.smart_triage.test_evidence_retrieval_service import FakeRetriever, masker

CONFIG_RAG_URL = "/api/v1/config/rag"
FAKE_HASH = "$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm"


def _headers_for_user(context, user_model: UserModel) -> dict[str, str]:
    user = SqlAlchemyUserRepository(context.session).find_by_id(user_model.id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _headers_for_role(context, role: str) -> dict[str, str]:
    return _headers_for_user(context, context.users[role])


def _parse_cell(value: str):
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _payload_from_table(table) -> dict:
    row = table[0]
    return {heading: _parse_cell(row[heading]) for heading in table.headings}


def _wire_smart_triage(context, *, similarity: float, uncited_answer: bool = False) -> None:
    reader = WorkspaceSettingsReader(
        SqlAlchemyWorkspaceSettingsRepository(context.session),
        cache=get_workspace_settings_cache(),
    )
    retriever = FakeRetriever(similarity)
    bus = InMemoryEventBus()
    retrieval = EvidenceRetrievalService(
        retriever=retriever,
        masker=masker,
        events=bus,
        parameters=IamRagParametersProvider(reader),
    )
    draft = (
        DiagnosisDraft(True, "Reinicia el adaptador VPN.", ("Abre el cliente VPN.",), ())
        if uncited_answer
        else None
    )
    generator = FakeGenerator(draft=draft)
    generation = DiagnosisGenerationService(generator=generator, masker=masker)

    context.rag_retriever = retriever
    context.rag_retrieval_service = retrieval
    context.rag_generation_service = generation
    context.rag_triage_bus = bus
    context.app.dependency_overrides[get_evidence_retrieval_service] = lambda: retrieval
    context.app.dependency_overrides[get_diagnosis_generation_service] = lambda: generation


# --- Preparación ----------------------------------------------------------------------------------------------


@given('the "{role}" updated the RAG configuration to {similarity:f}, {self_service:f}, {top_k:d}, {strict}')
def step_preset_rag_config(context, role, similarity, self_service, top_k, strict):
    payload = {
        "similarity_threshold": similarity,
        "self_service_threshold": self_service,
        "retrieval_top_k": top_k,
        "strict_grounding": _parse_cell(strict),
    }
    res = context.client.put(CONFIG_RAG_URL, json=payload, headers=_headers_for_role(context, role))
    assert res.status_code == 200, res.text


@given("smart triage reads workspace RAG settings with a simulated retriever returning similarity {score:f}")
def step_wire_retriever(context, score):
    _wire_smart_triage(context, similarity=score, uncited_answer=False)


@given("smart triage reads workspace RAG settings with similarity {score:f} and an uncited LLM answer")
def step_wire_uncited_llm(context, score):
    _wire_smart_triage(context, similarity=score, uncited_answer=True)


@given("a second workspace with its own IT leader")
def step_second_workspace(context):
    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    context.session.add(other_ws)
    context.session.flush()
    other_leader = UserModel(
        id=uuid.uuid4(),
        workspace_id=other_ws.id,
        full_name="Líder Secundario",
        email=f"lider2-{uuid.uuid4().hex[:6]}@otra.pe",
        password_hash=FAKE_HASH,
        role=RoleName.IT_LEADER,
        department="TI",
    )
    context.session.add(other_leader)
    context.session.flush()
    context.other_workspace = other_ws
    context.other_leader = other_leader


# --- Acciones -------------------------------------------------------------------------------------------------


@when('the "{role}" requests the RAG configuration')
def step_get_rag(context, role):
    context.response = context.client.get(CONFIG_RAG_URL, headers=_headers_for_role(context, role))


@when("an unauthenticated client requests the RAG configuration")
def step_get_rag_unauth(context):
    context.response = context.client.get(CONFIG_RAG_URL)


@when('a client with invalid token requests the RAG configuration')
def step_get_rag_invalid_token(context):
    context.response = context.client.get(CONFIG_RAG_URL, headers={"Authorization": "Bearer invalid-jwt"})


@when("an unauthenticated client updates the RAG configuration")
def step_put_rag_unauth(context):
    context.response = context.client.put(
        CONFIG_RAG_URL,
        json={
            "similarity_threshold": 0.72,
            "self_service_threshold": 0.85,
            "retrieval_top_k": 5,
            "strict_grounding": True,
        },
    )


@when('the "{role}" updates the RAG configuration with:')
def step_put_rag_table(context, role):
    payload = _payload_from_table(context.table)
    context.response = context.client.put(CONFIG_RAG_URL, json=payload, headers=_headers_for_role(context, role))


@when('the "{role}" sends the raw RAG configuration payload:')
def step_put_rag_raw(context, role):
    payload = json.loads(context.text)
    context.response = context.client.put(CONFIG_RAG_URL, json=payload, headers=_headers_for_role(context, role))


@when("the leader of the second workspace requests the RAG configuration")
def step_other_leader_get_rag(context):
    context.response = context.client.get(CONFIG_RAG_URL, headers=_headers_for_user(context, context.other_leader))


@when('automatic triage processes a ticket for "{description}" using the workspace RAG settings')
def step_run_auto_triage_with_rag(context, description):
    ticket = Ticket.register(
        workspace_id=context.workspace.id,
        reporter_id=context.users["COLLABORATOR"].id,
        title="Incidente VPN",
        description=description,
        impact_level=ImpactLevel.MEDIUM,
    )
    SqlAlchemyTicketRepository(context.session).save(ticket)
    triage = AutomaticTriageService(
        session=context.session,
        tickets=HelpdeskTicketReader(context.session),
        diagnoses=SqlAlchemyTriageDiagnosisRepository(context.session),
        analysis=TriageAnalysisService(
            ocr=TesseractOcrAdapter(),
            retrieval=context.rag_retrieval_service,
            generation=context.rag_generation_service,
        ),
        masker=masker,
        events=context.rag_triage_bus,
    )
    context.rag_triage_diagnosis = triage.triage(ticket.id)


# --- Verificaciones -------------------------------------------------------------------------------------------


@then("the RAG configuration response has:")
def step_assert_rag_fields(context):
    body = context.response.json()
    for row in context.table:
        key, raw_expected = row[0], row[1]
        expected = _parse_cell(raw_expected)
        actual = body.get(key)
        if isinstance(expected, bool):
            assert actual is expected, f"{key}: {actual!r} != {expected!r}"
        else:
            assert actual == expected, f"{key}: {actual!r} != {expected!r}"


@then("the RAG thresholds are serialized as JSON numbers")
def step_assert_float_thresholds(context):
    body = context.response.json()
    for key in ("similarity_threshold", "self_service_threshold"):
        assert isinstance(body[key], float), f"{key} no es float JSON: {type(body[key])}"
    for key in ("similarity_threshold", "self_service_threshold"):
        assert isinstance(body["defaults"][key], float), f"defaults.{key} no es float JSON"


@then("the RAG configuration has no modification metadata")
def step_assert_no_mod_metadata(context):
    body = context.response.json()
    assert body["updated_at"] is None, body
    assert body["updated_by"] is None, body
    assert body["updated_by_name"] is None, body


@then("the RAG configuration includes defaults and calibration limits")
def step_assert_defaults_and_limits(context):
    body = context.response.json()
    assert body["defaults"] == {
        "similarity_threshold": 0.68,
        "self_service_threshold": 0.80,
        "retrieval_top_k": 5,
        "strict_grounding": True,
    }, body["defaults"]
    assert body["limits"] == {
        "similarity_threshold": {"min": 0.50, "max": 0.95, "step": 0.01, "warning_below": 0.65},
        "self_service_threshold": {"min": "similarity_threshold", "max": 0.99, "step": 0.01},
        "retrieval_top_k": {"min": 1, "max": 10},
    }, body["limits"]


@then('the RAG modification metadata shows the "{role}"')
def step_assert_mod_metadata(context, role):
    body = context.response.json()
    leader = context.users[role]
    assert body["updated_at"] is not None, body
    assert body["updated_by"] == str(leader.id), body
    assert body["updated_by_name"] == leader.full_name, body


@then('the audit log records {count:d} "{event_type}" entry for section "{section}" acted by "{role}"')
@then('the audit log records {count:d} "{event_type}" entries for section "{section}"')
def step_assert_rag_audit_count(context, count, event_type, section, role=None):
    rows = (
        context.session.execute(
            select(AuditLogModel)
            .where(AuditLogModel.workspace_id == context.workspace.id)
            .where(AuditLogModel.event_type == event_type)
            .order_by(AuditLogModel.occurred_at.asc(), AuditLogModel.id.asc())
        )
        .scalars()
        .all()
    )
    matching = [r for r in rows if r.detail.get("section") == section]
    assert len(matching) == count, f"Se esperaban {count} entradas y hay {len(matching)}: {[r.detail for r in rows]}"
    if count > 0 and role is not None:
        actor_id = context.users[role].id
        last = matching[-1]
        assert last.actor_id == actor_id, f"actor_id {last.actor_id} != {actor_id}"
        assert last.entity_type == "workspace_settings", last.entity_type
        assert last.entity_id == context.workspace.id, last.entity_id
        assert last.ticket_id is None, last.ticket_id
        context.last_rag_audit = last


@then("the last RAG audit entry records exactly these changes:")
def step_assert_rag_audit_changes(context):
    expected = {
        row["field"]: {"old": _parse_cell(row["old"]), "new": _parse_cell(row["new"])}
        for row in context.table
    }
    assert context.last_rag_audit.detail["changes"] == expected, context.last_rag_audit.detail


@then("the RAG modification timestamp is remembered")
def step_remember_updated_at(context):
    context.remembered_updated_at = context.response.json()["updated_at"]
    assert context.remembered_updated_at is not None


@then("the RAG modification timestamp matches the remembered one")
def step_match_updated_at(context):
    assert context.response.json()["updated_at"] == context.remembered_updated_at


@then("the evidence search reports similarity threshold {threshold:f} and retrieved top_k {top_k:d}")
def step_assert_evidence_search_params(context, threshold, top_k):
    body = context.response.json()
    assert body["similarity_threshold"] == threshold, body
    assert context.rag_retriever.calls[-1][2] == top_k, context.rag_retriever.calls


@then("the preview diagnosis has {count:d} sources")
def step_assert_preview_sources_count(context, count):
    diagnosis = context.response.json()["diagnosis"]
    assert diagnosis is not None, context.response.text
    assert len(diagnosis["sources"]) == count, diagnosis


@then('the resulting triage diagnosis has review status "{review_status}" and {count:d} sources')
def step_assert_triage_diagnosis(context, review_status, count):
    diag = context.rag_triage_diagnosis
    assert diag is not None
    assert diag.review_status.value == review_status, diag.review_status
    assert len(diag.sources) == count, diag.sources
