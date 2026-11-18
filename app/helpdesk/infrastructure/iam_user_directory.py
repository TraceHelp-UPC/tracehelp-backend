"""Adaptador que obtiene los nombres de usuario desde IAM para mostrarlos en las bandejas de Helpdesk.

Es el único punto de Helpdesk que lee datos de IAM; si IAM cambia su almacenamiento, solo cambia este archivo.
"""
import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.helpdesk.application.ports import AnalystAssignmentCandidate, IAnalystAvailabilityReader
from app.helpdesk.application.ticket_queries import IUserDirectory
from app.iam.domain.enums import AvailabilityStatus, UserStatus
from app.iam.domain.user import SUPPORT_ROLES
from app.iam.infrastructure.persistence.models import UserModel


class IamUserDirectory(IUserDirectory, IAnalystAvailabilityReader):
    def __init__(self, session: Session) -> None:
        self._session = session

    def display_names(self, user_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, str]:
        ids = {i for i in user_ids if i is not None}
        if not ids:
            return {}
        rows = self._session.execute(select(UserModel.id, UserModel.full_name).where(UserModel.id.in_(ids)))
        return {row.id: row.full_name for row in rows}

    def get_candidate(self, analyst_id: uuid.UUID) -> AnalystAssignmentCandidate | None:
        model = self._session.get(UserModel, analyst_id)
        if model is None:
            return None
        return AnalystAssignmentCandidate(
            id=model.id,
            workspace_id=model.workspace_id,
            full_name=model.full_name,
            is_active=model.status is UserStatus.ACTIVE,
            is_support_staff=model.role in SUPPORT_ROLES,
            is_available=model.availability_status is AvailabilityStatus.AVAILABLE,
        )
