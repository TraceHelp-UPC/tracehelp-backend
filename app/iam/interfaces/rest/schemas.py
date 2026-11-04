"""DTOs de entrada y salida del contexto IAM."""
import uuid

from pydantic import BaseModel, Field

from app.iam.domain.user import User


class LoginRequest(BaseModel):
    email: str = Field(..., examples=["karim.ramirez@empresa.pe"])
    password: str = Field(..., min_length=1, examples=["Segura123"])


class AuthenticatedUser(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    full_name: str
    email: str
    role: str
    permissions: list[str]

    @classmethod
    def from_domain(cls, user: User) -> "AuthenticatedUser":
        return cls(
            id=user.id,
            workspace_id=user.workspace_id,
            full_name=user.full_name,
            email=user.email.value,
            role=user.role.value,
            permissions=sorted(p.value for p in user.role_permission.permissions),
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
