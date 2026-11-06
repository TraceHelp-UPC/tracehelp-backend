"""Configuración central de la aplicación, leída desde variables de entorno (.env)."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Aplicación
    app_name: str = "TraceHelp API"
    app_version: str = "0.1.0"
    environment: str = "development" 
    api_prefix: str = "/api/v1"
    cors_origins: list[str] = ["*"]

    # Base de datos (PostgreSQL + pgvector)
    database_url: str = "postgresql+psycopg://tracehelp:tracehelp@localhost:5432/tracehelp"

    # Seguridad (JWT) - se usan en TS03
    jwt_secret_key: str = "dev-only-secret-cambiar-en-el-env-0123456789"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Inteligencia artificial (Google Gemini)
    gemini_api_key: str = ""
    llm_model: str = "gemini-2.5-flash-lite"
    embedding_model: str = "gemini-embedding-001"
    embedding_dimensions: int = 768

    # Anonimización PII (T27): clave del sello HMAC y modelo de spaCy (vacío = solo expresiones regulares)
    pii_audit_secret: str = "dev-only-pii-secret-cambiar-en-el-env-0123456789"
    pii_spacy_model: str = "es_core_news_sm"

    # Notificaciones
    resend_api_key: str = ""

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        """Neon y Render entregan URLs postgres:// o postgresql://; SQLAlchemy necesita el driver psycopg."""
        if value.startswith("postgres://"):
            value = "postgresql://" + value.removeprefix("postgres://")
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()

 #