from fastapi.testclient import TestClient

from app.core import database
from app.main import app

client = TestClient(app)


def test_health_ok_when_database_is_up(monkeypatch):
    monkeypatch.setattr(database, "check_database", lambda: {"database": "up", "pgvector": True})
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "up"
    assert response.json()["pgvector"] is True


def test_health_returns_503_when_database_is_down(monkeypatch):
    def fail():
        raise ConnectionError("db down")

    monkeypatch.setattr(database, "check_database", fail)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["database"] == "down"


def test_api_docs_are_available():
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "TraceHelp API"
