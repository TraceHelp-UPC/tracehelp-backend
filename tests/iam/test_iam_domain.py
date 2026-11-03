"""Pruebas unitarias del dominio IAM (TS03 / US09)."""
import uuid

import pytest

from app.iam.domain.enums import AvailabilityStatus, RoleName, UserStatus
from app.iam.domain.events import UserAuthenticated, UserRegistered
from app.iam.domain.exceptions import (
    InactiveUserError,
    InvalidEmailError,
    InvalidRoleOperationError,
    InvalidUserDataError,
    WeakPasswordError,
)
from app.iam.domain.permissions import Permission, RolePermission
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PasswordHash, PlainPassword
from app.iam.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher

HASHER = BcryptPasswordHasher(rounds=4)  # pocas rondas para que las pruebas sean rápidas


def _user(role: RoleName = RoleName.COLLABORATOR) -> User:
    return User.register(
        workspace_id=uuid.uuid4(),
        full_name="Karim Ramírez",
        email=EmailAddress("Karim.Ramirez@Empresa.pe"),
        password_hash=HASHER.hash(PlainPassword("Segura123")),
        role=role,
        department="TI",
    )


# ---------- EmailAddress ----------
def test_email_is_normalized_to_lowercase():
    assert EmailAddress("  Ana.Lopez@Empresa.PE ").value == "ana.lopez@empresa.pe"


@pytest.mark.parametrize("value", ["", "sin-arroba.pe", "a@b", "a@@empresa.pe", "a b@empresa.pe"])
def test_invalid_emails_are_rejected(value):
    with pytest.raises(InvalidEmailError):
        EmailAddress(value)


# ---------- Contraseñas ----------
@pytest.mark.parametrize("value", ["corta1", "sololetras", "12345678"])
def test_weak_passwords_are_rejected(value):
    with pytest.raises(WeakPasswordError):
        PlainPassword(value)


def test_password_hash_must_be_bcrypt():
    with pytest.raises(WeakPasswordError):
        PasswordHash("texto-plano")


def test_hasher_verifies_correct_password_only():
    hashed = HASHER.hash(PlainPassword("Segura123"))
    assert HASHER.verify("Segura123", hashed) is True
    assert HASHER.verify("Otra1234", hashed) is False
    assert HASHER.verify("", hashed) is False


def test_plain_password_is_not_shown_in_repr():
    assert "Segura123" not in repr(PlainPassword("Segura123"))


# ---------- RolePermission ----------
def test_collaborator_cannot_validate_ai_responses():
    perms = RolePermission.for_role(RoleName.COLLABORATOR)
    assert perms.allows(Permission.TICKETS_CREATE)
    assert not perms.allows(Permission.TRIAGE_VALIDATE_HITL)


def test_analyst_l1_can_validate_and_escalate_but_not_resolve_escalated():
    perms = RolePermission.for_role(RoleName.ANALYST_L1)
    assert perms.allows(Permission.TRIAGE_VALIDATE_HITL)
    assert perms.allows(Permission.TICKETS_ESCALATE)
    assert not perms.allows(Permission.TICKETS_RESOLVE_ESCALATED)


def test_it_leader_manages_configuration_but_not_ticket_queues():
    perms = RolePermission.for_role(RoleName.IT_LEADER)
    assert perms.allows(Permission.KB_WRITE) and perms.allows(Permission.IAM_ADMIN)
    assert not perms.allows(Permission.TICKETS_MANAGE)


# ---------- User ----------
def test_register_creates_active_user_and_emits_event():
    user = _user()
    assert user.status is UserStatus.ACTIVE
    assert user.email.value == "karim.ramirez@empresa.pe"
    events = user.pull_events()
    assert len(events) == 1 and isinstance(events[0], UserRegistered)


@pytest.mark.parametrize("field", ["full_name", "department"])
def test_register_requires_name_and_department(field):
    data = dict(
        workspace_id=uuid.uuid4(),
        full_name="Ana",
        email=EmailAddress("ana@empresa.pe"),
        password_hash=HASHER.hash(PlainPassword("Segura123")),
        role=RoleName.COLLABORATOR,
        department="Ventas",
    )
    data[field] = "  "
    with pytest.raises(InvalidUserDataError):
        User.register(**data)


def test_record_login_updates_timestamp_and_emits_event():
    user = _user()
    user.pull_events()
    user.record_login()
    assert user.last_login_at is not None
    assert isinstance(user.pull_events()[0], UserAuthenticated)


def test_inactive_user_cannot_login_nor_use_permissions():
    user = _user(RoleName.ANALYST_L1)
    user.deactivate()
    with pytest.raises(InactiveUserError):
        user.record_login()
    assert user.has_permission(Permission.TRIAGE_VALIDATE_HITL) is False


def test_only_support_staff_can_change_availability():
    analyst = _user(RoleName.ANALYST_L1)
    analyst.set_availability(AvailabilityStatus.UNAVAILABLE)
    assert analyst.availability_status is AvailabilityStatus.UNAVAILABLE

    with pytest.raises(InvalidRoleOperationError):
        _user(RoleName.COLLABORATOR).set_availability(AvailabilityStatus.UNAVAILABLE)
