"""Configuración de Behave para las pruebas BDD de la API.

Usa una base PostgreSQL de pruebas indicada en TEST_DATABASE_URL. Cada escenario corre dentro de una
transacción que se revierte al terminar, así los escenarios no se afectan entre sí.

Ejemplo con Docker:
    docker compose exec -e TEST_DATABASE_URL=postgresql+psycopg://tracehelp:tracehelp@db:5432/tracehelp_test api behave
"""
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


def _ensure_database(url: str) -> None:
    db_name = make_url(url).database
    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if not conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}).scalar():
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    admin.dispose()


def before_all(context):
    test_url = os.getenv("TEST_DATABASE_URL")
    if not test_url:
        raise RuntimeError("Define TEST_DATABASE_URL para ejecutar las pruebas BDD.")

    # La aplicación lee DATABASE_URL al importarse, por eso se fija antes de importar app.main
    os.environ["DATABASE_URL"] = test_url
    os.environ["INGESTION_WORKER_ENABLED"] = "false"
    from app.core.config import Settings, get_settings

    get_settings.cache_clear()
    url = Settings().database_url
    _ensure_database(url)

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")

    from fastapi.testclient import TestClient

    from app.main import app

    context.app = app
    context.client = TestClient(app)
    context.engine = create_engine(url)


def before_scenario(context, scenario):
    from app.core.database import get_db

    context.connection = context.engine.connect()
    context.transaction = context.connection.begin()
    context.session = Session(bind=context.connection, join_transaction_mode="create_savepoint")

    def _override_get_db():
        yield context.session

    context.app.dependency_overrides[get_db] = _override_get_db
    context.response = None


def after_scenario(context, scenario):
    context.app.dependency_overrides.clear()
    context.session.close()
    context.transaction.rollback()
    context.connection.close()


def after_all(context):
    engine = getattr(context, "engine", None)
    if engine is not None:
        engine.dispose()
