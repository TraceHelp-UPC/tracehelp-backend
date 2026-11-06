"""Pruebas del formato de errores RFC 7807 (T02). No requieren base de datos."""
from typing import Annotated

import pytest
from fastapi import FastAPI, Form, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.error_handlers import STATUS_BY_EXCEPTION
from app.helpdesk.domain.enums import TicketStatus
from app.helpdesk.domain.exceptions import (
    InvalidTicketDataError,
    InvalidTicketStateTransitionError,
    TicketNotFoundError,
    TicketStatusChangeForbiddenError,
)
from app.iam.domain.exceptions import InvalidCredentialsError
from app.main import app as real_app
from app.shared.interfaces.rest.problem_details import PROBLEM_JSON, register_problem_handlers


class Body(BaseModel):
    status: TicketStatus
    reason: str | None = Field(None, max_length=5)


def _build_app() -> FastAPI:
    app = FastAPI()
    register_problem_handlers(app, STATUS_BY_EXCEPTION)

    errors = {
        "not-found": TicketNotFoundError("El ticket no existe."),
        "invalid-data": InvalidTicketDataError("La descripción del incidente es obligatoria."),
        "transition": InvalidTicketStateTransitionError("No se puede cambiar el ticket de OPEN a CLOSED."),
        "forbidden": TicketStatusChangeForbiddenError("Solo el colaborador que reportó el incidente puede hacer este cambio."),
        "credentials": InvalidCredentialsError("Correo o contraseña incorrectos."),
    }

    @app.get("/domain/{kind}")
    def raise_domain(kind: str):
        raise errors[kind]

    @app.get("/http")
    def raise_http():
        raise HTTPException(409, "El documento ya fue cargado.")

    @app.post("/json")
    def json_body(body: Body):
        return body

    @app.post("/form")
    def form_body(title: Annotated[str, Form()], description: Annotated[str, Form()]):
        return {"title": title}

    @app.get("/boom")
    def boom():
        raise RuntimeError("detalle interno que no debe filtrarse")

    return app


client = TestClient(_build_app(), raise_server_exceptions=False)


def _assert_problem(response, status: int) -> dict:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith(PROBLEM_JSON)
    body = response.json()
    assert body["status"] == status
    assert body["type"].startswith("urn:tracehelp:problems:")
    assert isinstance(body["title"], str) and body["title"]
    assert isinstance(body["detail"], str) and body["detail"]
    return body


@pytest.mark.parametrize(
    ("kind", "status", "problem_type"),
    [
        ("not-found", 404, "ticket-not-found"),
        ("invalid-data", 400, "invalid-ticket-data"),
        ("transition", 422, "invalid-ticket-state-transition"),
        ("forbidden", 403, "ticket-status-change-forbidden"),
        ("credentials", 401, "invalid-credentials"),
    ],
)
def test_domain_errors_are_mapped_to_problem_details(kind, status, problem_type):
    body = _assert_problem(client.get(f"/domain/{kind}"), status)
    assert body["type"] == f"urn:tracehelp:problems:{problem_type}"
    assert body["instance"] == f"/domain/{kind}"


def test_domain_error_keeps_the_original_message_in_detail():
    body = _assert_problem(client.get("/domain/transition"), 422)
    assert body["detail"] == "No se puede cambiar el ticket de OPEN a CLOSED."


def test_unauthorized_domain_error_sends_www_authenticate():
    response = client.get("/domain/credentials")
    assert response.headers.get("www-authenticate") == "Bearer"


def test_http_exception_keeps_detail_as_text():
    body = _assert_problem(client.get("/http"), 409)
    assert body["detail"] == "El documento ya fue cargado."
    assert body["type"] == "urn:tracehelp:problems:conflict"


def test_unknown_route_returns_problem_404():
    _assert_problem(client.get("/no-existe"), 404)


def test_json_validation_errors_list_each_field():
    body = _assert_problem(client.post("/json", json={"status": "EN_PROCESO", "reason": "demasiado largo"}), 422)
    assert body["type"] == "urn:tracehelp:problems:validation-error"
    fields = {e["field"] for e in body["errors"]}
    assert fields == {"status", "reason"}
    assert "status" in body["detail"] and "reason" in body["detail"]


def test_form_validation_reports_missing_fields_in_spanish():
    body = _assert_problem(client.post("/form", data={"title": "Sin descripción"}), 422)
    assert body["errors"] == [{"field": "description", "message": "es obligatorio", "type": "missing"}]
    assert "description: es obligatorio" in body["detail"]


def test_malformed_json_is_a_validation_problem():
    response = client.post("/json", content=b"{no es json", headers={"Content-Type": "application/json"})
    _assert_problem(response, 422)


def test_unexpected_errors_do_not_leak_internal_details():
    body = _assert_problem(client.get("/boom"), 500)
    assert "detalle interno" not in body["detail"]


def test_real_app_uses_problem_details_for_missing_token():
    response = TestClient(real_app).get("/api/v1/auth/me")
    body = _assert_problem(response, 401)
    assert body["detail"] == "Se requiere un token de acceso."
    assert response.headers.get("www-authenticate") == "Bearer"
