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

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


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
        email=f"colab-{uuid.uuid4().hex[:6]}@demo.pe", password_hash="x", role=RoleName.COLLABORATOR, department="Ventas",
    )
    analyst = UserModel(
        id=uuid.uuid4(), workspace_id=workspace.id, full_name="Analista Demo",
        email=f"analista-{uuid.uuid4().hex[:6]}@demo.pe", password_hash="x", role=RoleName.ANALYST_L1, department="TI",
    )
    db_session.add(workspace)
    db_session.flush()
    db_session.add_all([collaborator, analyst])
    db_session.flush()
    return workspace, collaborator, analyst
