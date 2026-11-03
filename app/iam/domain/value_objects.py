"""Value objects del contexto IAM."""
import re
from dataclasses import dataclass, field

from app.iam.domain.exceptions import InvalidEmailError, WeakPasswordError

_EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72  # límite de bcrypt


@dataclass(frozen=True)
class EmailAddress:
    """Correo corporativo normalizado en minúsculas (US09)."""

    value: str

    def __post_init__(self) -> None:
        normalized = (self.value or "").strip().lower()
        if len(normalized) > 255 or not _EMAIL_PATTERN.match(normalized):
            raise InvalidEmailError(f"El correo '{self.value}' no tiene un formato válido.")
        object.__setattr__(self, "value", normalized)

    @property
    def domain(self) -> str:
        return self.value.split("@", 1)[1]

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class PlainPassword:
    """Contraseña en texto plano solo en memoria, validada contra la política mínima. Nunca se persiste."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        password = self.value or ""
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")
        if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise WeakPasswordError("La contraseña es demasiado larga.")
        if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
            raise WeakPasswordError("La contraseña debe incluir al menos una letra y un número.")


@dataclass(frozen=True)
class PasswordHash:
    """Hash criptográfico de la contraseña; garantiza que ninguna credencial se maneje en texto plano."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.value or not self.value.startswith("$2"):
            raise WeakPasswordError("El hash de contraseña no tiene un formato bcrypt válido.")
