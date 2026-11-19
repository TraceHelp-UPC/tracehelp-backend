"""DTOs de entrada y salida del contexto IAM."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from app.iam.domain.enums import AvailabilityStatus, RoleName, UserStatus
from app.iam.domain.user import User
from app.shared.domain.pagination import Page
from app.shared.domain.specialist_group import SpecialistGroup


class LoginRequest(BaseModel):
    email: str = Field(..., examples=["karim.ramirez@empresa.pe"])
    password: str = Field(..., min_length=1, examples=["Segura123"])


class AuthenticatedUser(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    full_name: str
    email: str
    role: str
    availability_status: str = "AVAILABLE"
    department: str | None = None
    specialist_group: str | None = Field(None, description="Grupo del especialista L2; null si no aplica")
    permissions: list[str]

    @classmethod
    def from_domain(cls, user: User) -> "AuthenticatedUser":
        return cls(
            id=user.id,
            workspace_id=user.workspace_id,
            full_name=user.full_name,
            email=user.email.value,
            role=user.role.value,
            availability_status=user.availability_status.value,
            department=user.department,
            specialist_group=user.specialist_group.value if user.specialist_group else None,
            permissions=sorted(p.value for p in user.role_permission.permissions),
        )


class UpdateAvailabilityRequest(BaseModel):
    availability_status: AvailabilityStatus = Field(
        ..., description="Nuevo estado de disponibilidad: AVAILABLE o UNAVAILABLE", examples=["UNAVAILABLE"]
    )


class AnalystSummaryResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    full_name: str
    email: str
    role: str
    department: str
    availability_status: str

    @classmethod
    def from_domain(cls, user: User) -> "AnalystSummaryResponse":
        return cls(
            id=user.id,
            workspace_id=user.workspace_id,
            full_name=user.full_name,
            email=user.email.value,
            role=user.role.value,
            department=user.department,
            availability_status=user.availability_status.value,
        )


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Segundos de vigencia del access token")
    user: AuthenticatedUser


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ----------------------------------------------------------------------------- administración de usuarios (US09)
class UserAdminResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    email: str
    role: RoleName
    department: str
    specialist_group: SpecialistGroup | None
    is_active: bool = Field(..., description="true si status es ACTIVE")
    status: UserStatus
    availability_status: AvailabilityStatus
    created_at: datetime
    last_login_at: datetime | None

    @classmethod
    def from_domain(cls, user: User) -> "UserAdminResponse":
        return cls(
            id=user.id,
            full_name=user.full_name,
            email=user.email.value,
            role=user.role,
            department=user.department,
            specialist_group=user.specialist_group,
            is_active=user.is_active,
            status=user.status,
            availability_status=user.availability_status,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        )


class UserAdminPageResponse(BaseModel):
    items: list[UserAdminResponse]
    page: int
    size: int
    total: int
    total_pages: int

    @classmethod
    def from_page(cls, page: Page[User]) -> "UserAdminPageResponse":
        return cls(
            items=[UserAdminResponse.from_domain(u) for u in page.items],
            page=page.page,
            size=page.size,
            total=page.total,
            total_pages=page.total_pages,
        )


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "full_name": "Lucía Torres",
                    "email": "Lucia.Torres@empresa.pe",
                    "role": "SPECIALIST_L2",
                    "department": "Redes y Comunicaciones",
                    "specialist_group": "REDES",
                }
            ]
        },
    )

    full_name: str = Field(..., min_length=1, max_length=150, description="Nombre completo (1 a 150 caracteres)")
    email: str = Field(..., max_length=255, description="Correo corporativo; se guarda en minúsculas y es único")
    role: RoleName = Field(..., description="COLLABORATOR, ANALYST_L1, SPECIALIST_L2 o IT_LEADER")
    department: str = Field(..., min_length=1, max_length=100, description="Área o departamento (1 a 100 caracteres)")
    specialist_group: SpecialistGroup | None = Field(
        None, description="Solo para SPECIALIST_L2: REDES, APLICACIONES, INFRAESTRUCTURA o SEGURIDAD"
    )


class CreatedUserResponse(BaseModel):
    user: UserAdminResponse
    temporary_password: str = Field(..., description="Contraseña temporal. Se muestra una sola vez.")
    password_notice: str = "Esta contraseña se muestra una sola vez. Entrégala al usuario por un canal seguro."


class UpdateUserRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"role": "SPECIALIST_L2", "specialist_group": "SEGURIDAD"}, {"is_active": False}]},
    )

    role: RoleName | None = Field(None, description="Nuevo rol. Si no es SPECIALIST_L2, el grupo se borra.")
    department: str | None = Field(None, min_length=1, max_length=100)
    specialist_group: SpecialistGroup | None = Field(
        None, description="Grupo del especialista; null explícito lo quita; si se omite no se toca"
    )
    is_active: StrictBool | None = Field(None, description="false desactiva la cuenta; true la reactiva")

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "UpdateUserRequest":
        if not self.model_fields_set:
            raise ValueError("Envía al menos un campo para actualizar.")
        for name in ("role", "department", "is_active"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} no puede ser null.")
        return self
