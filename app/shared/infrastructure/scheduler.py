"""Scheduler asíncrono de tareas periódicas (T60, TS09).

- Se arranca y se detiene en el lifespan de FastAPI.
- Cada job es una función síncrona sin argumentos que corre con ``asyncio.to_thread`` y abre su propia sesión.
- La tabla ``shared_scheduler_jobs`` es el candado: ``SELECT ... FOR UPDATE SKIP LOCKED`` evita que dos
  instancias ejecuten el mismo job a la vez.
- Ninguna excepción de un job detiene el bucle. ``/health`` solo expone el nombre de la clase de la excepción.

Uso desde otros contextos (T73, T88, T100)::

    scheduler.register("release_inactive_tickets", release_inactive_tickets)  # intervalo desde Settings
"""
import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

DEGRADED_AFTER_FAILURES = 3
STATUS_OK, STATUS_ERROR, STATUS_SKIPPED = "ok", "error", "skipped"

_UPSERT = text(
    """
    INSERT INTO shared_scheduler_jobs (job_name, interval_seconds, next_run_at)
    VALUES (:name, :interval, now())
    ON CONFLICT (job_name) DO UPDATE SET interval_seconds = EXCLUDED.interval_seconds
    """
)
_CLAIM = text(
    """
    SELECT interval_seconds FROM shared_scheduler_jobs
    WHERE job_name = :name AND next_run_at <= now()
    FOR UPDATE SKIP LOCKED
    """
)
_IS_DUE = text("SELECT 1 FROM shared_scheduler_jobs WHERE job_name = :name AND next_run_at <= now()")
_FINISH = text(
    """
    UPDATE shared_scheduler_jobs SET
        next_run_at = now() + make_interval(secs => interval_seconds),
        last_started_at = :started, last_finished_at = now(), last_status = :status, last_error = :error,
        consecutive_failures = CASE WHEN CAST(:status AS varchar) = 'ok' THEN 0 ELSE consecutive_failures + 1 END,
        updated_at = now()
    WHERE job_name = :name
    RETURNING next_run_at, consecutive_failures
    """
)


@dataclass
class JobState:
    """Último estado conocido de un job en esta instancia (lo que lee /health)."""

    name: str
    func: Callable[[], Any]
    interval_seconds: int
    last_run_at: datetime | None = None
    last_status: str | None = None
    last_duration_ms: int | None = None
    next_run_at: datetime | None = None
    consecutive_failures: int = 0
    last_error: str | None = None


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


class TaskScheduler:
    def __init__(self, session_factory: Callable[[], Session] | None = None, settings: Settings | None = None):
        self._session_factory = session_factory
        self._settings = settings
        self._jobs: dict[str, JobState] = {}
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._started_at: datetime | None = None

    # -- configuración -------------------------------------------------------------------------------
    @property
    def settings(self) -> Settings:
        return self._settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.scheduler_enabled

    def _sessions(self) -> Session:
        if self._session_factory is not None:
            return self._session_factory()
        from app.core.database import SessionLocal

        return SessionLocal()

    def interval_for(self, name: str) -> int | None:
        """Intervalo por variable de entorno (``JOB_<NOMBRE>_INTERVAL_SECONDS``) o None si no existe."""
        return getattr(self.settings, f"job_{name}_interval_seconds", None)

    # -- registro ------------------------------------------------------------------------------------
    def register(self, name: str, func: Callable[[], Any], interval_seconds: int | None = None) -> bool:
        """Registra un job por nombre. Sin ``interval_seconds`` se lee de Settings. Con intervalo <= 0 no se registra."""
        interval = interval_seconds if interval_seconds is not None else self.interval_for(name)
        if interval is None:
            raise ValueError(f"El job '{name}' no tiene intervalo: indícalo o define job_{name}_interval_seconds en Settings")
        if len(name) > 80:
            raise ValueError("El nombre del job admite hasta 80 caracteres")
        if interval <= 0:
            logger.info("Job '%s' desactivado (intervalo <= 0)", name)
            self._jobs.pop(name, None)
            return False
        self._jobs[name] = JobState(name=name, func=func, interval_seconds=interval)
        return True

    def unregister(self, name: str) -> None:
        self._jobs.pop(name, None)

    @property
    def job_names(self) -> list[str]:
        return list(self._jobs)

    # -- ejecución -----------------------------------------------------------------------------------
    def sync_jobs(self) -> None:
        """Crea o actualiza las filas de los jobs registrados (idempotente)."""
        with self._sessions() as session:
            for job in self._jobs.values():
                session.execute(_UPSERT, {"name": job.name, "interval": job.interval_seconds})
            session.commit()

    def run_job(self, name: str) -> str | None:
        """Intenta ejecutar un job. Devuelve ok, error, skipped (otra instancia lo tiene) o None (aún no toca)."""
        job = self._jobs[name]
        try:
            with self._sessions() as session:
                claimed = session.execute(_CLAIM, {"name": name}).first()
                if claimed is None:
                    due = session.execute(_IS_DUE, {"name": name}).first()
                    session.rollback()
                    if due is None:
                        return None
                    job.last_status = STATUS_SKIPPED
                    return STATUS_SKIPPED
                started = datetime.now(UTC)
                t0 = time.perf_counter()
                status, error = STATUS_OK, None
                try:
                    job.func()
                except Exception as exc:  # noqa: BLE001 - un job nunca detiene el bucle
                    logger.exception("Falló el job '%s'", name)
                    status, error = STATUS_ERROR, type(exc).__name__
                duration_ms = int((time.perf_counter() - t0) * 1000)
                row = session.execute(
                    _FINISH, {"name": name, "started": started, "status": status, "error": error}
                ).one()
                session.commit()
        except Exception as exc:  # noqa: BLE001 - base caída u otro fallo de infraestructura
            logger.exception("No se pudo coordinar el job '%s'", name)
            job.last_status, job.last_error = STATUS_ERROR, type(exc).__name__
            job.consecutive_failures += 1
            return STATUS_ERROR
        job.last_run_at, job.last_status, job.last_error = started, status, error
        job.last_duration_ms, job.next_run_at, job.consecutive_failures = (
            duration_ms, row.next_run_at, row.consecutive_failures,
        )
        return status

    async def tick(self) -> None:
        for name in self.job_names:
            await asyncio.to_thread(self.run_job, name)

    async def _loop(self) -> None:
        assert self._stop_event is not None
        try:
            await asyncio.to_thread(self.sync_jobs)
        except Exception:  # noqa: BLE001 - si la base no responde, la API arranca igual
            logger.exception("No se pudieron registrar los jobs del scheduler")
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception:  # noqa: BLE001
                logger.exception("Error inesperado en el ciclo del scheduler")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=max(1, self.settings.scheduler_tick_seconds))
            except TimeoutError:
                pass

    def start(self) -> None:
        if not self.enabled or self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._started_at = datetime.now(UTC)
        self._task = asyncio.create_task(self._loop(), name="tracehelp-scheduler")

    async def stop(self) -> None:
        if self._task is None:
            return
        assert self._stop_event is not None
        self._stop_event.set()
        try:
            await self._task
        finally:
            self._task = None

    # -- estado para /health -------------------------------------------------------------------------
    def status(self) -> str:
        if not self.enabled:
            return "disabled"
        if self._task is None or self._task.done():
            return "stopped"
        if any(j.consecutive_failures >= DEGRADED_AFTER_FAILURES for j in self._jobs.values()):
            return "degraded"
        return "running"

    def snapshot(self) -> dict:
        """Estado en memoria de esta instancia. Sin mensajes de excepción: /health es público."""
        return {
            "status": self.status(),
            "started_at": _iso(self._started_at),
            "tick_seconds": self.settings.scheduler_tick_seconds,
            "jobs": [
                {
                    "name": j.name,
                    "enabled": True,
                    "interval_seconds": j.interval_seconds,
                    "last_run_at": _iso(j.last_run_at),
                    "last_status": j.last_status,
                    "last_duration_ms": j.last_duration_ms,
                    "next_run_at": _iso(j.next_run_at),
                    "consecutive_failures": j.consecutive_failures,
                    "last_error": j.last_error,
                }
                for j in self._jobs.values()
            ],
        }


def heartbeat() -> None:
    """Job de ejemplo: confirma que el scheduler corre y que la base responde."""
    from app.core.database import SessionLocal

    with SessionLocal() as session:
        session.execute(text("SELECT 1"))
    logger.debug("heartbeat del scheduler")


scheduler = TaskScheduler()


def register_default_jobs(target: TaskScheduler = scheduler) -> None:
    """Jobs que existen hoy. T73, T88 y T100 agregan los suyos aquí (nombres reservados en TS09)."""
    target.register("heartbeat", heartbeat)
