"""Validación independiente de T60 (TS09): concurrencia real, bucle ante fallos y lifespan con scheduler activo."""
import threading
import warnings

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core import database
from app.core.config import Settings
from app.shared.infrastructure.scheduler import TaskScheduler


@pytest.fixture()
def factory(db_engine):
    sf = sessionmaker(bind=db_engine, expire_on_commit=False)
    yield sf
    with sf() as session:
        session.execute(text("DELETE FROM shared_scheduler_jobs"))
        session.commit()


def _sched(factory):
    return TaskScheduler(session_factory=factory, settings=Settings(scheduler_enabled=True, scheduler_tick_seconds=1))


def test_many_simultaneous_executors_run_job_exactly_once(factory):
    runs, results = [], []
    barrier = threading.Barrier(6)

    def job():
        runs.append(1)

    def worker():
        s = _sched(factory)
        s.register("heartbeat", job, interval_seconds=3600)
        barrier.wait(timeout=10)
        results.append(s.run_job("heartbeat"))

    _sched(factory).register("heartbeat", job, interval_seconds=3600)
    seed = _sched(factory)
    seed.register("heartbeat", job, interval_seconds=3600)
    seed.sync_jobs()
    threads = [threading.Thread(target=worker) for _ in range(6)]
    [t.start() for t in threads]
    [t.join(timeout=20) for t in threads]
    assert len(runs) == 1  # un solo ejecutor por intervalo
    assert results.count("ok") == 1
    assert all(r in ("ok", "skipped", None) for r in results)  # None: llegó tras el commit y ya no toca


def test_failing_job_does_not_stop_other_jobs_and_hides_message(factory):
    ran = []
    s = _sched(factory)

    def bad():
        raise RuntimeError("password=secreto juan@empresa.pe")

    s.register("heartbeat", bad, interval_seconds=60)
    s.register("release_inactive_tickets", lambda: ran.append(1), interval_seconds=60)
    s.sync_jobs()
    import asyncio

    asyncio.run(s.tick())
    assert ran == [1]
    snap = s.snapshot()
    assert snap["jobs"][0]["last_error"] == "RuntimeError"
    assert "secreto" not in str(snap) and "juan@" not in str(snap)
    with factory() as session:
        err = session.execute(text("SELECT last_error FROM shared_scheduler_jobs WHERE job_name='heartbeat'")).scalar()
    assert err == "RuntimeError"


@pytest.mark.parametrize("enabled", [True, False])
def test_lifespan_start_stop_clean(enabled, monkeypatch, db_engine):
    from app import main
    from app.shared.infrastructure.scheduler import scheduler

    monkeypatch.setattr(main.settings, "scheduler_enabled", enabled)
    monkeypatch.setattr(database, "check_database", lambda: {"database": "up", "pgvector": True})
    monkeypatch.setattr(scheduler, "_settings", Settings(scheduler_enabled=enabled, scheduler_tick_seconds=1))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        with TestClient(main.create_app()) as c:
            block = c.get("/health").json()["scheduler"]
            assert block["status"] == ("running" if enabled else "disabled")
            assert (len(block["jobs"]) == 1) == enabled
    assert scheduler._task is None
    scheduler.unregister("heartbeat")
