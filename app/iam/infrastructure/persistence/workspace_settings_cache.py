"""Caché en memoria por workspace para WorkspaceSettings (US07, T62).

Protegida con threading.Lock porque el worker de triaje corre en hilos paralelos dentro del mismo proceso.
Tiene un TTL de seguridad de 60 s y debe invalidarse siempre DESPUÉS del commit del guardado.
"""
import threading
import time
import uuid
from collections.abc import Callable

from app.iam.domain.workspace_settings import WorkspaceSettings

DEFAULT_CACHE_TTL_SECONDS = 60.0


def _clone(settings: WorkspaceSettings) -> WorkspaceSettings:
    """Devuelve una copia independiente para evitar mutaciones accidentales sobre la entrada en caché."""
    return WorkspaceSettings(
        workspace_id=settings.workspace_id,
        similarity_threshold=settings.similarity_threshold,
        self_service_threshold=settings.self_service_threshold,
        retrieval_top_k=settings.retrieval_top_k,
        strict_grounding=settings.strict_grounding,
        updated_at=settings.updated_at,
        updated_by=settings.updated_by,
    )


class WorkspaceSettingsCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[uuid.UUID, tuple[WorkspaceSettings, float]] = {}

    def get(self, workspace_id: uuid.UUID) -> WorkspaceSettings | None:
        now = self._clock()
        with self._lock:
            entry = self._entries.get(workspace_id)
            if entry is None:
                return None
            settings, expires_at = entry
            if now >= expires_at:
                self._entries.pop(workspace_id, None)
                return None
            return _clone(settings)

    def set(self, workspace_id: uuid.UUID, settings: WorkspaceSettings) -> None:
        expires_at = self._clock() + self._ttl_seconds
        snapshot = _clone(settings)
        with self._lock:
            self._entries[workspace_id] = (snapshot, expires_at)

    def invalidate(self, workspace_id: uuid.UUID) -> None:
        """Elimina la entrada del workspace. Llamar siempre después del commit de la transacción."""
        with self._lock:
            self._entries.pop(workspace_id, None)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


workspace_settings_cache = WorkspaceSettingsCache()


def get_workspace_settings_cache() -> WorkspaceSettingsCache:
    return workspace_settings_cache
