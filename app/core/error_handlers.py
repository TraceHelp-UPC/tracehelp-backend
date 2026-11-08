"""Códigos HTTP de las excepciones de dominio que no siguen la regla general (T02).

Regla general (app/shared/interfaces/rest/problem_details.py):
    ResourceNotFoundError -> 404, DomainValidationError -> 400, cualquier otro DomainError -> 422.

Aquí solo se agregan las excepciones que necesitan otro código. Cada contexto suma las suyas cuando las crea.
"""
from fastapi import FastAPI

from app.helpdesk.domain.exceptions import TicketAccessDeniedError, TicketStatusChangeForbiddenError
from app.iam.domain.exceptions import InactiveUserError, InvalidCredentialsError, InvalidTokenError
from app.shared.interfaces.rest.problem_details import register_problem_handlers
from app.smart_triage.application.hitl_review_service import HitlPermissionError
from app.smart_triage.domain.triage_diagnosis import DiagnosisAlreadyReviewedError

STATUS_BY_EXCEPTION: dict[type[Exception], int] = {
    # IAM
    InvalidCredentialsError: 401,
    InvalidTokenError: 401,
    InactiveUserError: 403,
    # Helpdesk
    TicketStatusChangeForbiddenError: 403,
    TicketAccessDeniedError: 403,
    # Smart Triage
    HitlPermissionError: 403,
    DiagnosisAlreadyReviewedError: 409,
}


def register_error_handlers(app: FastAPI) -> None:
    register_problem_handlers(app, STATUS_BY_EXCEPTION)
