"""Contratos de persistencia del contexto IAM."""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.iam.domain.enums import RoleName
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress
from app.iam.domain.workspace_settings import WorkspaceSettings
from app.shared.domain.pagination import Page, PageRequest
from app.shared.domain.specialist_group import SpecialistGroup


@dataclass(frozen=True)
class UserSearchCriteria:
    """Filtros del listado de usuarios (US09). `is_active=False` incluye INACTIVE y LOCKED."""

    workspace_id: uuid.UUID
    role: RoleName | None = None
    specialist_group: SpecialistGroup | None = None
    is_active: bool | None = None
    search: str | None = None


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

    @abstractmethod
    def search(self, criteria: UserSearchCriteria, page: PageRequest) -> Page[User]:
        """Usuarios del workspace ordenados por nombre y luego id."""


class IWorkspaceSettingsRepository(ABC):
    @abstractmethod
    def get(self, workspace_id: uuid.UUID) -> WorkspaceSettings | None:
        """Devuelve la configuración guardada del workspace, o None si no tiene fila."""

    @abstractmethod
    def save(self, settings: WorkspaceSettings) -> WorkspaceSettings:
        """Inserta o actualiza (upsert) la configuración del workspace sin hacer commit."""
