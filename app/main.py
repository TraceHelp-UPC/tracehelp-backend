"""Punto de entrada del backend monolítico de TraceHelp."""
import logging
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.analytics.interfaces.rest.router import router as analytics_router
from app.core import database
from app.core.config import get_settings
from app.core.event_handlers import register_event_handlers
from app.helpdesk.interfaces.rest.router import router as helpdesk_router
from app.iam.interfaces.rest.router import router as iam_router
from app.knowledge.interfaces.rest.router import router as knowledge_router
from app.shared.infrastructure.event_bus import event_bus
from app.smart_triage.interfaces.rest.router import router as smart_triage_router

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Al arrancar, reanuda las ingestas de manuales que quedaron a medias (T23)."""
    worker = None
    if settings.ingestion_worker_enabled:
        from app.knowledge.infrastructure.ingestion_worker import ingestion_worker as worker

        try:
            worker.resume_pending()
        except Exception:  # noqa: BLE001 - si la base no responde, la API arranca igual
            logger.exception("No se pudieron reanudar las ingestas pendientes")
    yield
    if worker is not None:
        worker.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="API REST de TraceHelp: triaje inteligente de incidentes de TI con RAG y supervisión humana.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_event_handlers(event_bus)

    for router in (iam_router, helpdesk_router, knowledge_router, smart_triage_router, analytics_router):
        app.include_router(router, prefix=settings.api_prefix)

    @app.get("/health", tags=["Health"])
    def health() -> JSONResponse:
        """Health check usado por Render. Responde 503 si la base de datos no está disponible."""
        body = {
            "status": "ok",
            "version": settings.app_version,
            "environment": settings.environment,
            "tesseract": shutil.which("tesseract") is not None,
        }
        try:
            body.update(database.check_database())
            status_code = 200
        except Exception:  # noqa: BLE001 - cualquier fallo de conexión se reporta como caída
            body.update({"status": "degraded", "database": "down", "pgvector": False})
            status_code = 503
        return JSONResponse(content=body, status_code=status_code)

    return app


app = create_app()
