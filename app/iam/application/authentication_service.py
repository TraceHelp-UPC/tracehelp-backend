"""Casos de uso de autenticación: login y renovación del access token (TS03)."""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.iam.domain.exceptions import InvalidCredentialsError, InvalidEmailError, InvalidTokenError
from app.iam.domain.repositories import IUserRepository
from app.iam.domain.services import IPasswordHasher
from app.iam.domain.tokens import ITokenProvider, TokenPair
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress

_INVALID_CREDENTIALS = "Correo o contraseña incorrectos."


@dataclass(frozen=True)
class LoginResult:
    user: User
    tokens: TokenPair


class AuthenticationService:
    def __init__(
        self,
        session: Session,
        users: IUserRepository,
        hasher: IPasswordHasher,
        tokens: ITokenProvider,
    ) -> None:
        self._session = session
        self._users = users
        self._hasher = hasher
        self._tokens = tokens

    def login(self, email: str, password: str) -> LoginResult:
        try:
            address = EmailAddress(email)
        except InvalidEmailError as exc:
            raise InvalidCredentialsError(_INVALID_CREDENTIALS) from exc

        user = self._users.find_by_email(address)
        if user is None or not self._hasher.verify(password, user.password_hash):
            raise InvalidCredentialsError(_INVALID_CREDENTIALS)

        user.record_login()  # lanza InactiveUserError si la cuenta no está activa
        self._users.save(user)
        self._session.commit()
        return LoginResult(user=user, tokens=self._tokens.issue_tokens(user))

    def refresh(self, refresh_token: str) -> tuple[str, int]:
        user_id = self._tokens.decode_refresh_token(refresh_token)
        user = self._users.find_by_id(user_id)
        if user is None or not user.is_active:
            raise InvalidTokenError("El usuario del token ya no está habilitado.")
        return self._tokens.issue_access_token(user)
