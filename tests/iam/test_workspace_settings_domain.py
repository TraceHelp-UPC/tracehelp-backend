"""Pruebas unitarias del agregado WorkspaceSettings, caché, lector y validación de defaults (US07, T62)."""
import logging
import threading
import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.iam.application.workspace_settings_reader import WorkspaceSettingsReader
from app.iam.domain.events import ConfigurationChanged
from app.iam.domain.exceptions import InvalidWorkspaceSettingsError
from app.iam.domain.repositories import IWorkspaceSettingsRepository
from app.iam.domain.workspace_settings import RagSettings, WorkspaceSettings
from app.iam.infrastructure.persistence.workspace_settings_cache import WorkspaceSettingsCache

DEFAULTS = RagSettings(
    similarity_threshold=0.68,
    self_service_threshold=0.80,
    retrieval_top_k=5,
    strict_grounding=True,
)


# --- RagSettings value object -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sim", "ss", "top_k", "strict"),
    [
        (0.50, 0.50, 1, True),
        (0.95, 0.99, 10, False),
        (0.64, 0.70, 5, True),  # bajo 0.65 es válido (solo muestra aviso en UI)
        (Decimal("0.72"), Decimal("0.85"), 7, True),
        (0.700, 0.800, 3, False),
    ],
)
def test_rag_settings_accepts_valid_boundaries(sim, ss, top_k, strict):
    rag = RagSettings(
        similarity_threshold=sim,
        self_service_threshold=ss,
        retrieval_top_k=top_k,
        strict_grounding=strict,
    )
    assert isinstance(rag.similarity_threshold, float)
    assert isinstance(rag.self_service_threshold, float)
    assert rag.similarity_threshold == float(sim)
    assert rag.self_service_threshold == float(ss)
    assert rag.retrieval_top_k == top_k
    assert rag.strict_grounding is strict


@pytest.mark.parametrize(
    ("sim", "ss", "top_k", "strict"),
    [
        (0.30, 0.80, 5, True),  # similarity < 0.50
        (0.49, 0.80, 5, True),
        (0.96, 0.99, 5, True),  # similarity > 0.95
        (0.725, 0.80, 5, True),  # > 2 decimales
        (Decimal("0.681"), 0.80, 5, True),
        (0.75, 0.70, 5, True),  # self_service < similarity
        (0.70, 1.00, 5, True),  # self_service > 0.99
        (0.70, 0.855, 5, True),  # self_service > 2 decimales
        (0.68, 0.80, 0, True),  # top_k < 1
        (0.68, 0.80, -2, True),
        (0.68, 0.80, 11, True),  # top_k > 10
        (0.68, 0.80, 5.0, True),  # top_k no entero
        (0.68, 0.80, True, True),  # bool como top_k
        (True, 0.80, 5, True),  # bool como similarity
        (float("nan"), 0.80, 5, True),
        (float("inf"), 0.80, 5, True),
        (0.68, 0.80, 5, "true"),  # strict_grounding no bool
    ],
)
def test_rag_settings_rejects_invalid_values(sim, ss, top_k, strict):
    with pytest.raises(InvalidWorkspaceSettingsError):
        RagSettings(
            similarity_threshold=sim,
            self_service_threshold=ss,
            retrieval_top_k=top_k,
            strict_grounding=strict,
        )


# --- WorkspaceSettings aggregate ----------------------------------------------------------------------------


def test_empty_workspace_settings_uses_defaults():
    ws_id = uuid.uuid4()
    ws = WorkspaceSettings.empty(ws_id)
    assert ws.is_rag_default is True
    assert ws.updated_at is None
    assert ws.updated_by is None
    assert ws.effective_rag(DEFAULTS) == DEFAULTS


def test_partial_null_settings_fallback_field_by_field():
    ws = WorkspaceSettings(workspace_id=uuid.uuid4(), similarity_threshold=0.72, strict_grounding=False)
    assert ws.is_rag_default is False
    effective = ws.effective_rag(DEFAULTS)
    assert effective == RagSettings(
        similarity_threshold=0.72,
        self_service_threshold=0.80,
        retrieval_top_k=5,
        strict_grounding=False,
    )


def test_update_rag_from_defaults_records_only_changed_fields():
    ws_id, leader_id = uuid.uuid4(), uuid.uuid4()
    ws = WorkspaceSettings.empty(ws_id)
    new_rag = RagSettings(0.72, 0.85, 5, False)

    changed = ws.update_rag(new_rag, changed_by=leader_id, defaults=DEFAULTS)

    assert changed is True
    assert ws.is_rag_default is False
    assert ws.updated_by == leader_id
    assert ws.updated_at is not None
    assert ws.effective_rag(DEFAULTS) == new_rag

    [event] = ws.pull_events()
    assert isinstance(event, ConfigurationChanged)
    assert event.workspace_id == ws_id
    assert event.changed_by == leader_id
    assert event.section == "rag"
    assert event.changes == {
        "similarity_threshold": {"old": 0.68, "new": 0.72},
        "self_service_threshold": {"old": 0.80, "new": 0.85},
        "strict_grounding": {"old": True, "new": False},
    }
    assert "retrieval_top_k" not in event.changes


def test_update_rag_without_effective_changes_is_noop():
    ws_id, leader_id = uuid.uuid4(), uuid.uuid4()
    ws = WorkspaceSettings.empty(ws_id)

    # Guardar los mismos defaults sobre un workspace vacío no cambia nada
    assert ws.update_rag(DEFAULTS, changed_by=leader_id, defaults=DEFAULTS) is False
    assert ws.pull_events() == []
    assert ws.updated_at is None
    assert ws.is_rag_default is True

    # Guardar un cambio real y luego repetir el mismo valor tampoco emite evento ni cambia updated_at
    custom = RagSettings(0.75, 0.88, 7, True)
    assert ws.update_rag(custom, changed_by=leader_id, defaults=DEFAULTS) is True
    ws.pull_events()
    first_updated_at = ws.updated_at

    assert ws.update_rag(custom, changed_by=uuid.uuid4(), defaults=DEFAULTS) is False
    assert ws.pull_events() == []
    assert ws.updated_at == first_updated_at
    assert ws.updated_by == leader_id


def test_update_rag_reset_to_defaults_records_change():
    ws_id, leader_id = uuid.uuid4(), uuid.uuid4()
    ws = WorkspaceSettings.empty(ws_id)
    ws.update_rag(RagSettings(0.75, 0.80, 5, True), changed_by=leader_id, defaults=DEFAULTS)
    ws.pull_events()

    changed = ws.update_rag(DEFAULTS, changed_by=leader_id, defaults=DEFAULTS)
    assert changed is True
    [event] = ws.pull_events()
    assert event.changes == {"similarity_threshold": {"old": 0.75, "new": 0.68}}


# --- Settings startup validation ----------------------------------------------------------------------------


def test_app_settings_defaults_are_valid():
    cfg = Settings()
    assert cfg.strict_grounding is True
    assert RagSettings(
        similarity_threshold=cfg.similarity_threshold,
        self_service_threshold=cfg.self_service_threshold,
        retrieval_top_k=cfg.retrieval_top_k,
        strict_grounding=cfg.strict_grounding,
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"similarity_threshold": 0.30},
        {"similarity_threshold": 0.96},
        {"similarity_threshold": 0.85, "self_service_threshold": 0.80},
        {"self_service_threshold": 1.00},
        {"retrieval_top_k": 0},
        {"retrieval_top_k": 11},
    ],
)
def test_app_settings_rejects_invalid_rag_defaults_on_startup(overrides):
    with pytest.raises(ValidationError, match="Configuración RAG por defecto no válida"):
        Settings(**overrides)


# --- WorkspaceSettingsCache ---------------------------------------------------------------------------------


def test_cache_respects_ttl_invalidation_and_immutability():
    now = [100.0]
    cache = WorkspaceSettingsCache(ttl_seconds=60.0, clock=lambda: now[0])
    ws1, ws2 = uuid.uuid4(), uuid.uuid4()
    s1 = WorkspaceSettings(workspace_id=ws1, similarity_threshold=0.72, self_service_threshold=0.85, retrieval_top_k=6, strict_grounding=True)
    s2 = WorkspaceSettings(workspace_id=ws2, similarity_threshold=0.60, self_service_threshold=0.75, retrieval_top_k=4, strict_grounding=False)

    assert cache.get(ws1) is None
    cache.set(ws1, s1)
    cache.set(ws2, s2)

    hit = cache.get(ws1)
    assert hit is not None and hit.similarity_threshold == 0.72
    # Mutar la copia devuelta no corrompe el valor en caché
    hit.similarity_threshold = 0.90
    assert cache.get(ws1).similarity_threshold == 0.72

    # Justo antes del TTL sigue vigente
    now[0] = 159.9
    assert cache.get(ws1) is not None

    # Invalidar ws1 no afecta a ws2
    cache.invalidate(ws1)
    assert cache.get(ws1) is None
    assert cache.get(ws2) is not None

    # Al vencer el TTL expira ws2
    now[0] = 160.0
    assert cache.get(ws2) is None


def test_cache_is_thread_safe():
    cache = WorkspaceSettingsCache(ttl_seconds=60.0)
    ws_id = uuid.uuid4()
    errors: list[Exception] = []

    def worker(idx: int) -> None:
        try:
            for step in range(50):
                sim = 0.50 + ((idx + step) % 40) / 100
                cache.set(ws_id, WorkspaceSettings(workspace_id=ws_id, similarity_threshold=round(sim, 2)))
                cache.get(ws_id)
                if step % 10 == 0:
                    cache.invalidate(ws_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []


# --- WorkspaceSettingsReader --------------------------------------------------------------------------------


class InMemoryWorkspaceSettingsRepository(IWorkspaceSettingsRepository):
    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, WorkspaceSettings] = {}
        self.get_calls = 0
        self.fail_on_get = False

    def get(self, workspace_id: uuid.UUID) -> WorkspaceSettings | None:
        self.get_calls += 1
        if self.fail_on_get:
            raise RuntimeError("conexión perdida")
        return self.rows.get(workspace_id)

    def save(self, settings: WorkspaceSettings) -> WorkspaceSettings:
        self.rows[settings.workspace_id] = settings
        return settings


def test_reader_caches_reads_and_refreshes_after_invalidation():
    ws_id = uuid.uuid4()
    repo = InMemoryWorkspaceSettingsRepository()
    cache = WorkspaceSettingsCache(ttl_seconds=60.0)
    reader = WorkspaceSettingsReader(repo, cache=cache, defaults=DEFAULTS)

    assert reader.rag_for(ws_id) == DEFAULTS
    assert reader.rag_for(ws_id) == DEFAULTS
    assert repo.get_calls == 1

    updated = WorkspaceSettings(
        workspace_id=ws_id,
        similarity_threshold=0.74,
        self_service_threshold=0.88,
        retrieval_top_k=8,
        strict_grounding=False,
    )
    repo.save(updated)
    # Sin invalidar sigue sirviendo caché
    assert reader.rag_for(ws_id) == DEFAULTS
    assert repo.get_calls == 1

    cache.invalidate(ws_id)
    assert reader.rag_for(ws_id) == RagSettings(0.74, 0.88, 8, False)
    assert repo.get_calls == 2


def test_reader_falls_back_to_defaults_when_db_fails_without_caching_failure(caplog):
    ws_id = uuid.uuid4()
    repo = InMemoryWorkspaceSettingsRepository()
    repo.save(WorkspaceSettings(workspace_id=ws_id, similarity_threshold=0.77, self_service_threshold=0.90, retrieval_top_k=6, strict_grounding=True))
    repo.fail_on_get = True
    cache = WorkspaceSettingsCache(ttl_seconds=60.0)
    reader = WorkspaceSettingsReader(repo, cache=cache, defaults=DEFAULTS)

    with caplog.at_level(logging.WARNING, logger="app.iam.application.workspace_settings_reader"):
        assert reader.rag_for(ws_id) == DEFAULTS
    assert "valores por defecto" in caplog.text

    # Cuando la BD se recupera, la siguiente lectura obtiene el valor real
    repo.fail_on_get = False
    assert reader.rag_for(ws_id) == RagSettings(0.77, 0.90, 6, True)
