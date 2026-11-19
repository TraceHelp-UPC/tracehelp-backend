"""Servicio de lectura de WorkspaceSettings con caché en memoria y fallback a valores por defecto (US07, T62).

Lo consumen los adaptadores de otros contextos (como Smart Triage) sin depender de detalles de persistencia de IAM.
"""
import logging
import uuid

from app.core.config import Settings, get_settings
from app.iam.domain.repositories import IWorkspaceSettingsRepository
from app.iam.domain.workspace_settings import RagSettings, WorkspaceSettings
from app.iam.infrastructure.persistence.workspace_settings_cache import (
    WorkspaceSettingsCache,
    get_workspace_settings_cache,
)

logger = logging.getLogger(__name__)


def default_rag_settings(settings: Settings | None = None) -> RagSettings:
    """Construye los parámetros RAG por defecto a partir de app/core/config.py."""
    cfg = settings or get_settings()
    return RagSettings(
        similarity_threshold=cfg.similarity_threshold,
        self_service_threshold=cfg.self_service_threshold,
        retrieval_top_k=cfg.retrieval_top_k,
        strict_grounding=cfg.strict_grounding,
    )


class WorkspaceSettingsReader:
    def __init__(
        self,
        repository: IWorkspaceSettingsRepository,
        *,
        cache: WorkspaceSettingsCache | None = None,
        defaults: RagSettings | None = None,
    ) -> None:
        self._repository = repository
        self._cache = cache if cache is not None else get_workspace_settings_cache()
        self._defaults = defaults

    def get_for(self, workspace_id: uuid.UUID) -> WorkspaceSettings:
        """Lee el agregado del workspace usando caché en memoria (TTL 60 s)."""
        cached = self._cache.get(workspace_id)
        if cached is not None:
            return cached
        stored = self._repository.get(workspace_id)
        settings = stored if stored is not None else WorkspaceSettings.empty(workspace_id)
        self._cache.set(workspace_id, settings)
        return settings

    def rag_for(self, workspace_id: uuid.UUID) -> RagSettings:
        """Devuelve los parámetros RAG vigentes del workspace.

        Si la base falla al leer la configuración, registra una advertencia y devuelve los valores por defecto
        sin detener el triaje ni cachear el fallo.
        """
        defaults = self._defaults or default_rag_settings()
        try:
            settings = self.get_for(workspace_id)
            return settings.effective_rag(defaults)
        except Exception:  # noqa: BLE001 - el fallo de lectura no debe detener el triaje
            logger.warning(
                "No se pudo leer la configuración RAG del workspace %s; se usan los valores por defecto.",
                workspace_id,
                exc_info=True,
            )
            return defaults
