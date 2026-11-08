"""Contrato de persistencia del agregado User."""
import uuid
from abc import ABC, abstractmethod

from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress


class IUserRepository(ABC):
    @abstractmethod
    def save(self, user: User) -> User:
        """Inserta o actualiza el usuario."""

    @abstractmethod
    def find_by_id(self, user_id: uuid.UUID) -> User | None: ...

    @abstractmethod
    def find_by_email(self, email: EmailAddress) -> User | None: ...

    @abstractmethod
    def exists_by_email(self, email: EmailAddress) -> bool: ...

    @abstractmethod
    def find_support_staff_by_workspace(self, workspace_id: uuid.UUID) -> list[User]: ...
