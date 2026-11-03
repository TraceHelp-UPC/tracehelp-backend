"""Implementación del hashing de contraseñas con bcrypt."""
import bcrypt

from app.iam.domain.services import IPasswordHasher
from app.iam.domain.value_objects import PasswordHash, PlainPassword


class BcryptPasswordHasher(IPasswordHasher):
    def __init__(self, rounds: int = 12) -> None:
        self._rounds = rounds

    def hash(self, password: PlainPassword) -> PasswordHash:
        hashed = bcrypt.hashpw(password.value.encode("utf-8"), bcrypt.gensalt(rounds=self._rounds))
        return PasswordHash(hashed.decode("utf-8"))

    def verify(self, plain: str, password_hash: PasswordHash) -> bool:
        if not plain:
            return False
        try:
            return bcrypt.checkpw(plain.encode("utf-8")[:72], password_hash.value.encode("utf-8"))
        except ValueError:
            return False
