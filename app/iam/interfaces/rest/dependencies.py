"""Construcción de servicios de IAM para los endpoints (inyección de dependencias de FastAPI)."""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.iam.application.authentication_service import AuthenticationService
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.iam.infrastructure.security.jwt_token_provider import JwtTokenProvider


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
) -> AuthenticationService:
    return AuthenticationService(
        session=db,
        users=SqlAlchemyUserRepository(db),
        hasher=BcryptPasswordHasher(),
        tokens=tokens,
    )


def get_user_repository(db: Session = Depends(get_db)) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(db)
