"""Fixtures compartidas.

Las pruebas de integración usan una base PostgreSQL real indicada en TEST_DATABASE_URL.
Si la variable no existe, esas pruebas se omiten y solo corren las unitarias.
Con Docker: docker compose up -d db y luego
TEST_DATABASE_URL=postgresql+psycopg://tracehelp:tracehelp@localhost:5432/tracehelp_test pytest
"""
import os
import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings

# Las pruebas no lanzan el worker de ingesta en segundo plano (T23); el pipeline se prueba directamente
os.environ.setdefault("INGESTION_WORKER_ENABLED", "false")
os.environ.setdefault("TRIAGE_WORKER_ENABLED", "false")

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
FAKE_HASH = "$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm"


def _normalized_url() -> str:
    return Settings(database_url=TEST_DATABASE_URL).database_url


@pytest.fixture(scope="session")
def db_engine():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL no está configurada; se omiten las pruebas de integración.")
    url = _normalized_url()

    # Crea la base de pruebas si no existe
    admin_url = make_url(url).set(database="postgres")
    db_name = make_url(url).database
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin.dispose()

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    engine = create_engine(url)
    yield engine
    engine.dispose()
    command.downgrade(cfg, "base")


@pytest.fixture()
def db_session(db_engine):
    """Sesión dentro de una transacción que se revierte al terminar cada prueba."""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def workspace_and_users(db_session):
    """Crea un workspace con un colaborador y un analista L1."""
    from app.iam.domain.enums import RoleName
    from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel

    workspace = WorkspaceModel(id=uuid.uuid4(), name="Empresa Demo", subdomain=f"demo-{uuid.uuid4().hex[:6]}")
    collaborator = UserModel(
        id=uuid.uuid4(), workspace_id=workspace.id, full_name="Colaborador Demo",
        email=f"colab-{uuid.uuid4().hex[:6]}@demo.pe", password_hash=FAKE_HASH, role=RoleName.COLLABORATOR, department="Ventas",
    )
    analyst = UserModel(
        id=uuid.uuid4(), workspace_id=workspace.id, full_name="Analista Demo",
        email=f"analista-{uuid.uuid4().hex[:6]}@demo.pe", password_hash=FAKE_HASH, role=RoleName.ANALYST_L1, department="TI",
    )
    db_session.add(workspace)
    db_session.flush()
    db_session.add_all([collaborator, analyst])
    db_session.flush()
    return workspace, collaborator, analyst


@pytest.fixture()
def api_client(db_session):
    """Cliente HTTP de la API que usa la sesión transaccional de la prueba."""
    import contextlib

    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.core.event_handlers import analytics_audit_handler
    from app.main import app

    def _override_get_db():
        yield db_session

    original_factory = analytics_audit_handler._session_factory
    analytics_audit_handler._session_factory = lambda: contextlib.nullcontext(db_session)
    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    analytics_audit_handler._session_factory = original_factory


@pytest.fixture()
def auth_headers():
    """Genera el encabezado Authorization para un UserModel guardado en la base de pruebas."""
    from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
    from app.iam.interfaces.rest.dependencies import get_token_provider

    def _headers(db_session, user_model) -> dict:
        user = SqlAlchemyUserRepository(db_session).find_by_id(user_model.id)
        token, _ = get_token_provider().issue_access_token(user)
        return {"Authorization": f"Bearer {token}"}

    return _headers
