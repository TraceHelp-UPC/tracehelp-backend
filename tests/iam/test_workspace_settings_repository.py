"""Pruebas de integración de SqlAlchemyWorkspaceSettingsRepository y lectura en vivo desde Smart Triage (US07, T62).

Requieren TEST_DATABASE_URL (PostgreSQL local Docker).
"""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.iam.application.workspace_settings_reader import WorkspaceSettingsReader
from app.iam.domain.enums import RoleName
from app.iam.domain.workspace_settings import RagSettings, WorkspaceSettings
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.persistence.workspace_settings_cache import WorkspaceSettingsCache
from app.iam.infrastructure.persistence.workspace_settings_repository import SqlAlchemyWorkspaceSettingsRepository
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.diagnosis_generation_service import DiagnosisGenerationService
from app.smart_triage.application.evidence_retrieval_service import (
    EvidenceRetrievalService,
    RetrieveEvidenceCommand,
)
from app.smart_triage.domain.diagnosis import DiagnosisDraft, DiagnosisStatus
from app.smart_triage.domain.grounding import ConfidenceLevel
from app.smart_triage.domain.triage_diagnosis import ReviewStatus, TicketRoute, TriageDiagnosis
from app.smart_triage.infrastructure.iam.iam_rag_parameters import IamRagParametersProvider
from tests.conftest import FAKE_HASH
from tests.smart_triage.test_diagnosis_generation_service import FakeGenerator
from tests.smart_triage.test_evidence_retrieval_service import FakeRetriever, masker

DEFAULTS = RagSettings(0.68, 0.80, 5, True)


def _leader(db_session, workspace_id: uuid.UUID) -> UserModel:
    leader = UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        full_name="Líder TI Demo",
        email=f"lider-{uuid.uuid4().hex[:6]}@demo.pe",
        password_hash=FAKE_HASH,
        role=RoleName.IT_LEADER,
        department="TI",
    )
    db_session.add(leader)
    db_session.flush()
    return leader


def test_repository_get_returns_none_when_no_row_exists(db_session, workspace_and_users):
    workspace, _, _ = workspace_and_users
    repo = SqlAlchemyWorkspaceSettingsRepository(db_session)
    assert repo.get(workspace.id) is None


def test_repository_upsert_inserts_and_updates_without_losing_precision(db_session, workspace_and_users):
    workspace, _, _ = workspace_and_users
    leader = _leader(db_session, workspace.id)
    repo = SqlAlchemyWorkspaceSettingsRepository(db_session)

    settings = WorkspaceSettings.empty(workspace.id)
    assert settings.update_rag(RagSettings(0.72, 0.85, 7, True), changed_by=leader.id, defaults=DEFAULTS)
    repo.save(settings)

    loaded = repo.get(workspace.id)
    assert loaded is not None
    assert loaded.similarity_threshold == 0.72
    assert loaded.self_service_threshold == 0.85
    assert loaded.retrieval_top_k == 7
    assert loaded.strict_grounding is True
    assert loaded.updated_by == leader.id
    assert loaded.updated_at is not None

    # Segundo save hace upsert sobre la misma fila
    assert loaded.update_rag(RagSettings(0.60, 0.90, 9, False), changed_by=leader.id, defaults=DEFAULTS)
    repo.save(loaded)

    reloaded = repo.get(workspace.id)
    assert reloaded is not None
    assert (
        reloaded.similarity_threshold,
        reloaded.self_service_threshold,
        reloaded.retrieval_top_k,
        reloaded.strict_grounding,
    ) == (0.60, 0.90, 9, False)


@pytest.mark.parametrize(
    ("sim", "ss", "top_k"),
    [
        (0.30, 0.80, 5),  # similarity < 0.50
        (0.96, 0.99, 5),  # similarity > 0.95
        (0.75, 0.70, 5),  # self_service < similarity
        (0.70, 1.00, 5),  # self_service > 0.99
        (0.70, 0.80, 0),  # top_k < 1
        (0.70, 0.80, 11),  # top_k > 10
    ],
)
def test_db_check_constraints_reject_out_of_range_values(db_session, workspace_and_users, sim, ss, top_k):
    workspace, _, _ = workspace_and_users
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(
                text(
                    "INSERT INTO iam_workspace_settings "
                    "(workspace_id, similarity_threshold, self_service_threshold, retrieval_top_k, strict_grounding) "
                    "VALUES (:ws, :sim, :ss, :top_k, true)"
                ),
                {"ws": workspace.id, "sim": sim, "ss": ss, "top_k": top_k},
            )


def test_fk_cascade_and_set_null_behavior(db_session):
    workspace = WorkspaceModel(id=uuid.uuid4(), name="Temp WS", subdomain=f"tmp-{uuid.uuid4().hex[:6]}")
    db_session.add(workspace)
    db_session.flush()
    leader = _leader(db_session, workspace.id)
    repo = SqlAlchemyWorkspaceSettingsRepository(db_session)

    ws_settings = WorkspaceSettings.empty(workspace.id)
    ws_settings.update_rag(RagSettings(0.75, 0.85, 6, True), changed_by=leader.id, defaults=DEFAULTS)
    repo.save(ws_settings)

    # Borrar el usuario deja updated_by en NULL (ON DELETE SET NULL)
    db_session.execute(text("DELETE FROM iam_users WHERE id = :id"), {"id": leader.id})
    db_session.flush()
    after_user_delete = repo.get(workspace.id)
    assert after_user_delete is not None and after_user_delete.updated_by is None

    # Borrar el workspace borra la fila de configuración (ON DELETE CASCADE)
    db_session.execute(text("DELETE FROM iam_workspaces WHERE id = :id"), {"id": workspace.id})
    db_session.flush()
    assert repo.get(workspace.id) is None


def test_evidence_retrieval_uses_saved_workspace_settings_without_restarting(db_session, workspace_and_users):
    """Criterio de terminado T62: guardar con el repositorio + invalidar caché cambia el triaje sin reiniciar."""
    workspace, _, _ = workspace_and_users
    leader = _leader(db_session, workspace.id)
    repo = SqlAlchemyWorkspaceSettingsRepository(db_session)
    cache = WorkspaceSettingsCache(ttl_seconds=60.0)
    reader = WorkspaceSettingsReader(repo, cache=cache, defaults=DEFAULTS)
    provider = IamRagParametersProvider(reader)
    retriever = FakeRetriever(0.70)
    bus = InMemoryEventBus()
    service = EvidenceRetrievalService(retriever=retriever, masker=masker, events=bus, parameters=provider)

    # Sin fila en BD usa defaults (0.68 / 0.80 / 5 / True): 0.70 es GROUNDED
    eval_before = service.retrieve_and_evaluate(RetrieveEvidenceCommand(workspace.id, "error 809 vpn"))
    assert eval_before.level is ConfidenceLevel.GROUNDED
    assert eval_before.thresholds.similarity == 0.68
    assert eval_before.strict_grounding is True
    assert retriever.calls[-1][2] == 5

    # Guardar nuevo umbral (0.72 / 0.85 / 8 / False) e invalidar la caché
    ws_settings = WorkspaceSettings.empty(workspace.id)
    ws_settings.update_rag(RagSettings(0.72, 0.85, 8, False), changed_by=leader.id, defaults=DEFAULTS)
    repo.save(ws_settings)
    cache.invalidate(workspace.id)

    # Misma instancia del servicio, sin reiniciar: ahora 0.70 es LOW_CONFIDENCE y top_k=8
    eval_after = service.retrieve_and_evaluate(RetrieveEvidenceCommand(workspace.id, "error 809 vpn"))
    assert eval_after.level is ConfidenceLevel.LOW_CONFIDENCE
    assert eval_after.thresholds.similarity == 0.72
    assert eval_after.thresholds.self_service == 0.85
    assert eval_after.strict_grounding is False
    assert retriever.calls[-1][2] == 8

    # Y con una consulta de 0.90 + strict_grounding=False sin citas, queda PENDING_REVIEW (nunca autoservicio)
    high_service = EvidenceRetrievalService(
        retriever=FakeRetriever(0.90), masker=masker, events=bus, parameters=provider
    )
    high_eval = high_service.retrieve_and_evaluate(RetrieveEvidenceCommand(workspace.id, "error 809 vpn"))
    assert high_eval.level is ConfidenceLevel.SELF_SERVICE
    assert high_eval.strict_grounding is False

    uncited = DiagnosisDraft(True, "Reinicia el cliente VPN.", ("Reconecta.",), ())
    outcome = DiagnosisGenerationService(generator=FakeGenerator(uncited), masker=masker).generate(
        "error 809", high_eval
    )
    assert outcome.status is DiagnosisStatus.ANSWERED
    diagnosis = TriageDiagnosis.from_analysis(
        workspace_id=workspace.id, ticket_id=uuid.uuid4(), evaluation=high_eval, outcome=outcome, ocr=None
    )
    assert diagnosis.review_status is ReviewStatus.PENDING_REVIEW
    assert diagnosis.route is TicketRoute.PENDING_ASSIGNMENT
    assert diagnosis.sources == ()
