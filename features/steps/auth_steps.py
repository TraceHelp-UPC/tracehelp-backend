"""Steps de la feature de autenticación (TS03)."""
import uuid

from behave import given, then, when

from app.core.config import get_settings
from app.iam.domain.enums import RoleName
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PlainPassword
from app.iam.infrastructure.persistence.models import WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher

import jwt

LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
HASHER = BcryptPasswordHasher(rounds=4)


@given('an active user "{email}" with password "{password}" and role "{role}"')
def step_active_user(context, email, password, role):
    workspace = WorkspaceModel(id=uuid.uuid4(), name="Empresa Demo", subdomain=f"demo-{uuid.uuid4().hex[:6]}")
    context.session.add(workspace)
    context.session.flush()
    user = User.register(
        workspace_id=workspace.id,
        full_name="Karim Ramírez",
        email=EmailAddress(email),
        password_hash=HASHER.hash(PlainPassword(password)),
        role=RoleName(role),
        department="TI",
    )
    SqlAlchemyUserRepository(context.session).save(user)


@given('the user "{email}" has been deactivated')
def step_deactivated(context, email):
    repo = SqlAlchemyUserRepository(context.session)
    user = repo.find_by_email(EmailAddress(email))
    user.deactivate()
    repo.save(user)


@given('the user "{email}" has signed in with password "{password}"')
def step_signed_in(context, email, password):
    response = context.client.post(LOGIN_URL, json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    context.tokens = response.json()


@when('the user signs in with email "{email}" and password "{password}"')
def step_sign_in(context, email, password):
    context.response = context.client.post(LOGIN_URL, json={"email": email, "password": password})


@when("the client requests a new access token with the refresh token")
def step_refresh(context):
    context.response = context.client.post(REFRESH_URL, json={"refresh_token": context.tokens["refresh_token"]})


@when('the client requests a new access token with the refresh token "{token}"')
def step_refresh_with(context, token):
    context.response = context.client.post(REFRESH_URL, json={"refresh_token": token})


@when("the client requests a new access token using the access token")
def step_refresh_with_access(context):
    context.response = context.client.post(REFRESH_URL, json={"refresh_token": context.tokens["access_token"]})


@then("the response contains an access token and a refresh token")
def step_has_tokens(context):
    body = context.response.json()
    assert body["access_token"] and body["refresh_token"]
    assert body["token_type"] == "bearer"


@then('the authenticated user has the role "{role}"')
def step_has_role(context, role):
    assert context.response.json()["user"]["role"] == role


@then('the access token includes the permission "{permission}"')
def step_token_permission(context, permission):
    settings = get_settings()
    claims = jwt.decode(
        context.response.json()["access_token"], settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
    )
    assert permission in claims["permissions"]


@then("the response contains a new access token")
def step_new_access_token(context):
    body = context.response.json()
    assert body["access_token"] and body["access_token"] != context.tokens["access_token"]


ME_URL = "/api/v1/auth/me"


@when("the user requests their profile with the access token")
def step_me_with_token(context):
    headers = {"Authorization": f"Bearer {context.tokens['access_token']}"}
    context.response = context.client.get(ME_URL, headers=headers)


@when("the user requests their profile without an access token")
def step_me_without_token(context):
    context.response = context.client.get(ME_URL)


@then('the profile shows the role "{role}"')
def step_profile_role(context, role):
    assert context.response.json()["role"] == role
