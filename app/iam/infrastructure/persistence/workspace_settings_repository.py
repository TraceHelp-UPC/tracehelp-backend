"""Implementación SQLAlchemy del repositorio de WorkspaceSettings (US07, T62).

No hace commit: lo controla la capa de aplicación para coordinar la invalidación de caché después del commit.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.iam.domain.repositories import IWorkspaceSettingsRepository
from app.iam.domain.workspace_settings import WorkspaceSettings
from app.iam.infrastructure.persistence.models import WorkspaceSettingsModel


def _to_decimal(value: float | None) -> Decimal | None:
    return Decimal(f"{value:.2f}") if value is not None else None


def _to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


class SqlAlchemyWorkspaceSettingsRepository(IWorkspaceSettingsRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, workspace_id: uuid.UUID) -> WorkspaceSettings | None:
        stmt = (
            select(WorkspaceSettingsModel)
            .where(WorkspaceSettingsModel.workspace_id == workspace_id)
            .execution_options(populate_existing=True)
        )
        model = self._session.scalars(stmt).one_or_none()
        return self._to_domain(model) if model is not None else None

    def save(self, settings: WorkspaceSettings) -> WorkspaceSettings:
        updated_at = settings.updated_at or datetime.now(UTC)
        values = {
            "workspace_id": settings.workspace_id,
            "similarity_threshold": _to_decimal(settings.similarity_threshold),
            "self_service_threshold": _to_decimal(settings.self_service_threshold),
            "retrieval_top_k": settings.retrieval_top_k,
            "strict_grounding": settings.strict_grounding,
            "updated_at": updated_at,
            "updated_by": settings.updated_by,
        }
        stmt = pg_insert(WorkspaceSettingsModel).values(**values).on_conflict_do_update(
            index_elements=[WorkspaceSettingsModel.workspace_id],
            set_={
                "similarity_threshold": values["similarity_threshold"],
                "self_service_threshold": values["self_service_threshold"],
                "retrieval_top_k": values["retrieval_top_k"],
                "strict_grounding": values["strict_grounding"],
                "updated_at": values["updated_at"],
                "updated_by": values["updated_by"],
            },
        )
        self._session.execute(stmt)
        self._session.flush()
        settings.updated_at = updated_at
        return settings

    @staticmethod
    def _to_domain(model: WorkspaceSettingsModel) -> WorkspaceSettings:
        return WorkspaceSettings(
            workspace_id=model.workspace_id,
            similarity_threshold=_to_float(model.similarity_threshold),
            self_service_threshold=_to_float(model.self_service_threshold),
            retrieval_top_k=model.retrieval_top_k,
            strict_grounding=model.strict_grounding,
            updated_at=model.updated_at,
            updated_by=model.updated_by,
        )
