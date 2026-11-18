"""Nombres de usuario desde IAM para mostrar quién revisó un diagnóstico."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.iam.infrastructure.persistence.models import UserModel
from app.smart_triage.application.ports import IUserNames


class IamUserNames(IUserNames):
    def __init__(self, session: Session) -> None:
        self._session = session

    def display_names(self, user_ids) -> dict[uuid.UUID, str]:
        ids = {i for i in user_ids if i is not None}
        if not ids:
            return {}
        rows = self._session.execute(select(UserModel.id, UserModel.full_name).where(UserModel.id.in_(ids)))
        return {row.id: row.full_name for row in rows}
