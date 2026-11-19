"""Construcción de servicios de IAM para los endpoints (inyección de dependencias de FastAPI)."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.iam.application.authentication_service import AuthenticationService
from app.iam.application.user_admin_service import UserAdministrationService
from app.iam.application.workspace_settings_service import WorkspaceSettingsService
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.infrastructure.persistence.workspace_settings_cache import get_workspace_settings_cache
from app.iam.infrastructure.persistence.workspace_settings_repository import SqlAlchemyWorkspaceSettingsRepository
from app.iam.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.iam.infrastructure.security.jwt_token_provider import JwtTokenProvider
from app.iam.infrastructure.security.temporary_password_generator import SecretsTemporaryPasswordGenerator
from app.shared.infrastructure.event_bus import InMemoryEventBus, get_event_bus


def get_token_provider() -> JwtTokenProvider:
    settings = get_settings()
    return JwtTokenProvider(
        secret_key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
        access_minutes=settings.access_token_expire_minutes,
        refresh_days=settings.refresh_token_expire_days,
    )


def get_authentication_service(
    db: Session = Depends(get_db),
    tokens: JwtTokenProvider = Depends(get_token_provider),
    bus: InMemoryEventBus = Depends(get_event_bus),
) -> AuthenticationService:
    return AuthenticationService(
        session=db,
        users=SqlAlchemyUserRepository(db),
        hasher=BcryptPasswordHasher(),
        tokens=tokens,
        events=bus,
    )


def get_user_repository(db: Session = Depends(get_db)) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(db)


def get_user_administration_service(
    db: Session = Depends(get_db),
    bus: InMemoryEventBus = Depends(get_event_bus),
) -> UserAdministrationService:
    return UserAdministrationService(
        session=db,
        users=SqlAlchemyUserRepository(db),
        hasher=BcryptPasswordHasher(),
        password_generator=SecretsTemporaryPasswordGenerator(),
        events=bus,
    )


def get_workspace_settings_service(
    db: Session = Depends(get_db),
    bus: InMemoryEventBus = Depends(get_event_bus),
) -> WorkspaceSettingsService:
    return WorkspaceSettingsService(
        session=db,
        settings_repository=SqlAlchemyWorkspaceSettingsRepository(db),
        users=SqlAlchemyUserRepository(db),
        cache=get_workspace_settings_cache(),
        events=bus,
    )
