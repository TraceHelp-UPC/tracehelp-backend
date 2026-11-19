"""Casos de uso de administración de usuarios y roles (US09, T69). Los ejecuta el líder de TI (iam:admin)."""
import uuid
from dataclasses import dataclass, field

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.iam.domain.enums import RoleName
from app.iam.domain.exceptions import (
    EmailAlreadyRegisteredError,
    SelfLockoutError,
    UserNotFoundError,
)
from app.iam.domain.repositories import IUserRepository, UserSearchCriteria
from app.iam.domain.services import IPasswordHasher, ITemporaryPasswordGenerator
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress
from app.shared.domain.pagination import Page, PageRequest
from app.shared.domain.specialist_group import SpecialistGroup
from app.shared.infrastructure.event_bus import InMemoryEventBus


@dataclass(frozen=True)
class CreateUserCommand:
    workspace_id: uuid.UUID
    created_by: uuid.UUID
    full_name: str
    email: str
    role: RoleName
    department: str
    specialist_group: SpecialistGroup | None = None


@dataclass(frozen=True)
class CreatedUser:
    user: User
    temporary_password: str = field(repr=False)


@dataclass(frozen=True)
class UpdateUserCommand:
    workspace_id: uuid.UUID
    user_id: uuid.UUID
    changed_by: uuid.UUID
    role: RoleName | None = None
    department: str | None = None
    specialist_group: SpecialistGroup | None = None
    set_specialist_group: bool = False  # True si el cliente envió el campo (permite null = quitar grupo)
    is_active: bool | None = None


class UserAdministrationService:
    def __init__(
        self,
        session: Session,
        users: IUserRepository,
        hasher: IPasswordHasher,
        password_generator: ITemporaryPasswordGenerator,
        events: InMemoryEventBus | None = None,
    ) -> None:
        self._session = session
        self._users = users
        self._hasher = hasher
        self._generator = password_generator
        self._events = events

    def list_users(self, criteria: UserSearchCriteria, page: PageRequest) -> Page[User]:
        return self._users.search(criteria, page)

    def create_user(self, command: CreateUserCommand) -> CreatedUser:
        address = EmailAddress(command.email)
        if self._users.exists_by_email(address):
            raise self._conflict(address)
        temporary = self._generator.generate()
        user = User.register(
            workspace_id=command.workspace_id,
            full_name=command.full_name,
            email=address,
            password_hash=self._hasher.hash(temporary),
            role=command.role,
            department=command.department,
            specialist_group=command.specialist_group,
            registered_by=command.created_by,
        )
        try:
            self._users.save(user)
            events = user.pull_events()
            self._session.commit()
        except IntegrityError as exc:  # alta simultánea que pasó la comprobación previa
            self._session.rollback()
            raise self._conflict(address) from exc
        self._publish(events)
        return CreatedUser(user=user, temporary_password=temporary.value)

    def update_user(self, command: UpdateUserCommand) -> User:
        user = self._users.find_by_id(command.user_id)
        if user is None or user.workspace_id != command.workspace_id:
            raise UserNotFoundError("El usuario no existe.")

        by = command.changed_by
        if command.user_id == by:
            if command.role is not None and command.role is not RoleName.IT_LEADER:
                raise SelfLockoutError("No puedes quitarte tu propio rol de Líder de TI.")
            if command.is_active is False:
                raise SelfLockoutError("No puedes desactivar tu propia cuenta.")

        if command.role is not None:
            user.change_role(command.role, changed_by=by)
        if command.set_specialist_group:
            user.assign_specialist_group(command.specialist_group, changed_by=by)
        if command.department is not None:
            user.change_department(command.department, changed_by=by)
        if command.is_active is True:
            user.activate(changed_by=by)
        elif command.is_active is False:
            user.deactivate(changed_by=by)

        self._users.save(user)
        events = user.pull_events()
        self._session.commit()
        self._publish(events)
        return user

    def _publish(self, events: list) -> None:
        if self._events is not None:
            self._events.publish_all(events)

    @staticmethod
    def _conflict(address: EmailAddress) -> EmailAlreadyRegisteredError:
        return EmailAlreadyRegisteredError(f"Ya existe una cuenta con el correo {address.value}.")
