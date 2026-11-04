"""Pruebas de integración del repositorio de usuarios (requieren TEST_DATABASE_URL)."""
import uuid

from app.iam.domain.enums import RoleName
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PlainPassword
from app.iam.infrastructure.persistence.models import WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher

HASHER = BcryptPasswordHasher(rounds=4)


def _workspace(db_session) -> WorkspaceModel:
    workspace = WorkspaceModel(id=uuid.uuid4(), name="Empresa Demo", subdomain=f"demo-{uuid.uuid4().hex[:6]}")
    db_session.add(workspace)
    db_session.flush()
    return workspace


def _register(workspace_id, email="luis.vega@empresa.pe", role=RoleName.ANALYST_L1) -> User:
    return User.register(
        workspace_id=workspace_id,
        full_name="Luis Vega",
        email=EmailAddress(email),
        password_hash=HASHER.hash(PlainPassword("Segura123")),
        role=role,
        department="TI",
    )


def test_save_and_find_by_email(db_session):
    repo = SqlAlchemyUserRepository(db_session)
    user = repo.save(_register(_workspace(db_session).id))
    db_session.expire_all()

    loaded = repo.find_by_email(EmailAddress("LUIS.VEGA@empresa.pe"))
    assert loaded is not None and loaded.id == user.id
    assert loaded.role is RoleName.ANALYST_L1
    assert HASHER.verify("Segura123", loaded.password_hash)


def test_exists_by_email(db_session):
    repo = SqlAlchemyUserRepository(db_session)
    repo.save(_register(_workspace(db_session).id, email="existe@empresa.pe"))
    assert repo.exists_by_email(EmailAddress("existe@empresa.pe")) is True
    assert repo.exists_by_email(EmailAddress("no-existe@empresa.pe")) is False


def test_save_updates_existing_user(db_session):
    repo = SqlAlchemyUserRepository(db_session)
    user = repo.save(_register(_workspace(db_session).id, email="cambia@empresa.pe"))
    user.change_role(RoleName.SPECIALIST_L2)
    user.record_login()
    repo.save(user)
    db_session.expire_all()

    loaded = repo.find_by_id(user.id)
    assert loaded.role is RoleName.SPECIALIST_L2
    assert loaded.last_login_at is not None


def test_me_returns_authenticated_user(api_client, db_session, auth_headers):
    workspace = _workspace(db_session)
    user = SqlAlchemyUserRepository(db_session).save(_register(workspace.id, email="me@empresa.pe"))

    class _Model:
        id = user.id

    response = api_client.get("/api/v1/auth/me", headers=auth_headers(db_session, _Model))
    assert response.status_code == 200
    assert response.json()["email"] == "me@empresa.pe"
    assert "triage:validate_hitl" in response.json()["permissions"]


def test_me_rejects_deactivated_user(api_client, db_session, auth_headers):
    repo = SqlAlchemyUserRepository(db_session)
    user = repo.save(_register(_workspace(db_session).id, email="inactivo@empresa.pe"))

    class _Model:
        id = user.id

    headers = auth_headers(db_session, _Model)
    user.deactivate()
    repo.save(user)
    assert api_client.get("/api/v1/auth/me", headers=headers).status_code == 401
