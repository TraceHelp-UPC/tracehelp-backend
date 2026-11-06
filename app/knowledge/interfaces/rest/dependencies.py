"""Construcción de servicios de Knowledge Management para los endpoints."""
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.iam.domain.permissions import Permission
from app.iam.interfaces.rest.auth_dependencies import CurrentUser, get_current_user
from app.knowledge.application.knowledge_command_service import KnowledgeCommandService
from app.knowledge.application.knowledge_query_service import KnowledgeQueryService
from app.knowledge.infrastructure.persistence.document_storage import DatabaseDocumentStorage
from app.knowledge.infrastructure.persistence.technical_document_repository import (
    SqlAlchemyTechnicalDocumentRepository,
)
from app.shared.infrastructure.event_bus import InMemoryEventBus, get_event_bus


def get_knowledge_command_service(
    db: Session = Depends(get_db),
    bus: InMemoryEventBus = Depends(get_event_bus),
) -> KnowledgeCommandService:
    return KnowledgeCommandService(
        session=db,
        documents=SqlAlchemyTechnicalDocumentRepository(db),
        storage=DatabaseDocumentStorage(db),
        events=bus,
    )


def get_knowledge_query_service(db: Session = Depends(get_db)) -> KnowledgeQueryService:
    return KnowledgeQueryService(SqlAlchemyTechnicalDocumentRepository(db))


def require_knowledge_reader(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Consultar manuales: el líder de TI (kb:write) y el equipo de soporte (tickets:manage)."""
    if not (user.can(Permission.KB_WRITE) or user.can(Permission.TICKETS_MANAGE)):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Tu rol no tiene el permiso requerido: {Permission.KB_WRITE.value} o {Permission.TICKETS_MANAGE.value}.",
        )
    return user
