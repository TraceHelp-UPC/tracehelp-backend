"""Pruebas de integración de GET/POST/PATCH /api/v1/users (US09, T69)."""
import logging
import uuid

import pytest

from app.iam.domain.enums import RoleName
from app.iam.domain.value_objects import PlainPassword
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.iam.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher
from app.shared.domain.specialist_group import SpecialistGroup
from tests.conftest import FAKE_HASH

USERS = "/api/v1/users"
PASSWORD = "Segura123"


def _model(workspace_id, role, name, group=None, password=PASSWORD):
    return UserModel(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        full_name=name,
        email=f"{name.lower().replace(' ', '.')}-{uuid.uuid4().hex[:5]}@empresa.pe",
        password_hash=BcryptPasswordHasher(rounds=4).hash(PlainPassword(password)).value if password else FAKE_HASH,
        role=role,
        department="TI",
        specialist_group=group,
    )


@pytest.fixture()
def team(db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    leader = _model(workspace.id, RoleName.IT_LEADER, "Roberto Lider")
    specialist = _model(workspace.id, RoleName.SPECIALIST_L2, "Carlos Especialista", SpecialistGroup.INFRAESTRUCTURA)
    db_session.add_all([leader, specialist])
    db_session.flush()
    return {
        "workspace": workspace,
        "leader": leader,
        "analyst": analyst,
        "collaborator": collaborator,
        "specialist": specialist,
        "h": {
            "leader": auth_headers(db_session, leader),
            "analyst": auth_headers(db_session, analyst),
            "collaborator": auth_headers(db_session, collaborator),
            "specialist": auth_headers(db_session, specialist),
        },
    }


def _new_user(**overrides):
    body = {
        "full_name": "Lucía Torres",
        "email": f"Lucia.{uuid.uuid4().hex[:6]}@empresa.pe",
        "role": "ANALYST_L1",
        "department": "Mesa de Ayuda",
    }
    body.update(overrides)
    return body


def test_create_user_returns_temporary_password_once_without_caching(api_client, team):
    response = api_client.post(USERS, json=_new_user(role="SPECIALIST_L2", specialist_group="REDES"), headers=team["h"]["leader"])
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert len(body["temporary_password"]) == 12
    assert "una sola vez" in body["password_notice"]
    user = body["user"]
    assert user["role"] == "SPECIALIST_L2" and user["specialist_group"] == "REDES" and user["is_active"] is True
    assert user["email"] == user["email"].lower()
    assert not {"password_hash", "workspace_id", "external_ad_id"} & set(user)

    # la contraseña temporal sirve para iniciar sesión
    login = api_client.post("/api/v1/auth/login", json={"email": user["email"], "password": body["temporary_password"]})
    assert login.status_code == 200
    assert login.json()["user"]["specialist_group"] == "REDES"


def test_temporary_password_is_not_audited_nor_logged_nor_readable_again(api_client, team, caplog):
    caplog.set_level(logging.DEBUG)
    response = api_client.post(USERS, json=_new_user(), headers=team["h"]["leader"])
    assert response.status_code == 201
    secret = response.json()["temporary_password"]
    new_id = response.json()["user"]["id"]

    audit = api_client.get("/api/v1/audit-log?event_type=UserRegistered", headers=team["h"]["leader"])
    assert audit.status_code == 200
    entries = [e for e in audit.json()["items"] if e["entity_id"] == new_id]
    assert len(entries) == 1
    assert entries[0]["actor_id"] == str(team["leader"].id)
    assert entries[0]["detail"] == {"role": "ANALYST_L1", "specialist_group": None, "source": "admin"}
    assert secret not in audit.text
    assert secret not in caplog.text

    listing = api_client.get(USERS, headers=team["h"]["leader"])
    assert secret not in listing.text and "temporary_password" not in listing.text


def test_create_user_with_invalid_role_is_422_on_role_field(api_client, team):
    response = api_client.post(USERS, json=_new_user(role="SUPERADMIN"), headers=team["h"]["leader"])
    assert response.status_code == 422
    body = response.json()
    assert body["type"].endswith("validation-error")
    assert body["errors"][0]["field"] == "role"


def test_create_user_rejects_password_field_and_group_for_non_specialist(api_client, team):
    leader = team["h"]["leader"]
    assert api_client.post(USERS, json=_new_user(password="Hola12345"), headers=leader).status_code == 422
    response = api_client.post(USERS, json=_new_user(role="ANALYST_L1", specialist_group="REDES"), headers=leader)
    assert response.status_code == 422
    assert response.json()["type"].endswith("specialist-group-not-allowed")


def test_create_user_duplicate_email_is_409_case_insensitive(api_client, team):
    leader = team["h"]["leader"]
    assert api_client.post(USERS, json=_new_user(email="Lucia.Torres@empresa.pe"), headers=leader).status_code == 201
    response = api_client.post(USERS, json=_new_user(email="lucia.torres@empresa.pe"), headers=leader)
    assert response.status_code == 409
    assert response.json()["type"].endswith("email-already-registered")


def test_create_user_translates_unique_violation_from_concurrency_to_409(api_client, team, monkeypatch):
    """Simula la carrera: la comprobación previa no ve al otro alta, pero la restricción UNIQUE de la base sí."""
    from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository

    leader = team["h"]["leader"]
    email = "carrera@empresa.pe"
    assert api_client.post(USERS, json=_new_user(email=email), headers=leader).status_code == 201
    monkeypatch.setattr(SqlAlchemyUserRepository, "exists_by_email", lambda self, address: False)
    response = api_client.post(USERS, json=_new_user(email=email), headers=leader)
    assert response.status_code == 409
    assert response.json()["type"].endswith("email-already-registered")


def test_create_user_with_malformed_email_is_400(api_client, team):
    response = api_client.post(USERS, json=_new_user(email="no-es-correo"), headers=team["h"]["leader"])
    assert response.status_code == 400
    assert response.json()["type"].endswith("invalid-email")


@pytest.mark.parametrize("who", ["analyst", "collaborator", "specialist"])
def test_users_endpoints_require_iam_admin(api_client, team, who):
    headers = team["h"][who]
    target = f"{USERS}/{team['analyst'].id}"
    assert api_client.get(USERS, headers=headers).status_code == 403
    assert api_client.post(USERS, json=_new_user(), headers=headers).status_code == 403
    response = api_client.patch(target, json={"department": "X"}, headers=headers)
    assert response.status_code == 403
    assert response.json()["type"].endswith("forbidden")


def test_users_endpoints_require_authentication(api_client, team):
    assert api_client.get(USERS).status_code == 401


def test_deactivate_user_blocks_login_and_refresh_and_audits(api_client, team):
    leader = team["h"]["leader"]
    analyst = team["analyst"]
    created = api_client.post(USERS, json=_new_user(), headers=leader).json()
    user_id, email, password = created["user"]["id"], created["user"]["email"], created["temporary_password"]
    tokens = api_client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()

    response = api_client.patch(f"{USERS}/{user_id}", json={"is_active": False}, headers=leader)
    assert response.status_code == 200
    body = response.json()
    assert (body["is_active"], body["status"], body["availability_status"]) == (False, "INACTIVE", "UNAVAILABLE")

    assert api_client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 403
    assert api_client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    me = api_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert me.status_code == 401

    audit = api_client.get("/api/v1/audit-log?event_type=UserDeactivated", headers=leader).json()["items"]
    assert [e["actor_id"] for e in audit if e["entity_id"] == user_id] == [str(team["leader"].id)]

    # reactivar
    response = api_client.patch(f"{USERS}/{user_id}", json={"is_active": True}, headers=leader)
    assert response.json()["is_active"] is True
    assert api_client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 200
    assert analyst.id != uuid.UUID(user_id)


def test_leader_cannot_remove_own_role_nor_deactivate_himself(api_client, team):
    leader = team["h"]["leader"]
    me = f"{USERS}/{team['leader'].id}"
    for payload in ({"role": "ANALYST_L1"}, {"is_active": False}):
        response = api_client.patch(me, json=payload, headers=leader)
        assert response.status_code == 422, response.text
        assert response.json()["type"].endswith("self-lockout")
    # lo que sí puede: cambiar su departamento y confirmar su mismo rol
    ok = api_client.patch(me, json={"role": "IT_LEADER", "department": "Gerencia"}, headers=leader)
    assert ok.status_code == 200 and ok.json()["department"] == "Gerencia"


def test_change_role_clears_specialist_group(api_client, team):
    leader = team["h"]["leader"]
    response = api_client.patch(f"{USERS}/{team['specialist'].id}", json={"role": "ANALYST_L1"}, headers=leader)
    assert response.status_code == 200
    assert response.json()["role"] == "ANALYST_L1" and response.json()["specialist_group"] is None


def test_group_rules_on_update(api_client, team):
    leader = team["h"]["leader"]
    analyst_url = f"{USERS}/{team['analyst'].id}"
    rejected = api_client.patch(analyst_url, json={"specialist_group": "REDES"}, headers=leader)
    assert rejected.status_code == 422 and rejected.json()["type"].endswith("specialist-group-not-allowed")

    ok = api_client.patch(analyst_url, json={"role": "SPECIALIST_L2", "specialist_group": "SEGURIDAD"}, headers=leader)
    assert ok.status_code == 200 and ok.json()["specialist_group"] == "SEGURIDAD"

    kept = api_client.patch(analyst_url, json={"department": "Seguridad TI"}, headers=leader)
    assert kept.json()["specialist_group"] == "SEGURIDAD"  # omitido = no se toca

    cleared = api_client.patch(analyst_url, json={"specialist_group": None}, headers=leader)
    assert cleared.status_code == 200 and cleared.json()["specialist_group"] is None


def test_update_validation_and_not_found(api_client, team, db_session):
    leader = team["h"]["leader"]
    url = f"{USERS}/{team['analyst'].id}"
    assert api_client.patch(url, json={}, headers=leader).status_code == 422
    assert api_client.patch(url, json={"role": "SUPERADMIN"}, headers=leader).status_code == 422
    assert api_client.patch(url, json={"is_active": "si"}, headers=leader).status_code == 422
    missing = api_client.patch(f"{USERS}/{uuid.uuid4()}", json={"department": "X"}, headers=leader)
    assert missing.status_code == 404 and missing.json()["type"].endswith("user-not-found")

    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Otra", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    db_session.add(other_ws)
    db_session.flush()
    foreign = _model(other_ws.id, RoleName.ANALYST_L1, "Ajeno")
    db_session.add(foreign)
    db_session.flush()
    assert api_client.patch(f"{USERS}/{foreign.id}", json={"department": "X"}, headers=leader).status_code == 404


def test_patch_without_real_changes_is_200_and_emits_no_events(api_client, team):
    leader = team["h"]["leader"]
    before = api_client.get("/api/v1/audit-log?size=100", headers=leader).json()["total"]
    response = api_client.patch(f"{USERS}/{team['analyst'].id}", json={"role": "ANALYST_L1"}, headers=leader)
    assert response.status_code == 200
    assert api_client.get("/api/v1/audit-log?size=100", headers=leader).json()["total"] == before


def test_list_users_filters_search_and_pagination(api_client, team):
    leader = team["h"]["leader"]
    all_users = api_client.get(USERS, headers=leader).json()
    assert all_users["total"] == 4 and all_users["page"] == 1 and all_users["size"] == 20
    names = [u["full_name"] for u in all_users["items"]]
    assert names == sorted(names)
    assert not {"password_hash", "workspace_id"} & set(all_users["items"][0])

    specialists = api_client.get(f"{USERS}?role=SPECIALIST_L2", headers=leader).json()
    assert [u["role"] for u in specialists["items"]] == ["SPECIALIST_L2"]
    assert api_client.get(f"{USERS}?specialist_group=INFRAESTRUCTURA", headers=leader).json()["total"] == 1
    assert api_client.get(f"{USERS}?specialist_group=REDES", headers=leader).json()["total"] == 0
    assert api_client.get(f"{USERS}?search=CARLOS", headers=leader).json()["total"] == 1
    assert api_client.get(f"{USERS}?search=%25", headers=leader).json()["total"] == 0  # el comodín se escapa

    api_client.patch(f"{USERS}/{team['analyst'].id}", json={"is_active": False}, headers=leader)
    assert api_client.get(f"{USERS}?is_active=false", headers=leader).json()["total"] == 1
    assert api_client.get(f"{USERS}?is_active=true", headers=leader).json()["total"] == 3

    second = api_client.get(f"{USERS}?page=2&size=3", headers=leader).json()
    assert len(second["items"]) == 1 and second["total_pages"] == 2


def test_list_users_invalid_params(api_client, team):
    leader = team["h"]["leader"]
    too_big = api_client.get(f"{USERS}?size=101", headers=leader)
    assert too_big.status_code == 400 and too_big.json()["type"].endswith("invalid-page-request")
    assert api_client.get(f"{USERS}?page=0", headers=leader).status_code == 400
    assert api_client.get(f"{USERS}?page=9", headers=leader).status_code == 400
    assert api_client.get(f"{USERS}?role=SUPERADMIN", headers=leader).status_code == 422


def test_list_is_limited_to_the_token_workspace(api_client, team, db_session):
    other_ws = WorkspaceModel(id=uuid.uuid4(), name="Otra", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    db_session.add(other_ws)
    db_session.flush()
    db_session.add(_model(other_ws.id, RoleName.ANALYST_L1, "Ajeno"))
    db_session.flush()
    assert api_client.get(f"{USERS}?search=ajeno", headers=team["h"]["leader"]).json()["total"] == 0


def test_auth_me_includes_department_and_specialist_group(api_client, team):
    me = api_client.get("/api/v1/auth/me", headers=team["h"]["specialist"])
    assert me.status_code == 200
    assert me.json()["department"] == "TI" and me.json()["specialist_group"] == "INFRAESTRUCTURA"


def test_database_check_rejects_group_for_non_specialist(db_session, team):
    from sqlalchemy.exc import IntegrityError

    team["analyst"].specialist_group = SpecialistGroup.REDES
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()
