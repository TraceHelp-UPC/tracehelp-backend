"""Pruebas del scheduler (T60, TS09). Las de integración usan TEST_DATABASE_URL."""
import asyncio
import threading

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.shared.infrastructure.scheduler import TaskScheduler


def make_settings(**overrides) -> Settings:
    return Settings(scheduler_enabled=True, scheduler_tick_seconds=1, **overrides)


# ---------------------------------------------------------------- unitarias (sin base de datos)
def test_register_uses_interval_from_settings():
    s = TaskScheduler(settings=make_settings(job_heartbeat_interval_seconds=45))
    assert s.register("heartbeat", lambda: None) is True
    assert s.snapshot()["jobs"][0]["interval_seconds"] == 45


def test_reserved_jobs_have_default_intervals():
    s = TaskScheduler(settings=make_settings())
    for name, expected in (
        ("heartbeat", 60),
        ("release_inactive_tickets", 300),
        ("auto_close_resolved_tickets", 3600),
        ("knowledge_gap_analysis", 86400),
    ):
        s.register(name, lambda: None)
        assert {j["name"]: j["interval_seconds"] for j in s.snapshot()["jobs"]}[name] == expected


def test_explicit_interval_overrides_settings_and_unknown_job_requires_one():
    s = TaskScheduler(settings=make_settings())
    s.register("heartbeat", lambda: None, interval_seconds=5)
    assert s.snapshot()["jobs"][0]["interval_seconds"] == 5
    with pytest.raises(ValueError):
        s.register("job_desconocido", lambda: None)
    assert s.register("job_desconocido", lambda: None, interval_seconds=10) is True


def test_interval_zero_disables_job():
    s = TaskScheduler(settings=make_settings(job_heartbeat_interval_seconds=0))
    assert s.register("heartbeat", lambda: None) is False
    assert s.snapshot()["jobs"] == []


def test_status_disabled_without_jobs_when_scheduler_off():
    s = TaskScheduler(settings=Settings(scheduler_enabled=False))
    snap = s.snapshot()
    assert snap["status"] == "disabled" and snap["jobs"] == [] and snap["started_at"] is None


def test_status_stopped_before_start():
    assert TaskScheduler(settings=make_settings()).status() == "stopped"


def test_start_does_nothing_when_disabled():
    async def scenario():
        s = TaskScheduler(settings=Settings(scheduler_enabled=False))
        s.start()
        await s.stop()
        return s.status()

    assert asyncio.run(scenario()) == "disabled"


def test_degraded_after_three_failures():
    s = TaskScheduler(settings=make_settings())
    s.register("heartbeat", lambda: None)
    s._jobs["heartbeat"].consecutive_failures = 3

    async def scenario():
        s._task = asyncio.create_task(asyncio.sleep(10))
        try:
            return s.status()
        finally:
            s._task.cancel()

    assert asyncio.run(scenario()) == "degraded"


# ---------------------------------------------------------------- integración (PostgreSQL real)
@pytest.fixture()
def factory(db_engine):
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    yield session_factory
    with session_factory() as session:
        session.execute(text("DELETE FROM shared_scheduler_jobs"))
        session.commit()


def row(factory, name):
    with factory() as session:
        return session.execute(
            text("SELECT * FROM shared_scheduler_jobs WHERE job_name = :n"), {"n": name}
        ).mappings().one()


def new_scheduler(factory, **overrides) -> TaskScheduler:
    return TaskScheduler(session_factory=factory, settings=make_settings(**overrides))


def test_sync_creates_rows_and_is_idempotent(factory):
    s = new_scheduler(factory)
    s.register("heartbeat", lambda: None, interval_seconds=60)
    s.sync_jobs()
    s.sync_jobs()
    assert row(factory, "heartbeat")["interval_seconds"] == 60
    s.register("heartbeat", lambda: None, interval_seconds=90)
    s.sync_jobs()
    assert row(factory, "heartbeat")["interval_seconds"] == 90
    with factory() as session:
        assert session.execute(text("SELECT count(*) FROM shared_scheduler_jobs")).scalar() == 1


def test_job_runs_once_until_next_run_is_due(factory):
    calls = []
    s = new_scheduler(factory)
    s.register("heartbeat", lambda: calls.append(1), interval_seconds=60)
    s.sync_jobs()
    assert s.run_job("heartbeat") == "ok"
    assert s.run_job("heartbeat") is None  # aún no toca: idempotente
    assert len(calls) == 1
    data = row(factory, "heartbeat")
    assert data["last_status"] == "ok" and data["consecutive_failures"] == 0
    assert data["next_run_at"] > data["last_finished_at"]
    snap = s.snapshot()["jobs"][0]
    assert snap["last_status"] == "ok" and snap["last_run_at"].endswith("Z") and snap["next_run_at"] is not None


def test_failing_job_records_only_class_name(factory):
    def boom():
        raise ValueError("password=secreto juan@empresa.pe")

    s = new_scheduler(factory)
    s.register("heartbeat", boom, interval_seconds=60)
    s.sync_jobs()
    assert s.run_job("heartbeat") == "error"
    assert row(factory, "heartbeat")["last_error"] == "ValueError"
    assert row(factory, "heartbeat")["consecutive_failures"] == 1
    assert s.snapshot()["jobs"][0]["last_error"] == "ValueError"
    assert "secreto" not in str(s.snapshot())


def test_success_resets_consecutive_failures(factory):
    state = {"fail": True}

    def flaky():
        if state["fail"]:
            raise RuntimeError("x")

    s = new_scheduler(factory)
    s.register("heartbeat", flaky, interval_seconds=60)
    s.sync_jobs()
    s.run_job("heartbeat")
    with factory() as session:  # vuelve a vencer el job
        session.execute(text("UPDATE shared_scheduler_jobs SET next_run_at = now() - interval '1 second'"))
        session.commit()
    state["fail"] = False
    assert s.run_job("heartbeat") == "ok"
    assert row(factory, "heartbeat")["consecutive_failures"] == 0


def test_two_executors_compete_only_one_runs(factory):
    """Mientras A ejecuta (con la fila bloqueada), B queda skipped y no ejecuta el job."""
    started, release = threading.Event(), threading.Event()
    runs = {"a": 0, "b": 0}

    def slow():
        runs["a"] += 1
        started.set()
        assert release.wait(timeout=10)

    a, b = new_scheduler(factory), new_scheduler(factory)
    a.register("heartbeat", slow, interval_seconds=60)
    b.register("heartbeat", lambda: runs.__setitem__("b", runs["b"] + 1), interval_seconds=60)
    a.sync_jobs()

    thread = threading.Thread(target=a.run_job, args=("heartbeat",))
    thread.start()
    assert started.wait(timeout=10)
    assert b.run_job("heartbeat") == "skipped"
    assert b.snapshot()["jobs"][0]["last_status"] == "skipped"
    release.set()
    thread.join(timeout=10)
    assert runs == {"a": 1, "b": 0}
    assert row(factory, "heartbeat")["last_status"] == "ok"


def test_start_runs_jobs_and_stops_cleanly(factory):
    calls = []

    async def scenario():
        s = new_scheduler(factory)
        s.register("heartbeat", lambda: calls.append(1), interval_seconds=60)
        s.start()
        assert s.status() == "running"
        for _ in range(100):
            if calls:
                break
            await asyncio.sleep(0.05)
        await s.stop()
        return s

    s = asyncio.run(scenario())
    assert len(calls) == 1
    assert s.status() == "stopped" and s._task is None
    assert s.snapshot()["started_at"] is not None


def test_loop_survives_database_failure():
    def broken():
        raise ConnectionError("db caida")

    async def scenario():
        s = TaskScheduler(session_factory=broken, settings=make_settings())
        s.register("heartbeat", lambda: None, interval_seconds=60)
        s.start()
        await asyncio.sleep(0.3)
        running = s.status()
        await s.stop()
        return running, s.snapshot()["jobs"][0]

    running, job = asyncio.run(scenario())
    assert running == "running"
    assert job["last_status"] == "error" and job["last_error"] == "ConnectionError"
