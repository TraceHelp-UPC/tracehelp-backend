"""Pruebas unitarias y de integración de GET/PUT /api/v1/config/rag (US07, T63).

Las pruebas unitarias corren sin base de datos; las de integración usan TEST_DATABASE_URL (PostgreSQL local).
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.analytics.application.audit_log_service import AuditEventHandler
from app.iam.application.workspace_settings_reader import WorkspaceSettingsReader
from app.iam.application.workspace_settings_service import (
    UpdateRagSettingsCommand,
    WorkspaceSettingsService,
)
from app.iam.domain.enums import RoleName
from app.iam.domain.events import ConfigurationChanged
from app.iam.domain.exceptions import InvalidWorkspaceSettingsError
from app.iam.domain.repositories import IUserRepository, IWorkspaceSettingsRepository
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PasswordHash
from app.iam.domain.workspace_settings import RagSettings, WorkspaceSettings
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.persistence.workspace_settings_cache import (
    WorkspaceSettingsCache,
    get_workspace_settings_cache,
)
from app.iam.infrastructure.persistence.workspace_settings_repository import SqlAlchemyWorkspaceSettingsRepository
from app.main import app as real_app
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.shared.interfaces.rest.problem_details import PROBLEM_JSON, _message
from app.smart_triage.application.evidence_retrieval_service import (
    EvidenceRetrievalService,
    RetrieveEvidenceCommand,
)
from app.smart_triage.domain.grounding import ConfidenceLevel
from app.smart_triage.infrastructure.iam.iam_rag_parameters import IamRagParametersProvider
from tests.conftest import FAKE_HASH
from tests.smart_triage.test_evidence_retrieval_service import FakeRetriever, masker

CONFIG_RAG = "/api/v1/config/rag"
DEFAULTS = RagSettings(0.68, 0.80, 5, True)


# =============================================================================
# Pruebas unitarias (sin base de datos)
# =============================================================================
class _RecordingSession:
    def __init__(self, trace: list[str]) -> None:
        self._trace = trace

    def commit(self) -> None:
        self._trace.append("commit")


class _InMemorySettingsRepo(IWorkspaceSettingsRepository):
    def __init__(self, trace: list[str], initial: WorkspaceSettings | None = None) -> None:
        self._trace = trace
        self._store: dict[uuid.UUID, WorkspaceSettings] = {}
        if initial is not None:
            self._store[initial.workspace_id] = initial

    def get(self, workspace_id: uuid.UUID) -> WorkspaceSettings | None:
        return self._store.get(workspace_id)

    def save(self, settings: WorkspaceSettings) -> WorkspaceSettings:
        self._trace.append("save")
        self._store[settings.workspace_id] = settings
        return settings


class _StubUsers(IUserRepository):
    def __init__(self, users: dict[uuid.UUID, User] | None = None) -> None:
        self._users = users or {}

    def save(self, user: User) -> User:
        self._users[user.id] = user
        return user

    def find_by_id(self, user_id: uuid.UUID) -> User | None:
        return self._users.get(user_id)

    def find_by_email(self, email: EmailAddress) -> User | None:
        return None

    def exists_by_email(self, email: EmailAddress) -> bool:
        return False

    def find_support_staff_by_workspace(self, workspace_id: uuid.UUID) -> list[User]:
        return []

    def search(self, criteria, page):
        raise NotImplementedError


class _TracingCache(WorkspaceSettingsCache):
    def __init__(self, trace: list[str]) -> None:
        super().__init__()
        self._trace = trace

    def invalidate(self, workspace_id: uuid.UUID) -> None:
        self._trace.append("invalidate")
        super().invalidate(workspace_id)


def _domain_leader(workspace_id: uuid.UUID) -> User:
    return User.register(
        workspace_id=workspace_id,
        full_name="Roberto Pérez",
        email=EmailAddress("roberto@empresa.pe"),
        password_hash=PasswordHash(FAKE_HASH),
        role=RoleName.IT_LEADER,
        department="TI",
    )


def test_service_commits_before_invalidating_cache_and_publishing_event():
    ws_id = uuid.uuid4()
    leader = _domain_leader(ws_id)
    trace: list[str] = []
    cache = _TracingCache(trace)
    cache.set(ws_id, WorkspaceSettings.empty(ws_id))

    bus = InMemoryEventBus()
    received: list[ConfigurationChanged] = []

    def _on_event(event: ConfigurationChanged) -> None:
        trace.append("publish")
        received.append(event)

    bus.subscribe(ConfigurationChanged, _on_event)

    service = WorkspaceSettingsService(
        session=_RecordingSession(trace),  # type: ignore[arg-type]
        settings_repository=_InMemorySettingsRepo(trace),
        users=_StubUsers({leader.id: leader}),
        cache=cache,
        events=bus,
        defaults=DEFAULTS,
    )

    view = service.update_rag(
        UpdateRagSettingsCommand(
            workspace_id=ws_id,
            changed_by=leader.id,
            similarity_threshold=Decimal("0.72"),
            self_service_threshold=Decimal("0.85"),
            retrieval_top_k=7,
            strict_grounding=True,
        )
    )

    assert trace == ["save", "commit", "invalidate", "publish"]
    assert cache.get(ws_id) is None
    assert view.is_default is False
    assert view.rag == RagSettings(0.72, 0.85, 7, True)
    assert view.updated_by == leader.id
    assert view.updated_by_name == "Roberto Pérez"
    assert len(received) == 1
    assert received[0].section == "rag"
    assert received[0].changes == {
        "similarity_threshold": {"old": 0.68, "new": 0.72},
        "self_service_threshold": {"old": 0.80, "new": 0.85},
        "retrieval_top_k": {"old": 5, "new": 7},
    }


def test_service_noop_update_does_not_save_commit_invalidate_or_publish():
    ws_id = uuid.uuid4()
    leader = _domain_leader(ws_id)
    trace: list[str] = []
    cache = _TracingCache(trace)
    cache.set(ws_id, WorkspaceSettings.empty(ws_id))
    bus = InMemoryEventBus()
    published: list = []
    bus.subscribe(ConfigurationChanged, published.append)

    service = WorkspaceSettingsService(
        session=_RecordingSession(trace),  # type: ignore[arg-type]
        settings_repository=_InMemorySettingsRepo(trace),
        users=_StubUsers({leader.id: leader}),
        cache=cache,
        events=bus,
        defaults=DEFAULTS,
    )

    view = service.update_rag(
        UpdateRagSettingsCommand(
            workspace_id=ws_id,
            changed_by=leader.id,
            similarity_threshold=0.68,
            self_service_threshold=0.80,
            retrieval_top_k=5,
            strict_grounding=True,
        )
    )

    assert trace == []
    assert published == []
    assert cache.get(ws_id) is not None
    assert view.is_default is True
    assert view.updated_at is None
    assert view.updated_by is None
    assert view.updated_by_name is None


def test_service_get_rag_returns_null_metadata_when_row_has_only_null_rag_columns():
    ws_id = uuid.uuid4()
    leader = _domain_leader(ws_id)
    # Simula una fila creada por otra sección (ej. US08 business_rules) con columnas RAG en NULL
    row_with_null_rag = WorkspaceSettings(
        workspace_id=ws_id,
        updated_at=datetime.now(UTC),
        updated_by=leader.id,
    )
    service = WorkspaceSettingsService(
        session=_RecordingSession([]),  # type: ignore[arg-type]
        settings_repository=_InMemorySettingsRepo([], initial=row_with_null_rag),
        users=_StubUsers({leader.id: leader}),
        cache=WorkspaceSettingsCache(),
        defaults=DEFAULTS,
    )

    view = service.get_rag(ws_id)
    assert view.is_default is True
    assert view.rag == DEFAULTS
    assert view.updated_at is None
    assert view.updated_by is None
    assert view.updated_by_name is None


def test_service_rejects_domain_invalid_values_without_side_effects():
    ws_id = uuid.uuid4()
    trace: list[str] = []
    service = WorkspaceSettingsService(
        session=_RecordingSession(trace),  # type: ignore[arg-type]
        settings_repository=_InMemorySettingsRepo(trace),
        users=_StubUsers(),
        cache=_TracingCache(trace),
        defaults=DEFAULTS,
    )

    with pytest.raises(InvalidWorkspaceSettingsError):
        service.update_rag(
            UpdateRagSettingsCommand(
                workspace_id=ws_id,
                changed_by=uuid.uuid4(),
                similarity_threshold=0.75,
                self_service_threshold=0.70,
                retrieval_top_k=5,
                strict_grounding=True,
            )
        )
    assert trace == []


def test_audit_handler_explicit_branch_for_configuration_changed():
    ws_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    event = ConfigurationChanged(
        workspace_id=ws_id,
        changed_by=actor_id,
        section="rag",
        changes={"similarity_threshold": {"old": 0.68, "new": 0.72}},
    )

    entry = AuditEventHandler().to_audit_entry(event)
    assert entry is not None
    assert entry.event_type == "ConfigurationChanged"
    assert entry.workspace_id == ws_id
    assert entry.actor_id == actor_id
    assert entry.entity_type == "workspace_settings"
    assert entry.entity_id == ws_id
    assert entry.ticket_id is None
    assert entry.detail == {
        "section": "rag",
        "changes": {"similarity_threshold": {"old": 0.68, "new": 0.72}},
    }
    assert entry.verify_integrity() is True


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ({"type": "greater_than_equal", "ctx": {"ge": Decimal("0.50")}}, "debe ser mayor o igual que 0.50"),
        ({"type": "less_than_equal", "ctx": {"le": 10}}, "debe ser menor o igual que 10"),
        ({"type": "greater_than", "ctx": {"gt": 0}}, "debe ser mayor que 0"),
        ({"type": "less_than", "ctx": {"lt": 1}}, "debe ser menor que 1"),
        ({"type": "decimal_max_places", "ctx": {"decimal_places": 2}}, "admite como máximo 2 decimales"),
        ({"type": "extra_forbidden"}, "campo no permitido"),
    ],
)
def test_problem_details_message_formats_limits_and_new_validation_kinds(error, expected):
    assert _message(error) == expected


def test_openapi_documents_config_rag_endpoints_with_examples():
    spec = real_app.openapi()
    path = spec["paths"][CONFIG_RAG]

    get_op = path["get"]
    assert get_op["summary"] == "Consultar parámetros RAG"
    assert "Configuración" in get_op["tags"]
    assert "analytics:read" in get_op["description"]
    assert "200" in get_op["responses"] and "403" in get_op["responses"]

    put_op = path["put"]
    assert put_op["summary"] == "Actualizar parámetros RAG"
    assert "Configuración" in put_op["tags"]
    assert "config:write" in put_op["description"]
    for code in ("200", "403", "422"):
        assert code in put_op["responses"]
    err_422 = put_op["responses"]["422"]["content"][PROBLEM_JSON]["example"]
    assert err_422["type"] == "urn:tracehelp:problems:validation-error"
    assert err_422["errors"][0]["field"] == "similarity_threshold"


# =============================================================================
# Pruebas de integración (requieren TEST_DATABASE_URL)
# =============================================================================
def _user_model(workspace_id: uuid.UUID, role: RoleName, name: str) -> UserModel:
    return UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        full_name=name,
        email=f"user-{uuid.uuid4().hex[:8]}@empresa.pe",
        password_hash=FAKE_HASH,
        role=role,
        department="TI",
    )


@pytest.fixture()
def team(db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    leader = _user_model(workspace.id, RoleName.IT_LEADER, "Roberto Pérez")
    specialist = _user_model(workspace.id, RoleName.SPECIALIST_L2, "Carlos Reátegui")
    db_session.add_all([leader, specialist])
    db_session.flush()
    get_workspace_settings_cache().invalidate(workspace.id)
    yield {
        "workspace": workspace,
        "leader": leader,
        "analyst": analyst,
        "collaborator": collaborator,
        "specialist": specialist,
        "h": {
            "leader": auth_headers(db_session, leader),
            "analyst": auth_headers(db_session, analyst),
            "collaborator": auth_headers(db_session, collaborator),
            "specialist": auth_headers(db_session, specialist),
        },
    }
    get_workspace_settings_cache().invalidate(workspace.id)


def _valid_payload(**overrides):
    body = {
        "similarity_threshold": 0.72,
        "self_service_threshold": 0.85,
        "retrieval_top_k": 7,
        "strict_grounding": True,
    }
    body.update(overrides)
    return body


def test_config_rag_requires_authentication(api_client, team):
    get_res = api_client.get(CONFIG_RAG)
    assert get_res.status_code == 401
    assert get_res.headers["content-type"].startswith(PROBLEM_JSON)
    assert get_res.json()["type"] == "urn:tracehelp:problems:unauthorized"

    put_res = api_client.put(CONFIG_RAG, json=_valid_payload())
    assert put_res.status_code == 401
    assert put_res.json()["type"] == "urn:tracehelp:problems:unauthorized"


@pytest.mark.parametrize("who", ["collaborator", "analyst", "specialist"])
def test_config_rag_forbids_roles_without_permissions(api_client, team, who):
    headers = team["h"][who]
    get_res = api_client.get(CONFIG_RAG, headers=headers)
    assert get_res.status_code == 403
    assert get_res.headers["content-type"].startswith(PROBLEM_JSON)
    assert get_res.json()["type"] == "urn:tracehelp:problems:forbidden"
    assert "analytics:read" in get_res.json()["detail"]

    put_res = api_client.put(CONFIG_RAG, json=_valid_payload(), headers=headers)
    assert put_res.status_code == 403
    assert put_res.headers["content-type"].startswith(PROBLEM_JSON)
    assert put_res.json()["type"] == "urn:tracehelp:problems:forbidden"
    assert "config:write" in put_res.json()["detail"]


def test_get_rag_returns_defaults_and_limits_as_json_numbers(api_client, team):
    response = api_client.get(CONFIG_RAG, headers=team["h"]["leader"])
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["similarity_threshold"] == 0.68
    assert body["self_service_threshold"] == 0.80
    assert type(body["similarity_threshold"]) is float
    assert type(body["self_service_threshold"]) is float
    assert body["retrieval_top_k"] == 5
    assert body["strict_grounding"] is True
    assert body["is_default"] is True
    assert body["updated_at"] is None
    assert body["updated_by"] is None
    assert body["updated_by_name"] is None
    assert body["defaults"] == {
        "similarity_threshold": 0.68,
        "self_service_threshold": 0.80,
        "retrieval_top_k": 5,
        "strict_grounding": True,
    }
    assert body["limits"] == {
        "similarity_threshold": {"min": 0.50, "max": 0.95, "step": 0.01, "warning_below": 0.65},
        "self_service_threshold": {"min": "similarity_threshold", "max": 0.99, "step": 0.01},
        "retrieval_top_k": {"min": 1, "max": 10},
    }


def test_put_rag_persists_returns_metadata_and_writes_audit_log(api_client, team):
    leader_headers = team["h"]["leader"]
    leader = team["leader"]
    workspace = team["workspace"]

    put_res = api_client.put(CONFIG_RAG, json=_valid_payload(), headers=leader_headers)
    assert put_res.status_code == 200, put_res.text
    body = put_res.json()

    assert body["similarity_threshold"] == 0.72
    assert body["self_service_threshold"] == 0.85
    assert type(body["similarity_threshold"]) is float
    assert type(body["self_service_threshold"]) is float
    assert body["retrieval_top_k"] == 7
    assert body["strict_grounding"] is True
    assert body["is_default"] is False
    assert body["updated_at"] is not None
    assert body["updated_by"] == str(leader.id)
    assert body["updated_by_name"] == "Roberto Pérez"

    # GET posterior refleja exactamente lo guardado
    get_res = api_client.get(CONFIG_RAG, headers=leader_headers)
    assert get_res.status_code == 200
    assert get_res.json() == body

    # Bitácora de auditoría: una entrada ConfigurationChanged con solo los campos modificados
    audit = api_client.get("/api/v1/audit/logs?event_type=ConfigurationChanged", headers=leader_headers)
    assert audit.status_code == 200, audit.text
    items = audit.json()["items"]
    assert len(items) == 1
    entry = items[0]
    assert entry["actor_id"] == str(leader.id)
    assert entry["actor_name"] == "Roberto Pérez"
    assert entry["entity_type"] == "workspace_settings"
    assert entry["entity_id"] == str(workspace.id)
    assert entry["ticket_id"] is None
    assert entry["detail"] == {
        "section": "rag",
        "changes": {
            "similarity_threshold": {"old": 0.68, "new": 0.72},
            "self_service_threshold": {"old": 0.80, "new": 0.85},
            "retrieval_top_k": {"old": 5, "new": 7},
        },
    }

    # Segundo cambio solo sobre strict_grounding: changes solo registra ese campo
    second = api_client.put(CONFIG_RAG, json=_valid_payload(strict_grounding=False), headers=leader_headers)
    assert second.status_code == 200
    assert second.json()["strict_grounding"] is False

    audit2 = api_client.get("/api/v1/audit/logs?event_type=ConfigurationChanged", headers=leader_headers).json()["items"]
    assert len(audit2) == 2
    assert audit2[0]["detail"] == {
        "section": "rag",
        "changes": {"strict_grounding": {"old": True, "new": False}},
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"similarity_threshold": 0.50, "self_service_threshold": 0.50, "retrieval_top_k": 1, "strict_grounding": False},
        {"similarity_threshold": 0.95, "self_service_threshold": 0.99, "retrieval_top_k": 10, "strict_grounding": True},
    ],
)
def test_put_rag_accepts_boundary_values(api_client, team, payload):
    res = api_client.put(CONFIG_RAG, json=payload, headers=team["h"]["leader"])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["similarity_threshold"] == payload["similarity_threshold"]
    assert body["self_service_threshold"] == payload["self_service_threshold"]
    assert body["retrieval_top_k"] == payload["retrieval_top_k"]
    assert body["strict_grounding"] is payload["strict_grounding"]


def test_put_rag_noop_keeps_updated_at_and_emits_no_audit_event(api_client, team):
    leader_headers = team["h"]["leader"]

    # 1) No-op contra valores por defecto (sin fila previa)
    noop_defaults = api_client.put(
        CONFIG_RAG,
        json={
            "similarity_threshold": 0.68,
            "self_service_threshold": 0.80,
            "retrieval_top_k": 5,
            "strict_grounding": True,
        },
        headers=leader_headers,
    )
    assert noop_defaults.status_code == 200
    assert noop_defaults.json()["is_default"] is True
    assert noop_defaults.json()["updated_at"] is None
    assert api_client.get("/api/v1/audit/logs?event_type=ConfigurationChanged", headers=leader_headers).json()["total"] == 0

    # 2) Guardado real seguido de un PUT idéntico
    first = api_client.put(CONFIG_RAG, json=_valid_payload(), headers=leader_headers)
    assert first.status_code == 200
    saved_updated_at = first.json()["updated_at"]
    assert api_client.get("/api/v1/audit/logs?event_type=ConfigurationChanged", headers=leader_headers).json()["total"] == 1

    noop_same = api_client.put(CONFIG_RAG, json=_valid_payload(), headers=leader_headers)
    assert noop_same.status_code == 200
    assert noop_same.json()["updated_at"] == saved_updated_at
    assert api_client.get("/api/v1/audit/logs?event_type=ConfigurationChanged", headers=leader_headers).json()["total"] == 1


@pytest.mark.parametrize(
    ("payload", "expected_field", "expected_type", "expected_msg_fragment"),
    [
        (_valid_payload(similarity_threshold=0.30), "similarity_threshold", "greater_than_equal", "mayor o igual que 0.50"),
        (_valid_payload(similarity_threshold=0.96), "similarity_threshold", "less_than_equal", "menor o igual que 0.95"),
        (
            _valid_payload(similarity_threshold=0.75, self_service_threshold=0.70),
            "self_service_threshold",
            "self_service_below_similarity",
            "0.75",
        ),
        (_valid_payload(self_service_threshold=1.00), "self_service_threshold", "less_than_equal", "menor o igual que 0.99"),
        (_valid_payload(similarity_threshold=0.725), "similarity_threshold", "decimal_max_places", "máximo 2 decimales"),
        (_valid_payload(self_service_threshold=0.855), "self_service_threshold", "decimal_max_places", "máximo 2 decimales"),
        (_valid_payload(retrieval_top_k=0), "retrieval_top_k", "greater_than_equal", "mayor o igual que 1"),
        (_valid_payload(retrieval_top_k=11), "retrieval_top_k", "less_than_equal", "menor o igual que 10"),
        (
            {"similarity_threshold": 0.72, "self_service_threshold": 0.85, "retrieval_top_k": 5},
            "strict_grounding",
            "missing",
            "es obligatorio",
        ),
        (_valid_payload(unknown_param=123), "unknown_param", "extra_forbidden", "campo no permitido"),
        (_valid_payload(strict_grounding="si"), "strict_grounding", "bool_parsing", "verdadero o falso"),
    ],
)
def test_put_rag_rejects_invalid_payloads_with_rfc7807_422(
    api_client, team, payload, expected_field, expected_type, expected_msg_fragment
):
    leader_headers = team["h"]["leader"]
    # Guarda un estado previo conocido para comprobar que un 422 no lo altera
    assert api_client.put(CONFIG_RAG, json=_valid_payload(similarity_threshold=0.70), headers=leader_headers).status_code == 200

    res = api_client.put(CONFIG_RAG, json=payload, headers=leader_headers)
    assert res.status_code == 422, res.text
    assert res.headers["content-type"].startswith(PROBLEM_JSON)
    body = res.json()
    assert body["type"] == "urn:tracehelp:problems:validation-error"
    assert body["status"] == 422
    assert body["instance"] == CONFIG_RAG
    matching = [e for e in body["errors"] if e["field"] == expected_field]
    assert matching, body["errors"]
    assert matching[0]["type"] == expected_type
    assert expected_msg_fragment in matching[0]["message"]

    # Los valores previos siguen intactos
    current = api_client.get(CONFIG_RAG, headers=leader_headers).json()
    assert current["similarity_threshold"] == 0.70


def test_put_rag_invalidates_shared_cache_and_updates_smart_triage_immediately(api_client, db_session, team):
    workspace = team["workspace"]
    leader_headers = team["h"]["leader"]

    # Smart Triage lee desde la caché global compartida con el endpoint PUT
    shared_cache = get_workspace_settings_cache()
    reader = WorkspaceSettingsReader(
        SqlAlchemyWorkspaceSettingsRepository(db_session),
        cache=shared_cache,
    )
    provider = IamRagParametersProvider(reader)
    retriever = FakeRetriever(0.70)
    triage_service = EvidenceRetrievalService(
        retriever=retriever,
        masker=masker,
        events=InMemoryEventBus(),
        parameters=provider,
    )

    # 1) Antes del PUT, el workspace queda cacheado con defaults (0.68): 0.70 es GROUNDED
    eval_before = triage_service.retrieve_and_evaluate(RetrieveEvidenceCommand(workspace.id, "error 809 vpn"))
    assert eval_before.level is ConfidenceLevel.GROUNDED
    assert eval_before.thresholds.similarity == 0.68
    assert shared_cache.get(workspace.id) is not None

    # 2) PUT sube el umbral a 0.72 y top_k a 8 -> invalida la caché global tras el commit
    put_res = api_client.put(
        CONFIG_RAG,
        json=_valid_payload(similarity_threshold=0.72, self_service_threshold=0.85, retrieval_top_k=8),
        headers=leader_headers,
    )
    assert put_res.status_code == 200
    assert shared_cache.get(workspace.id) is None

    # 3) Misma instancia de EvidenceRetrievalService, sin reiniciar: 0.70 ahora es LOW_CONFIDENCE
    eval_after = triage_service.retrieve_and_evaluate(RetrieveEvidenceCommand(workspace.id, "error 809 vpn"))
    assert eval_after.level is ConfidenceLevel.LOW_CONFIDENCE
    assert eval_after.thresholds.similarity == 0.72
    assert eval_after.thresholds.self_service == 0.85
    assert retriever.calls[-1][2] == 8


def test_config_rag_is_isolated_per_workspace(api_client, db_session, team, auth_headers):
    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Otro WS", subdomain=f"otro-{uuid.uuid4().hex[:6]}")
    db_session.add(other_ws)
    db_session.flush()
    other_leader = _user_model(other_ws.id, RoleName.IT_LEADER, "Otra Líder")
    db_session.add(other_leader)
    db_session.flush()
    other_headers = auth_headers(db_session, other_leader)

    assert api_client.put(CONFIG_RAG, json=_valid_payload(similarity_threshold=0.80, self_service_threshold=0.90), headers=team["h"]["leader"]).status_code == 200

    other_get = api_client.get(CONFIG_RAG, headers=other_headers)
    assert other_get.status_code == 200
    assert other_get.json()["is_default"] is True
    assert other_get.json()["similarity_threshold"] == 0.68


def test_get_rag_handles_null_updated_by(api_client, db_session, team):
    assert api_client.put(CONFIG_RAG, json=_valid_payload(), headers=team["h"]["leader"]).status_code == 200

    db_session.execute(
        text("UPDATE iam_workspace_settings SET updated_by = NULL WHERE workspace_id = :ws"),
        {"ws": team["workspace"].id},
    )
    db_session.flush()

    res = api_client.get(CONFIG_RAG, headers=team["h"]["leader"])
    assert res.status_code == 200
    body = res.json()
    assert body["is_default"] is False
    assert body["similarity_threshold"] == 0.72
    assert body["updated_by"] is None
    assert body["updated_by_name"] is None
