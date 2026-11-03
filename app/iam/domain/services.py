"""Puertos del dominio IAM implementados en infraestructura."""
from abc import ABC, abstractmethod

from app.iam.domain.value_objects import PasswordHash, PlainPassword


class IPasswordHasher(ABC):
    @abstractmethod
    def hash(self, password: PlainPassword) -> PasswordHash:
        """Genera el hash de una contraseña que ya cumple la política."""

    @abstractmethod
    def verify(self, plain: str, password_hash: PasswordHash) -> bool:
        """Compara una contraseña ingresada con el hash almacenado."""
