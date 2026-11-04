"""Excepciones del contexto IAM."""
from app.shared.domain.exceptions import DomainError, DomainValidationError


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
