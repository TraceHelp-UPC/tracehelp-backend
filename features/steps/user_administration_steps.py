"""Steps de la administración de usuarios y roles (US09, T71). Reutiliza los steps de auth_steps y common_steps."""
import json
import logging
import uuid
from unittest import mock

from behave import given, step, then, when
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError

from app.analytics.infrastructure.persistence.models import AuditLogModel
from app.iam.domain.enums import RoleName
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PlainPassword
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.shared.domain.specialist_group import SpecialistGroup

USERS_URL = "/api/v1/users"
LOGIN_URL = "/api/v1/auth/login"
PROBLEM_PREFIX = "urn:tracehelp:problems:"
HASHER = BcryptPasswordHasher(rounds=4)
SYMBOLS = "!#$%*+-=?@"
AMBIGUOUS = "0Oo1lI"
INTERNAL_FIELDS = ("password_hash", "external_ad_id", "workspace_id")


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.messages.append(record.getMessage())
        except Exception:  # un mensaje mal formado no debe romper la prueba
            self.messages.append(str(record.msg))


def _repo(context) -> SqlAlchemyUserRepository:
    return SqlAlchemyUserRepository(context.session)


def _add_user(context, workspace_id, email, role, department="TI", group=None, full_name="Usuario Demo") -> User:
    user = User.register(
        workspace_id=workspace_id,
        full_name=full_name,
        email=EmailAddress(email),
        password_hash=HASHER.hash(PlainPassword("Segura123")),
        role=RoleName(role),
        department=department,
        specialist_group=SpecialistGroup(group) if group else None,
    )
    user.pull_events()  # el alta de preparación no es una acción auditada
    _repo(context).save(user)
    return user


def _user(context, email) -> User:
    user = _repo(context).find_by_email(EmailAddress(email))
    assert user is not None, f"No existe el usuario {email}"
    return user


def _login(context, email, password="Segura123") -> dict:
    response = context.client.post(LOGIN_URL, json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _lookup(body, path: str):
    value = body
    for part in path.split("."):
        value = value[int(part)] if isinstance(value, list) else value[part]
    return value


def _audit_rows(context):
    return context.session.execute(
        select(AuditLogModel).where(AuditLogModel.workspace_id == context.workspace_id)
    ).scalars().all()


# --------------------------------------------------------------------------------------------------- preparación
@given('a workspace with these active users, all with password "{password}":')
def step_workspace_with_users(context, password):
    workspace = WorkspaceModel(id=uuid.uuid4(), name="Empresa Demo", subdomain=f"demo-{uuid.uuid4().hex[:6]}")
    context.session.add(workspace)
    context.session.flush()
    context.workspace_id = workspace.id
    for row in context.table:
        _add_user(
            context,
            workspace.id,
            row["email"],
            row["role"],
            department=row["department"],
            group=row["specialist_group"] or None,
            full_name=row["full_name"],
        )
    context.auth_headers = {}
    context.temp_password = None


@given('an active user "{email}" with role "{role}" in another workspace')
def step_user_other_workspace(context, email, role):
    other = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    context.session.add(other)
    context.session.flush()
    _add_user(context, other.id, email, role, full_name="Usuario Externo")


@given("the application logs are being captured")
def step_capture_logs(context):
    handler = _ListHandler()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    context.log_handler = handler

    def _restore():
        root.removeHandler(handler)
        root.setLevel(previous_level)

    context.add_cleanup(_restore)


@given('"{email}" is the acting user')
def step_acting_user(context, email):
    tokens = _login(context, email)
    context.auth_headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    context.acting_email = email


@given("there is no acting user")
def step_no_acting_user(context):
    context.auth_headers = {}


@given('the acting user presents the token "{token}"')
def step_acting_token(context, token):
    context.auth_headers = {"Authorization": f"Bearer {token}"}


@given('the user "{email}" is promoted to specialist of group "{group}"')
def step_promote(context, email, group):
    repo = _repo(context)
    user = repo.find_by_email(EmailAddress(email))
    user.change_role(RoleName.SPECIALIST_L2)
    user.assign_specialist_group(SpecialistGroup(group))
    user.pull_events()
    repo.save(user)


@step("the audit log is cleared")
def step_clear_audit(context):
    context.session.execute(delete(AuditLogModel).where(AuditLogModel.workspace_id == context.workspace_id))
    context.session.flush()


@given("the duplicate-email pre-check is bypassed as in a concurrent request")
def step_bypass_precheck(context):
    patcher = mock.patch.object(SqlAlchemyUserRepository, "exists_by_email", return_value=False)
    patcher.start()
    context.add_cleanup(patcher.stop)


# --------------------------------------------------------------------------------------------------- acciones
@step("the acting user creates a user with the payload")
def step_create(context):
    context.response = context.client.post(USERS_URL, content=context.text, headers={
        **context.auth_headers, "Content-Type": "application/json"})
    if context.response.status_code == 201:
        context.temp_password = context.response.json()["temporary_password"]
        context.created_user = context.response.json()["user"]


@step('the acting user updates the user "{email}" with the payload')
def step_update_by_email(context, email):
    user_id = _user(context, email).id
    _patch(context, str(user_id))


@step('the acting user updates the user with id "{user_id}" with the payload')
def step_update_by_id(context, user_id):
    _patch(context, user_id)


def _patch(context, user_id: str):
    context.response = context.client.patch(
        f"{USERS_URL}/{user_id}",
        content=context.text,
        headers={**context.auth_headers, "Content-Type": "application/json"},
    )


@step('the acting user lists users with query "{query}"')
def step_list(context, query):
    url = f"{USERS_URL}?{query}" if query else USERS_URL
    context.response = context.client.get(url, headers=context.auth_headers)


@step("the acting user lists users without filters")
def step_list_all(context):
    context.response = context.client.get(USERS_URL, headers=context.auth_headers)


@step('the acting user requests "{operation}" on the users API')
def step_generic_request(context, operation):
    headers = {**context.auth_headers, "Content-Type": "application/json"}
    if operation == "GET":
        context.response = context.client.get(USERS_URL, headers=headers)
    elif operation == "POST":
        body = {"full_name": "Lucía Torres", "email": "lucia.torres@empresa.pe", "role": "COLLABORATOR", "department": "TI"}
        context.response = context.client.post(USERS_URL, json=body, headers=headers)
    elif operation == "PATCH":
        target = _user(context, "colaborador@empresa.pe").id
        context.response = context.client.patch(f"{USERS_URL}/{target}", json={"role": "ANALYST_L1"}, headers=headers)
    else:
        raise AssertionError(f"Operación no soportada: {operation}")


@when("the client requests the OpenAPI document")
def step_openapi(context):
    context.response = context.client.get("/openapi.json")


@step("the temporary password is remembered")
def step_remember_password(context):
    context.remembered_password = context.temp_password


# --------------------------------------------------------------------------------------------------- respuesta
@then('the response field "{path}" is "{expected}"')
def step_field_is(context, path, expected):
    actual = _lookup(context.response.json(), path)
    rendered = "null" if actual is None else str(actual).lower() if isinstance(actual, bool) else str(actual)
    assert rendered == expected, f"{path}: se esperaba {expected!r} y llegó {rendered!r}: {context.response.text}"


@then('the problem type is "{slug}"')
def step_problem_type(context, slug):
    assert context.response.headers["content-type"].startswith("application/problem+json"), context.response.headers
    assert context.response.json()["type"] == PROBLEM_PREFIX + slug, context.response.text


@then('the first error field is "{field}"')
def step_first_error_field(context, field):
    assert context.response.json()["errors"][0]["field"] == field, context.response.text


@then("the response is not cached")
def step_not_cached(context):
    assert context.response.headers.get("cache-control") == "no-store", context.response.headers


@then("the response does not expose internal fields")
def step_no_internal_fields(context):
    for name in INTERNAL_FIELDS:
        assert name not in context.response.text, f"La respuesta expone {name}"


@then("the temporary password follows the generation policy")
def step_password_policy(context):
    body = context.response.json()
    password = body["temporary_password"]
    assert len(password) == 12, password
    assert any(c.isupper() for c in password) and any(c.islower() for c in password)
    assert any(c.isdigit() for c in password) and any(c in SYMBOLS for c in password)
    assert not any(c in AMBIGUOUS for c in password), "Tiene caracteres ambiguos"
    assert body["password_notice"], "Falta el aviso de una sola vez"


@then("the temporary password differs from the remembered one")
def step_password_differs(context):
    assert context.temp_password and context.temp_password != context.remembered_password


@then("the created user can sign in with the temporary password")
def step_created_can_sign_in(context):
    email = context.response.json()["user"]["email"]
    response = context.client.post(LOGIN_URL, json={"email": email, "password": context.temp_password})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == email


@then("the temporary password does not appear in the response body")
def step_password_not_in_body(context):
    assert context.temp_password not in context.response.text


@then("the error detail does not mention a workspace")
def step_detail_no_workspace(context):
    assert "workspace" not in context.response.json()["detail"].lower()


@then('the listing has these emails in order')
def step_listing_order(context):
    expected = [row["email"] for row in context.table]
    actual = [item["email"] for item in context.response.json()["items"]]
    assert actual == expected, f"{actual} != {expected}"


@then('the listing contains the email "{email}"')
def step_listing_contains(context, email):
    assert email in [item["email"] for item in context.response.json()["items"]], context.response.text


@then("the listing has {count:d} items")
def step_listing_count(context, count):
    assert len(context.response.json()["items"]) == count, context.response.text


# --------------------------------------------------------------------------------------------------- estado en BD
@then('no user "{email}" exists')
def step_no_user(context, email):
    assert _repo(context).find_by_email(EmailAddress(email)) is None


@then("the workspace has {count:d} users")
def step_workspace_count(context, count):
    total = context.session.execute(
        select(func.count()).select_from(UserModel).where(UserModel.workspace_id == context.workspace_id)
    ).scalar_one()
    assert total == count, total


@then('the user "{email}" has the role "{role}"')
def step_user_role(context, email, role):
    assert _user(context, email).role.value == role


@then('the user "{email}" has the department "{department}"')
def step_user_department(context, email, department):
    assert _user(context, email).department == department


@then('the user "{email}" is active')
def step_user_active(context, email):
    assert _user(context, email).is_active


@then('the user "{email}" has no specialist group')
def step_user_no_group(context, email):
    assert _user(context, email).specialist_group is None


@then('the database refuses the group "{group}" on the user "{email}"')
def step_db_refuses_group(context, group, email):
    nested = context.session.begin_nested()
    refused = False
    try:
        context.session.execute(
            text("UPDATE iam_users SET specialist_group = :g WHERE email = :e"), {"g": group, "e": email}
        )
        context.session.flush()
    except IntegrityError:
        refused = True
    finally:
        nested.rollback()
    assert refused, f"La base aceptó el grupo {group} para {email}"


# --------------------------------------------------------------------------------------------------- auditoría
@then('the audit log has a "{event_type}" entry for "{email}" acted by "{actor_email}"')
def step_audit_entry(context, event_type, email, actor_email):
    entity_id = _user(context, email).id
    actor_id = _user(context, actor_email).id
    matches = [r for r in _audit_rows(context) if r.event_type == event_type and r.entity_id == entity_id]
    assert matches, f"No hay entrada {event_type} para {email}: {[r.event_type for r in _audit_rows(context)]}"
    assert all(r.actor_id == actor_id for r in matches), [(r.event_type, r.actor_id) for r in matches]
    assert all(r.entity_type == "user" for r in matches)
    context.audit_entry = matches[-1]


@then('the audit entry detail field "{key}" is "{expected}"')
def step_audit_detail(context, key, expected):
    assert str(context.audit_entry.detail.get(key)) == expected, context.audit_entry.detail


@then("the audit log has no entries")
def step_audit_empty(context):
    assert [r.event_type for r in _audit_rows(context)] == []


@then("the temporary password does not appear in any audit entry")
def step_password_not_in_audit(context):
    dump = json.dumps(
        [
            {"detail": r.detail, "event_type": r.event_type, "entity_type": r.entity_type}
            for r in _audit_rows(context)
        ],
        default=str,
    )
    assert context.temp_password not in dump
    assert "password" not in dump.lower(), dump


@then("the temporary password does not appear in the captured logs")
def step_password_not_in_logs(context):
    assert context.log_handler.messages, "La captura de logs no recibió nada: la comprobación sería vacía"
    leaked = [m for m in context.log_handler.messages if context.temp_password in m]
    assert not leaked, f"La contraseña temporal aparece en los logs: {len(leaked)} mensajes"


# --------------------------------------------------------------------------------------------------- OpenAPI
@then('the OpenAPI document declares "{method}" "{path}" with the responses "{codes}"')
def step_openapi_declares(context, method, path, codes):
    operation = context.response.json()["paths"][path][method.lower()]
    assert operation.get("summary") and operation.get("description"), f"{method} {path} sin summary/description"
    missing = [c for c in codes.split(",") if c not in operation["responses"]]
    assert not missing, f"{method} {path} no documenta {missing}"
    for code in codes.split(","):
        if code in {"200", "201"}:
            continue
        content = operation["responses"][code].get("content", {})
        assert "application/problem+json" in content, f"{method} {path} {code} sin ejemplo problem+json"


@then('the OpenAPI document has no route "{path}"')
def step_openapi_no_route(context, path):
    assert path not in context.response.json()["paths"]
