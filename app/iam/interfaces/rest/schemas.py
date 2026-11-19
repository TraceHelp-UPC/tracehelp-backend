"""DTOs de entrada y salida del contexto IAM."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticCustomError

from app.iam.application.workspace_settings_service import RagSettingsView
from app.iam.domain.enums import AvailabilityStatus, RoleName, UserStatus
from app.iam.domain.user import User
from app.iam.domain.workspace_settings import (
    MAX_RETRIEVAL_TOP_K,
    MAX_SELF_SERVICE_THRESHOLD,
    MAX_SIMILARITY_THRESHOLD,
    MIN_RETRIEVAL_TOP_K,
    MIN_SIMILARITY_THRESHOLD,
    SIMILARITY_WARNING_BELOW,
)
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


# ----------------------------------------------------------------------------- configuración del workspace (US07)
class RagDefaultsResponse(BaseModel):
    similarity_threshold: float
    self_service_threshold: float
    retrieval_top_k: int
    strict_grounding: bool


class SimilarityThresholdLimits(BaseModel):
    min: float = MIN_SIMILARITY_THRESHOLD
    max: float = MAX_SIMILARITY_THRESHOLD
    step: float = 0.01
    warning_below: float = SIMILARITY_WARNING_BELOW


class SelfServiceThresholdLimits(BaseModel):
    min: str = "similarity_threshold"
    max: float = MAX_SELF_SERVICE_THRESHOLD
    step: float = 0.01


class RetrievalTopKLimits(BaseModel):
    min: int = MIN_RETRIEVAL_TOP_K
    max: int = MAX_RETRIEVAL_TOP_K


class RagLimitsResponse(BaseModel):
    similarity_threshold: SimilarityThresholdLimits = Field(default_factory=SimilarityThresholdLimits)
    self_service_threshold: SelfServiceThresholdLimits = Field(default_factory=SelfServiceThresholdLimits)
    retrieval_top_k: RetrievalTopKLimits = Field(default_factory=RetrievalTopKLimits)


class RagSettingsResponse(BaseModel):
    """Configuración efectiva del motor RAG del workspace (D26). Los umbrales se serializan como float JSON."""

    similarity_threshold: float = Field(
        ..., description="Umbral mínimo de similitud para fundamentar respuestas RAG (0.50 a 0.95)"
    )
    self_service_threshold: float = Field(
        ..., description="Umbral mínimo de confianza para proponer autoservicio directo (≥ similarity_threshold y ≤ 0.99)"
    )
    retrieval_top_k: int = Field(..., description="Cantidad máxima de fragmentos recuperados por consulta (1 a 10)")
    strict_grounding: bool = Field(
        ..., description="Si es true, descarta toda respuesta de la IA que no cite al menos un fragmento válido"
    )
    is_default: bool = Field(
        ..., description="true si el workspace usa los valores por defecto (sin configuración RAG guardada)"
    )
    updated_at: datetime | None = Field(None, description="Fecha y hora de última modificación (UTC); null si usa defaults")
    updated_by: uuid.UUID | None = Field(None, description="ID del líder que modificó la configuración; null si usa defaults")
    updated_by_name: str | None = Field(None, description="Nombre del usuario que realizó la última modificación")
    defaults: RagDefaultsResponse = Field(..., description="Valores por defecto del motor RAG")
    limits: RagLimitsResponse = Field(
        default_factory=RagLimitsResponse, description="Rangos permitidos y avisos de calibración para la UI"
    )

    @classmethod
    def from_view(cls, view: RagSettingsView) -> "RagSettingsResponse":
        return cls(
            similarity_threshold=float(view.rag.similarity_threshold),
            self_service_threshold=float(view.rag.self_service_threshold),
            retrieval_top_k=view.rag.retrieval_top_k,
            strict_grounding=view.rag.strict_grounding,
            is_default=view.is_default,
            updated_at=view.updated_at,
            updated_by=view.updated_by,
            updated_by_name=view.updated_by_name,
            defaults=RagDefaultsResponse(
                similarity_threshold=float(view.defaults.similarity_threshold),
                self_service_threshold=float(view.defaults.self_service_threshold),
                retrieval_top_k=view.defaults.retrieval_top_k,
                strict_grounding=view.defaults.strict_grounding,
            ),
        )


class UpdateRagSettingsRequest(BaseModel):
    """Cuerpo de PUT /api/v1/config/rag (reemplazo completo de los 4 parámetros RAG)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "similarity_threshold": 0.72,
                    "self_service_threshold": 0.85,
                    "retrieval_top_k": 5,
                    "strict_grounding": True,
                }
            ]
        },
    )

    similarity_threshold: Annotated[
        Decimal,
        Field(
            ge=Decimal("0.50"),
            le=Decimal("0.95"),
            decimal_places=2,
            description="Umbral de fundamentación RAG (entre 0.50 y 0.95, máximo 2 decimales)",
        ),
    ]
    self_service_threshold: Annotated[
        Decimal,
        Field(
            le=Decimal("0.99"),
            decimal_places=2,
            description="Umbral de autoservicio directo (mayor o igual a similarity_threshold y hasta 0.99, máximo 2 decimales)",
        ),
    ]
    retrieval_top_k: Annotated[
        int,
        Field(ge=1, le=10, description="Número máximo de fragmentos de manuales recuperados por consulta (1 a 10)"),
    ]
    strict_grounding: bool = Field(
        ..., description="Si es true, rechaza diagnósticos de la IA sin citas válidas a los manuales"
    )

    @field_validator("self_service_threshold")
    @classmethod
    def _validate_self_service_vs_similarity(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        similarity = info.data.get("similarity_threshold")
        if similarity is not None and value < similarity:
            raise PydanticCustomError(
                "self_service_below_similarity",
                "debe ser mayor o igual que el umbral de fundamentación ({similarity})",
                {"similarity": f"{similarity:.2f}"},
            )
        if similarity is None and value < Decimal("0.50"):
            raise PydanticCustomError(
                "greater_than_equal",
                "debe ser mayor o igual que {ge}",
                {"ge": "0.50"},
            )
        return value
