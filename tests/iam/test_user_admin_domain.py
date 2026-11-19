"""Pruebas unitarias del dominio de administración de usuarios (US09, T69)."""
import uuid

import pytest

from app.analytics.application.audit_log_service import AuditEventHandler
from app.iam.domain.enums import AvailabilityStatus, RoleName, UserStatus
from app.iam.domain.events import (
    UserDeactivated,
    UserProfileUpdated,
    UserReactivated,
    UserRegistered,
    UserRoleChanged,
)
from app.iam.domain.exceptions import InvalidUserDataError, SpecialistGroupNotAllowedError
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PasswordHash, PlainPassword
from app.iam.infrastructure.security.temporary_password_generator import SecretsTemporaryPasswordGenerator
from app.shared.domain.specialist_group import SpecialistGroup

HASH = PasswordHash("$2b$04$abcdefghijklmnopqrstuuJ8Pn6R6qVqzLqL7vR0Qe2b7r6P9q5Gm")
LEADER = uuid.uuid4()


def _user(role=RoleName.ANALYST_L1, group=None) -> User:
    user = User.register(
        workspace_id=uuid.uuid4(),
        full_name="Ana Pérez",
        email=EmailAddress("ana@empresa.pe"),
        password_hash=HASH,
        role=role,
        department="TI",
        specialist_group=group,
        registered_by=LEADER,
    )
    user.pull_events()
    return user


def test_register_specialist_with_group_emits_event_with_actor():
    user = User.register(
        workspace_id=uuid.uuid4(),
        full_name="Lucía",
        email=EmailAddress("l@empresa.pe"),
        password_hash=HASH,
        role=RoleName.SPECIALIST_L2,
        department="Redes",
        specialist_group=SpecialistGroup.REDES,
        registered_by=LEADER,
    )
    event = user.pull_events()[0]
    assert isinstance(event, UserRegistered)
    assert (event.registered_by, event.specialist_group) == (LEADER, "REDES")
    assert user.specialist_group is SpecialistGroup.REDES


def test_register_group_with_non_specialist_role_is_rejected():
    with pytest.raises(SpecialistGroupNotAllowedError):
        _user(RoleName.ANALYST_L1, SpecialistGroup.REDES)


def test_register_rejects_department_longer_than_100():
    with pytest.raises(InvalidUserDataError):
        User.register(
            workspace_id=uuid.uuid4(),
            full_name="Ana",
            email=EmailAddress("a@empresa.pe"),
            password_hash=HASH,
            role=RoleName.COLLABORATOR,
            department="x" * 101,
        )


def test_change_role_clears_group_and_emits_two_events():
    user = _user(RoleName.SPECIALIST_L2, SpecialistGroup.SEGURIDAD)
    user.change_role(RoleName.ANALYST_L1, changed_by=LEADER)
    assert user.specialist_group is None
    role_event, profile_event = user.pull_events()
    assert isinstance(role_event, UserRoleChanged)
    assert (role_event.previous_role, role_event.new_role, role_event.changed_by) == (
        RoleName.SPECIALIST_L2,
        RoleName.ANALYST_L1,
        LEADER,
    )
    assert isinstance(profile_event, UserProfileUpdated)
    assert profile_event.changes == {"specialist_group": {"from": "SEGURIDAD", "to": None}}


def test_change_role_to_same_role_is_noop():
    user = _user(RoleName.ANALYST_L1)
    user.change_role(RoleName.ANALYST_L1, changed_by=LEADER)
    assert user.pull_events() == []


def test_change_role_to_specialist_allows_group_afterwards():
    user = _user(RoleName.ANALYST_L1)
    user.change_role(RoleName.SPECIALIST_L2, changed_by=LEADER)
    user.assign_specialist_group(SpecialistGroup.APLICACIONES, changed_by=LEADER)
    assert user.specialist_group is SpecialistGroup.APLICACIONES
    assert [type(e) for e in user.pull_events()] == [UserRoleChanged, UserProfileUpdated]


def test_assign_group_to_non_specialist_is_rejected_but_none_is_allowed():
    user = _user(RoleName.ANALYST_L1)
    with pytest.raises(SpecialistGroupNotAllowedError):
        user.assign_specialist_group(SpecialistGroup.REDES, changed_by=LEADER)
    user.assign_specialist_group(None, changed_by=LEADER)
    assert user.pull_events() == []


def test_assign_same_group_does_not_emit_event():
    user = _user(RoleName.SPECIALIST_L2, SpecialistGroup.REDES)
    user.assign_specialist_group(SpecialistGroup.REDES, changed_by=LEADER)
    assert user.pull_events() == []


def test_change_department_validates_and_emits_only_on_change():
    user = _user()
    user.change_department("  Soporte  ", changed_by=LEADER)
    assert user.department == "Soporte"
    event = user.pull_events()[0]
    assert event.changes == {"department": {"from": "TI", "to": "Soporte"}}
    user.change_department("Soporte", changed_by=LEADER)
    assert user.pull_events() == []
    with pytest.raises(InvalidUserDataError):
        user.change_department("   ")


def test_deactivate_sets_inactive_unavailable_and_activate_restores_only_status():
    user = _user(RoleName.ANALYST_L1)
    user.deactivate(changed_by=LEADER)
    assert user.status is UserStatus.INACTIVE
    assert user.availability_status is AvailabilityStatus.UNAVAILABLE
    assert isinstance(user.pull_events()[0], UserDeactivated)

    user.deactivate(changed_by=LEADER)
    assert user.pull_events() == []

    user.activate(changed_by=LEADER)
    assert user.status is UserStatus.ACTIVE
    assert user.availability_status is AvailabilityStatus.UNAVAILABLE
    assert isinstance(user.pull_events()[0], UserReactivated)


def test_temporary_password_generator_follows_policy_and_is_random():
    generator = SecretsTemporaryPasswordGenerator()
    passwords = {generator.generate().value for _ in range(50)}
    assert len(passwords) == 50
    for value in passwords:
        assert len(value) == 12
        assert any(c.isupper() for c in value) and any(c.islower() for c in value)
        assert any(c.isdigit() for c in value) and any(c in "!#$%*+-=?@" for c in value)
        assert not set(value) & set("0OolIl1")
        PlainPassword(value)  # cumple la política de contraseñas


def test_audit_entries_for_user_events_use_leader_as_actor_and_hide_sensitive_data():
    handler = AuditEventHandler(masker=object())  # el masker no se usa en estas ramas
    user = _user(RoleName.SPECIALIST_L2, SpecialistGroup.REDES)
    ws = user.workspace_id

    registered = User.register(
        workspace_id=ws,
        full_name="Lucía Torres",
        email=EmailAddress("lucia@empresa.pe"),
        password_hash=HASH,
        role=RoleName.SPECIALIST_L2,
        department="Redes",
        specialist_group=SpecialistGroup.REDES,
        registered_by=LEADER,
    ).pull_events()[0]
    entry = handler.to_audit_entry(registered)
    assert entry.actor_id == LEADER and entry.entity_id == registered.user_id
    assert entry.detail == {"role": "SPECIALIST_L2", "specialist_group": "REDES", "source": "admin"}

    self_registered = handler.to_audit_entry(
        UserRegistered(user_id=user.id, workspace_id=ws, role=RoleName.COLLABORATOR)
    )
    assert self_registered.actor_id == user.id and self_registered.detail["source"] == "self"

    user.change_role(RoleName.ANALYST_L1, changed_by=LEADER)
    user.deactivate(changed_by=LEADER)
    user.activate(changed_by=LEADER)
    entries = [handler.to_audit_entry(e) for e in user.pull_events()]
    assert [e.event_type for e in entries] == [
        "UserRoleChanged",
        "UserProfileUpdated",
        "UserDeactivated",
        "UserReactivated",
    ]
    assert all(e.actor_id == LEADER and e.entity_type == "user" and e.entity_id == user.id for e in entries)
    assert entries[0].detail == {"previous_role": "SPECIALIST_L2", "new_role": "ANALYST_L1"}
    for e in entries:
        assert "email" not in e.detail and "full_name" not in e.detail and "password" not in str(e.detail)
