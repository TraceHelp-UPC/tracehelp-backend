"""Generador de contraseñas temporales con CSPRNG (US09)."""
import secrets

from app.iam.domain.services import ITemporaryPasswordGenerator
from app.iam.domain.value_objects import PlainPassword

# Alfabetos sin caracteres ambiguos (0 O o 1 l I)
_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
_LOWER = "abcdefghijkmnpqrstuvwxyz"
_DIGITS = "23456789"
_SYMBOLS = "!#$%*+-=?@"
PASSWORD_LENGTH = 12


class SecretsTemporaryPasswordGenerator(ITemporaryPasswordGenerator):
    """12 caracteres con al menos una mayúscula, una minúscula, un dígito y un símbolo. No registra nada."""

    def generate(self) -> PlainPassword:
        alphabet = _UPPER + _LOWER + _DIGITS + _SYMBOLS
        chars = [secrets.choice(group) for group in (_UPPER, _LOWER, _DIGITS, _SYMBOLS)]
        chars += [secrets.choice(alphabet) for _ in range(PASSWORD_LENGTH - len(chars))]
        secrets.SystemRandom().shuffle(chars)
        return PlainPassword("".join(chars))
