"""Servicio de aplicación para consultar y actualizar la configuración por workspace (US07, T63).

Coordina el agregado WorkspaceSettings, el repositorio, la invalidación de caché DESPUÉS del commit
y la publicación de eventos de dominio (ConfigurationChanged) hacia la bitácora de auditoría.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.iam.application.workspace_settings_reader import default_rag_settings
from app.iam.domain.repositories import IUserRepository, IWorkspaceSettingsRepository
from app.iam.domain.workspace_settings import RagSettings, WorkspaceSettings
from app.iam.infrastructure.persistence.workspace_settings_cache import (
    WorkspaceSettingsCache,
    get_workspace_settings_cache,
)
from app.shared.infrastructure.event_bus import InMemoryEventBus


@dataclass(frozen=True)
class UpdateRagSettingsCommand:
    workspace_id: uuid.UUID
    changed_by: uuid.UUID
    similarity_threshold: float | Decimal
    self_service_threshold: float | Decimal
    retrieval_top_k: int
    strict_grounding: bool


@dataclass(frozen=True)
class RagSettingsView:
    rag: RagSettings
    defaults: RagSettings
    is_default: bool
    updated_at: datetime | None
    updated_by: uuid.UUID | None
    updated_by_name: str | None


class WorkspaceSettingsService:
    def __init__(
        self,
        session: Session,
        settings_repository: IWorkspaceSettingsRepository,
        users: IUserRepository,
        *,
        cache: WorkspaceSettingsCache | None = None,
        events: InMemoryEventBus | None = None,
        defaults: RagSettings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings_repository
        self._users = users
        self._cache = cache if cache is not None else get_workspace_settings_cache()
        self._events = events
        self._defaults = defaults

    def get_rag(self, workspace_id: uuid.UUID) -> RagSettingsView:
        defaults = self._defaults or default_rag_settings()
        stored = self._settings.get(workspace_id)
        settings = stored if stored is not None else WorkspaceSettings.empty(workspace_id)
        return self._to_view(settings, defaults)

    def update_rag(self, command: UpdateRagSettingsCommand) -> RagSettingsView:
        defaults = self._defaults or default_rag_settings()
        stored = self._settings.get(command.workspace_id)
        settings = stored if stored is not None else WorkspaceSettings.empty(command.workspace_id)

        new_rag = RagSettings(
            similarity_threshold=command.similarity_threshold,
            self_service_threshold=command.self_service_threshold,
            retrieval_top_k=command.retrieval_top_k,
            strict_grounding=command.strict_grounding,
        )
        changed = settings.update_rag(new_rag, changed_by=command.changed_by, defaults=defaults)
        if changed:
            self._settings.save(settings)
            events = settings.pull_events()
            self._session.commit()
            # Invalidar siempre DESPUÉS del commit para que ningún hilo concurrente recargue el valor viejo (D26)
            self._cache.invalidate(command.workspace_id)
            if self._events is not None:
                self._events.publish_all(events)

        return self._to_view(settings, defaults)

    def _to_view(self, settings: WorkspaceSettings, defaults: RagSettings) -> RagSettingsView:
        effective = settings.effective_rag(defaults)
        if settings.is_rag_default:
            return RagSettingsView(
                rag=effective,
                defaults=defaults,
                is_default=True,
                updated_at=None,
                updated_by=None,
                updated_by_name=None,
            )

        updated_by_name = self._resolve_user_name(settings.updated_by)
        return RagSettingsView(
            rag=effective,
            defaults=defaults,
            is_default=False,
            updated_at=settings.updated_at,
            updated_by=settings.updated_by,
            updated_by_name=updated_by_name,
        )

    def _resolve_user_name(self, user_id: uuid.UUID | None) -> str | None:
        if user_id is None:
            return None
        user = self._users.find_by_id(user_id)
        return user.full_name if user is not None else None
