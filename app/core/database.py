"""Conexión a PostgreSQL con SQLAlchemy 2.0 compartida por los cinco módulos."""
from collections.abc import Generator

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Nombres estables para índices y restricciones (necesario para que Alembic genere migraciones limpias)
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base declarativa para todos los modelos ORM. Cada tabla usa el prefijo de su contexto (iam_, helpdesk_, kb_, triage_, analytics_)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def get_db() -> Generator[Session, None, None]:
    """Dependencia de FastAPI que abre una sesión por petición."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_database() -> dict:
    """Verifica la conexión y si la extensión pgvector está instalada."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        has_vector = conn.execute(
            text("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        ).scalar()
    return {"database": "up", "pgvector": bool(has_vector)}
