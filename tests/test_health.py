from fastapi.testclient import TestClient

from app.core import database
from app.core.config import Settings
from app.main import app
from app.shared.infrastructure import scheduler as scheduler_module
from app.shared.infrastructure.scheduler import TaskScheduler

client = TestClient(app)


def test_health_ok_when_database_is_up(monkeypatch):
    monkeypatch.setattr(database, "check_database", lambda: {"database": "up", "pgvector": True})
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["database"] == "up"
    assert response.json()["pgvector"] is True
    assert response.json()["version"] == "1.0.0"


def test_health_returns_503_when_database_is_down(monkeypatch):
    def fail():
        raise ConnectionError("db down")

    monkeypatch.setattr(database, "check_database", fail)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["database"] == "down"


def test_health_includes_scheduler_block_disabled_in_tests(monkeypatch):
    monkeypatch.setattr(database, "check_database", lambda: {"database": "up", "pgvector": True})
    block = client.get("/health").json()["scheduler"]
    assert block["status"] == "disabled"
    assert block["jobs"] == []
    assert set(block) == {"status", "started_at", "tick_seconds", "jobs"}


def _scheduler_with_jobs(monkeypatch) -> TaskScheduler:
    s = TaskScheduler(settings=Settings(scheduler_enabled=True))
    s.register("heartbeat", lambda: None)
    s.register("release_inactive_tickets", lambda: None)
    failing = s._jobs["release_inactive_tickets"]
    failing.last_status, failing.last_error, failing.consecutive_failures = "error", "ValueError", 1
    monkeypatch.setattr("app.main.scheduler", s)
    return s


def test_health_lists_jobs_and_exposes_only_exception_class(monkeypatch):
    monkeypatch.setattr(database, "check_database", lambda: {"database": "up", "pgvector": True})
    _scheduler_with_jobs(monkeypatch)
    response = client.get("/health")
    assert response.status_code == 200
    block = response.json()["scheduler"]
    assert block["status"] == "stopped"  # el bucle no se arrancó en la prueba
    jobs = {j["name"]: j for j in block["jobs"]}
    assert set(jobs) == {"heartbeat", "release_inactive_tickets"}
    assert jobs["heartbeat"]["last_status"] is None and jobs["heartbeat"]["last_error"] is None
    assert jobs["release_inactive_tickets"]["last_error"] == "ValueError"


def test_health_keeps_503_and_scheduler_block_when_database_is_down(monkeypatch):
    def fail():
        raise ConnectionError("db down")

    monkeypatch.setattr(database, "check_database", fail)
    _scheduler_with_jobs(monkeypatch)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["scheduler"]["jobs"]


def test_degraded_scheduler_does_not_change_http_code(monkeypatch):
    monkeypatch.setattr(database, "check_database", lambda: {"database": "up", "pgvector": True})
    s = _scheduler_with_jobs(monkeypatch)
    s._jobs["heartbeat"].consecutive_failures = 5
    assert client.get("/health").status_code == 200


def test_default_jobs_register_heartbeat():
    s = TaskScheduler(settings=Settings(scheduler_enabled=True))
    scheduler_module.register_default_jobs(s)
    assert s.job_names == ["heartbeat"]


def test_api_docs_are_available():
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["info"]["title"] == "TraceHelp API"
