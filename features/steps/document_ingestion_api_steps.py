"""Steps de la feature del contrato de ingesta de documentos (T24, TS01).

Reutiliza los archivos de prueba y la carga de knowledge_base_steps.py (T20).
"""
import uuid

from behave import then, when

from app.core.config import get_settings
from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.infrastructure.security.jwt_token_provider import JwtTokenProvider
from app.iam.interfaces.rest.dependencies import get_token_provider

FAKE_HASH = "$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm"


def _domain_user(context, role: str):
    return SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _job_url(job_id) -> str:
    return f"/api/v1/documents/jobs/{job_id}"


def _token_for(context, kind: str) -> dict:
    user = _domain_user(context, "IT_LEADER")
    settings = get_settings()
    if kind == "no token":
        return {}
    if kind == "a malformed token":
        return _bearer("esto-no-es-un-jwt")
    if kind == "a token signed with another key":
        other = JwtTokenProvider("otra-clave-secreta-de-al-menos-32-caracteres-123", settings.jwt_algorithm, 30, 7)
        return _bearer(other.issue_access_token(user)[0])
    if kind == "an expired token":
        expired = JwtTokenProvider(settings.jwt_secret_key, settings.jwt_algorithm, -5, 7)
        return _bearer(expired.issue_access_token(user)[0])
    if kind == "a refresh token instead of an access":
        return _bearer(get_token_provider().issue_tokens(user).refresh_token)
    raise AssertionError(f"Token de prueba no definido: {kind}")


def _another_workspace_leader(context) -> UserModel:
    workspace = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    context.session.add(workspace)
    context.session.flush()
    leader = UserModel(
        id=uuid.uuid4(), workspace_id=workspace.id, full_name="Líder Externo",
        email=f"lider-ext-{uuid.uuid4().hex[:6]}@otra.pe", password_hash=FAKE_HASH,
        role=RoleName.IT_LEADER, department="TI",
    )
    context.session.add(leader)
    context.session.flush()
    return leader


@when("the client uploads the manual with {token}")
def step_upload_with_token(context, token):
    name, content, mime = context.manual
    context.response = context.client.post(
        f"/api/v1/workspaces/{context.workspace.id}/documents",
        files={"file": (name, content, mime)},
        headers=_token_for(context, token),
    )


@when('the "{role}" uploads the manual to another workspace')
def step_upload_other_workspace(context, role):
    name, content, mime = context.manual
    user = _domain_user(context, role)
    token, _ = get_token_provider().issue_access_token(user)
    context.response = context.client.post(
        f"/api/v1/workspaces/{uuid.uuid4()}/documents", files={"file": (name, content, mime)}, headers=_bearer(token)
    )


@when('the client requests the status of that job as the "{role}"')
def step_job_status(context, role):
    token, _ = get_token_provider().issue_access_token(_domain_user(context, role))
    context.response = context.client.get(_job_url(context.job_id), headers=_bearer(token))


@when("the client requests the status of that job without a token")
def step_job_status_anonymous(context):
    context.response = context.client.get(_job_url(context.job_id))


@when("a leader of another workspace requests the status of that job")
def step_job_status_other_workspace(context):
    outsider = SqlAlchemyUserRepository(context.session).find_by_id(_another_workspace_leader(context).id)
    token, _ = get_token_provider().issue_access_token(outsider)
    context.response = context.client.get(_job_url(context.job_id), headers=_bearer(token))


@when('the client requests the status of an unknown job as the "{role}"')
def step_unknown_job(context, role):
    token, _ = get_token_provider().issue_access_token(_domain_user(context, role))
    context.response = context.client.get(_job_url(uuid.uuid4()), headers=_bearer(token))


@then('the response contains a job id with status "{status}"')
def step_job_created(context, status):
    body = context.response.json()
    context.job_id = uuid.UUID(body["job_id"])
    assert body["status"] == status and body["document_id"], body
    assert body["status_url"] == _job_url(context.job_id)


@then('the "Location" header points to the status of that job')
def step_location_header(context):
    assert context.response.headers["location"] == _job_url(context.job_id), context.response.headers


@then('the job reports the file "{file_name}" in status "{status}"')
def step_job_body(context, file_name, status):
    body = context.response.json()
    assert (body["file_name"], body["status"], body["format"]) == (file_name, status, "PDF"), body
    assert body["job_id"] == str(context.job_id)


@then("the response asks for a Bearer token")
def step_www_authenticate(context):
    assert context.response.headers.get("www-authenticate") == "Bearer", context.response.headers
