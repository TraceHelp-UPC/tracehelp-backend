"""Agregado User del contexto IAM."""
import uuid
from datetime import UTC, datetime

from app.iam.domain.enums import AvailabilityStatus, RoleName, UserStatus
from app.iam.domain.events import UserAuthenticated, UserRegistered
from app.iam.domain.exceptions import InactiveUserError, InvalidRoleOperationError, InvalidUserDataError
from app.iam.domain.permissions import Permission, RolePermission
from app.iam.domain.value_objects import EmailAddress, PasswordHash
from app.shared.domain.aggregate_root import AggregateRoot

SUPPORT_ROLES = frozenset({RoleName.ANALYST_L1, RoleName.SPECIALIST_L2})


def _now() -> datetime:
    return datetime.now(UTC)


class User(AggregateRoot):
    """Identidad, rol y estado de un usuario corporativo."""

    def __init__(
        self,
        *,
        id: uuid.UUID,
        workspace_id: uuid.UUID,
        full_name: str,
        email: EmailAddress,
        password_hash: PasswordHash,
        role: RoleName,
        department: str,
        status: UserStatus = UserStatus.ACTIVE,
        availability_status: AvailabilityStatus = AvailabilityStatus.AVAILABLE,
        notify_email: bool = True,
        notify_inapp: bool = True,
        created_at: datetime | None = None,
        last_login_at: datetime | None = None,
    ) -> None:
        super().__init__()
        self.id = id
        self.workspace_id = workspace_id
        self.full_name = full_name
        self.email = email
        self.password_hash = password_hash
        self.role = role
        self.department = department
        self.status = status
        self.availability_status = availability_status
        self.notify_email = notify_email
        self.notify_inapp = notify_inapp
        self.created_at = created_at or _now()
        self.last_login_at = last_login_at

    # ------------------------------------------------------------------ fábrica
    @classmethod
    def register(
        cls,
        *,
        workspace_id: uuid.UUID,
        full_name: str,
        email: EmailAddress,
        password_hash: PasswordHash,
        role: RoleName,
        department: str,
    ) -> "User":
        """Crea un usuario activo y emite UserRegistered (US09)."""
        full_name = (full_name or "").strip()
        department = (department or "").strip()
        if not full_name:
            raise InvalidUserDataError("El nombre completo es obligatorio.")
        if len(full_name) > 150:
            raise InvalidUserDataError("El nombre completo no puede superar los 150 caracteres.")
        if not department:
            raise InvalidUserDataError("El área o departamento es obligatorio.")

        user = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            role=role,
            department=department,
        )
        user.record_event(UserRegistered(user_id=user.id, workspace_id=workspace_id, role=role))
        return user

    # ------------------------------------------------------------------ consultas
    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE

    @property
    def is_support_staff(self) -> bool:
        return self.role in SUPPORT_ROLES

    @property
    def role_permission(self) -> RolePermission:
        return RolePermission.for_role(self.role)

    def has_permission(self, permission: Permission) -> bool:
        return self.is_active and self.role_permission.allows(permission)

    # ------------------------------------------------------------------ comportamiento
    def record_login(self) -> None:
        """Registra un inicio de sesión exitoso. Solo los usuarios activos pueden autenticarse."""
        if not self.is_active:
            raise InactiveUserError("La cuenta no está activa. Contacta al líder de TI de tu organización.")
        self.last_login_at = _now()
        self.record_event(UserAuthenticated(user_id=self.id, workspace_id=self.workspace_id))

    def change_role(self, new_role: RoleName) -> None:
        self.role = new_role
        if not self.is_support_staff:
            self.availability_status = AvailabilityStatus.AVAILABLE

    def set_availability(self, availability: AvailabilityStatus) -> None:
        """Disponibilidad para la asignación automática de tickets (US24). Solo aplica a analistas y especialistas."""
        if not self.is_support_staff:
            raise InvalidRoleOperationError("Solo los analistas L1 y especialistas L2 gestionan su disponibilidad.")
        self.availability_status = availability

    def deactivate(self) -> None:
        self.status = UserStatus.INACTIVE

    def activate(self) -> None:
        self.status = UserStatus.ACTIVE
