"""Excepciones del contexto IAM."""
from app.shared.domain.exceptions import DomainError, DomainValidationError, ResourceNotFoundError


class InvalidEmailError(DomainValidationError):
    """El correo no tiene un formato válido."""


class WeakPasswordError(DomainValidationError):
    """La contraseña no cumple la política mínima."""


class InvalidUserDataError(DomainValidationError):
    """Faltan datos obligatorios del usuario o no son válidos."""


class InvalidRoleOperationError(DomainValidationError):
    """La operación no aplica para el rol del usuario."""


class InactiveUserError(DomainError):
    """El usuario no está activo y no puede iniciar sesión (se traduce a HTTP 401/403)."""


class InvalidCredentialsError(DomainError):
    """Correo o contraseña incorrectos (se traduce a HTTP 401). El mensaje no revela cuál de los dos falló."""


class InvalidTokenError(DomainError):
    """Token ausente, mal formado, expirado o de tipo incorrecto (se traduce a HTTP 401)."""


class UserNotFoundError(ResourceNotFoundError):
    """El usuario no existe en el workspace (se traduce a HTTP 404)."""


class EmailAlreadyRegisteredError(DomainError):
    """Ya existe una cuenta con ese correo (se traduce a HTTP 409)."""


class SpecialistGroupNotAllowedError(DomainError):
    """Solo los especialistas L2 pueden tener un grupo (se traduce a HTTP 422)."""


class SelfLockoutError(DomainError):
    """El líder intenta quitarse su propio rol o desactivar su propia cuenta (se traduce a HTTP 422)."""
