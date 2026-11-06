"""Respuestas de error en formato Problem Details (RFC 7807) para toda la API (T02).

Todas las respuestas de error tienen Content-Type application/problem+json y este cuerpo:

    {
      "type": "urn:tracehelp:problems:invalid-ticket-state-transition",
      "title": "Regla de negocio incumplida",
      "status": 422,
      "detail": "No se puede cambiar el ticket de OPEN a CLOSED. ...",
      "instance": "/api/v1/tickets/1f0c.../status"
    }

El campo detail siempre es un texto legible, porque las aplicaciones Appsmith lo muestran con
showAlert(Query.data?.detail). Los errores de validación agregan el arreglo errors con el detalle por campo.

Con estos manejadores, un endpoint puede dejar que las excepciones de dominio salgan sin traducirlas:
ResourceNotFoundError responde 404, DomainValidationError 400 y cualquier otro DomainError 422.
Los casos especiales (401, 403, 409...) se declaran en el mapa de app/core/error_handlers.py.
"""
import logging
import re
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.shared.domain.exceptions import DomainError, DomainValidationError, ResourceNotFoundError

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"
TYPE_PREFIX = "urn:tracehelp:problems:"

# Título y tipo genérico por código HTTP (se usan cuando el error no viene de una excepción de dominio)
_GENERIC: dict[int, tuple[str, str]] = {
    400: ("bad-request", "Solicitud no válida"),
    401: ("unauthorized", "No autenticado"),
    403: ("forbidden", "Acceso denegado"),
    404: ("not-found", "Recurso no encontrado"),
    405: ("method-not-allowed", "Método no permitido"),
    409: ("conflict", "Conflicto con el estado actual"),
    413: ("payload-too-large", "Archivo o solicitud demasiado grande"),
    415: ("unsupported-media-type", "Tipo de contenido no soportado"),
    422: ("unprocessable-entity", "Regla de negocio incumplida"),
    429: ("too-many-requests", "Demasiadas solicitudes"),
    500: ("internal-error", "Error interno del servidor"),
    503: ("service-unavailable", "Servicio no disponible"),
}


class FieldError(BaseModel):
    field: str = Field(..., description="Campo con error, por ejemplo body.title")
    message: str = Field(..., description="Motivo en español")
    type: str = Field(..., description="Código del error de validación")


class ProblemDetail(BaseModel):
    """Esquema de error RFC 7807 que devuelve toda la API."""

    type: str = Field(..., examples=["urn:tracehelp:problems:not-found"])
    title: str = Field(..., examples=["Recurso no encontrado"])
    status: int = Field(..., examples=[404])
    detail: str = Field(..., examples=["El ticket no existe."])
    instance: str | None = Field(None, examples=["/api/v1/tickets/1f0c2b8e-0000-0000-0000-000000000000/status"])
    errors: list[FieldError] | None = Field(None, description="Solo en errores de validación (422)")


def _generic(status_code: int) -> tuple[str, str]:
    if status_code in _GENERIC:
        return _GENERIC[status_code]
    try:
        phrase = HTTPStatus(status_code).phrase
    except ValueError:
        phrase = "Error"
    return re.sub(r"[^a-z0-9]+", "-", phrase.lower()).strip("-"), phrase


def _slug_from_exception(exc: Exception) -> str:
    """InvalidTicketStateTransitionError -> invalid-ticket-state-transition."""
    name = type(exc).__name__.removesuffix("Error") or type(exc).__name__
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()


def problem_response(
    request: Request,
    status_code: int,
    detail: str,
    *,
    problem_type: str | None = None,
    title: str | None = None,
    errors: list[dict[str, str]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Arma la respuesta application/problem+json."""
    generic_slug, generic_title = _generic(status_code)
    body: dict[str, Any] = {
        "type": TYPE_PREFIX + (problem_type or generic_slug),
        "title": title or generic_title,
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
    }
    if errors is not None:
        body["errors"] = errors
    return JSONResponse(content=body, status_code=status_code, media_type=PROBLEM_JSON, headers=dict(headers or {}))


# ----------------------------------------------------------------------------- validación (422)
_MESSAGES = {
    "missing": "es obligatorio",
    "string_too_long": "supera la longitud máxima permitida",
    "string_too_short": "es demasiado corto",
    "uuid_parsing": "no es un identificador válido",
    "uuid_type": "no es un identificador válido",
    "int_parsing": "debe ser un número entero",
    "float_parsing": "debe ser un número",
    "bool_parsing": "debe ser verdadero o falso",
    "json_invalid": "el JSON está mal formado",
    "model_attributes_type": "el cuerpo de la solicitud no tiene el formato esperado",
    "greater_than": "es menor al mínimo permitido",
    "greater_than_equal": "es menor al mínimo permitido",
    "less_than": "supera el máximo permitido",
    "less_than_equal": "supera el máximo permitido",
}


def _field_name(loc: tuple | list) -> str:
    parts = [str(p) for p in loc]
    if parts and parts[0] in {"body", "query", "path", "header", "cookie"} and len(parts) > 1:
        parts = parts[1:]
    return ".".join(parts) or "solicitud"


def _message(error: Mapping[str, Any]) -> str:
    kind = error.get("type", "")
    ctx = error.get("ctx") or {}
    if kind == "enum" and ctx.get("expected"):
        return f"valor no permitido; usa {ctx['expected']}"
    if kind == "string_too_long" and ctx.get("max_length"):
        return f"no puede superar los {ctx['max_length']} caracteres"
    return _MESSAGES.get(kind, str(error.get("msg", "valor no válido")))


def _validation_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    return [
        {"field": _field_name(e.get("loc", ())), "message": _message(e), "type": str(e.get("type", ""))}
        for e in exc.errors()
    ]


# ----------------------------------------------------------------------------- registro
def register_problem_handlers(app: FastAPI, status_by_exception: Mapping[type[Exception], int] | None = None) -> None:
    """Registra los manejadores globales de errores.

    status_by_exception permite fijar el código HTTP de excepciones de dominio concretas (por ejemplo,
    InvalidCredentialsError -> 401). Se busca por la jerarquía de clases, así una subclase hereda el código.
    """
    overrides = dict(status_by_exception or {})

    def _status_for(exc: DomainError) -> int:
        for cls in type(exc).__mro__:
            if cls in overrides:
                return overrides[cls]
        if isinstance(exc, ResourceNotFoundError):
            return 404
        if isinstance(exc, DomainValidationError):
            return 400
        return 422

    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, str):
            detail, errors = exc.detail, None
        else:
            # Algunos componentes envían detail como lista o diccionario; se conserva en errors
            detail, errors = _generic(exc.status_code)[1], None
            if isinstance(exc.detail, list):
                errors = [{"field": "solicitud", "message": str(item), "type": "error"} for item in exc.detail]
        return problem_response(request, exc.status_code, detail, errors=errors, headers=exc.headers)

    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = _validation_errors(exc)
        summary = "; ".join(f"{e['field']}: {e['message']}" for e in errors[:5])
        detail = f"Hay datos no válidos en la solicitud. {summary}." if summary else "Hay datos no válidos en la solicitud."
        return problem_response(
            request, 422, detail, problem_type="validation-error", title="Datos de entrada no válidos", errors=errors
        )

    async def handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status_code = _status_for(exc)
        headers = {"WWW-Authenticate": "Bearer"} if status_code == 401 else None
        return problem_response(
            request,
            status_code,
            exc.detail,
            problem_type=_slug_from_exception(exc),
            title=_generic(status_code)[1],
            headers=headers,
        )

    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Error no controlado en %s %s", request.method, request.url.path)
        return problem_response(
            request, 500, "Ocurrió un error inesperado. Inténtalo de nuevo o contacta al equipo de soporte."
        )

    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
