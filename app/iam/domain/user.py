"""Agregado User del contexto IAM."""
import uuid
from datetime import UTC, datetime

from app.iam.domain.enums import AvailabilityStatus, RoleName, UserStatus
from app.iam.domain.events import (
    UserAuthenticated,
    UserDeactivated,
    UserProfileUpdated,
    UserReactivated,
    UserRegistered,
    UserRoleChanged,
)
from app.iam.domain.exceptions import (
    InactiveUserError,
    InvalidRoleOperationError,
    InvalidUserDataError,
    SpecialistGroupNotAllowedError,
)
from app.iam.domain.permissions import Permission, RolePermission
from app.iam.domain.value_objects import EmailAddress, PasswordHash
from app.shared.domain.aggregate_root import AggregateRoot
from app.shared.domain.specialist_group import SpecialistGroup

SUPPORT_ROLES = frozenset({RoleName.ANALYST_L1, RoleName.SPECIALIST_L2})
MAX_DEPARTMENT_LENGTH = 100


def _now() -> datetime:
    return datetime.now(UTC)


def _clean_department(department: str | None) -> str:
    department = (department or "").strip()
    if not department:
        raise InvalidUserDataError("El área o departamento es obligatorio.")
    if len(department) > MAX_DEPARTMENT_LENGTH:
        raise InvalidUserDataError(f"El área o departamento no puede superar los {MAX_DEPARTMENT_LENGTH} caracteres.")
    return department


def _group_value(group: SpecialistGroup | None) -> str | None:
    return group.value if group is not None else None


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
        specialist_group: SpecialistGroup | None = None,
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
        self.specialist_group = specialist_group

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
        specialist_group: SpecialistGroup | None = None,
        registered_by: uuid.UUID | None = None,
    ) -> "User":
        """Crea un usuario activo y emite UserRegistered (US09). `registered_by` = líder que hizo el alta."""
        full_name = (full_name or "").strip()
        if not full_name:
            raise InvalidUserDataError("El nombre completo es obligatorio.")
        if len(full_name) > 150:
            raise InvalidUserDataError("El nombre completo no puede superar los 150 caracteres.")
        department = _clean_department(department)
        if specialist_group is not None and role is not RoleName.SPECIALIST_L2:
            raise SpecialistGroupNotAllowedError("Solo los especialistas L2 pueden tener un grupo asignado.")

        user = cls(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            role=role,
            department=department,
            specialist_group=specialist_group,
        )
        user.record_event(
            UserRegistered(
                user_id=user.id,
                workspace_id=workspace_id,
                role=role,
                specialist_group=_group_value(specialist_group),
                registered_by=registered_by,
            )
        )
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

    def change_role(self, new_role: RoleName, changed_by: uuid.UUID | None = None) -> None:
        """Cambia el rol. Si el nuevo rol no es SPECIALIST_L2, el grupo se borra en la misma operación."""
        if new_role is self.role:
            return
        previous_role = self.role
        previous_group = self.specialist_group
        self.role = new_role
        if not self.is_support_staff:
            self.availability_status = AvailabilityStatus.AVAILABLE
        self.record_event(
            UserRoleChanged(
                user_id=self.id,
                workspace_id=self.workspace_id,
                changed_by=changed_by,
                previous_role=previous_role,
                new_role=new_role,
            )
        )
        if new_role is not RoleName.SPECIALIST_L2 and previous_group is not None:
            self.specialist_group = None
            self._record_profile_change(changed_by, {"specialist_group": {"from": previous_group.value, "to": None}})

    def change_department(self, department: str, changed_by: uuid.UUID | None = None) -> None:
        department = _clean_department(department)
        if department == self.department:
            return
        previous = self.department
        self.department = department
        self._record_profile_change(changed_by, {"department": {"from": previous, "to": department}})

    def assign_specialist_group(self, group: SpecialistGroup | None, changed_by: uuid.UUID | None = None) -> None:
        """Asigna o quita (None) el grupo del especialista. Solo el rol SPECIALIST_L2 puede tener grupo."""
        if group is not None and self.role is not RoleName.SPECIALIST_L2:
            raise SpecialistGroupNotAllowedError("Solo los especialistas L2 pueden tener un grupo asignado.")
        if group is self.specialist_group:
            return
        previous = self.specialist_group
        self.specialist_group = group
        self._record_profile_change(
            changed_by, {"specialist_group": {"from": _group_value(previous), "to": _group_value(group)}}
        )

    def _record_profile_change(self, changed_by: uuid.UUID | None, changes: dict[str, dict[str, str | None]]) -> None:
        self.record_event(
            UserProfileUpdated(user_id=self.id, workspace_id=self.workspace_id, changed_by=changed_by, changes=changes)
        )

    def update_notification_preferences(
        self,
        *,
        notify_inapp: bool | None = None,
        notify_email: bool | None = None,
        changed_by: uuid.UUID | None = None,
    ) -> None:
        """Actualiza los canales de notificación (US19) y publica UserProfileUpdated solo si hubo cambios."""
        changes: dict[str, dict[str, str | None]] = {}
        if notify_inapp is not None and notify_inapp != self.notify_inapp:
            changes["notify_inapp"] = {"from": str(self.notify_inapp).lower(), "to": str(notify_inapp).lower()}
            self.notify_inapp = notify_inapp
        if notify_email is not None and notify_email != self.notify_email:
            changes["notify_email"] = {"from": str(self.notify_email).lower(), "to": str(notify_email).lower()}
            self.notify_email = notify_email
        if changes:
            self._record_profile_change(changed_by, changes)

    def set_availability(self, availability: AvailabilityStatus) -> None:
        """Disponibilidad para la asignación automática de tickets (US24). Solo aplica a analistas y especialistas."""
        if not self.is_support_staff:
            raise InvalidRoleOperationError("Solo los analistas L1 y especialistas L2 gestionan su disponibilidad.")
        self.availability_status = availability

    def deactivate(self, changed_by: uuid.UUID | None = None) -> None:
        """Deja la cuenta INACTIVE y no disponible, para que la asignación automática no le reparta tickets."""
        if self.status is UserStatus.INACTIVE:
            return
        self.status = UserStatus.INACTIVE
        self.availability_status = AvailabilityStatus.UNAVAILABLE
        self.record_event(UserDeactivated(user_id=self.id, workspace_id=self.workspace_id, changed_by=changed_by))

    def activate(self, changed_by: uuid.UUID | None = None) -> None:
        """Reactiva la cuenta. La disponibilidad sigue en UNAVAILABLE: la vuelve a activar el propio analista."""
        if self.status is UserStatus.ACTIVE:
            return
        self.status = UserStatus.ACTIVE
        self.record_event(UserReactivated(user_id=self.id, workspace_id=self.workspace_id, changed_by=changed_by))
