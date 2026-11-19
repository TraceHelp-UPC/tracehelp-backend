"""Implementación SQLAlchemy del repositorio de usuarios. No hace commit: lo controla la capa de aplicación."""
import uuid

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.iam.domain.enums import RoleName
from app.iam.domain.enums import UserStatus
from app.iam.domain.repositories import IUserRepository, UserSearchCriteria
from app.iam.domain.user import SUPPORT_ROLES, User
from app.iam.domain.value_objects import EmailAddress, PasswordHash
from app.iam.infrastructure.persistence.models import UserModel
from app.shared.domain.pagination import Page, PageRequest

_FIELDS = (
    "workspace_id",
    "full_name",
    "role",
    "department",
    "status",
    "availability_status",
    "notify_email",
    "notify_inapp",
    "created_at",
    "last_login_at",
    "specialist_group",
)


class SqlAlchemyUserRepository(IUserRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, user: User) -> User:
        model = self._session.get(UserModel, user.id)
        if model is None:
            model = UserModel(id=user.id)
            self._session.add(model)
        for name in _FIELDS:
            setattr(model, name, getattr(user, name))
        model.email = user.email.value
        model.password_hash = user.password_hash.value
        self._session.flush()
        return user

    def find_by_id(self, user_id: uuid.UUID) -> User | None:
        model = self._session.get(UserModel, user_id)
        return self._to_domain(model) if model else None

    def find_by_email(self, email: EmailAddress) -> User | None:
        model = self._session.scalars(select(UserModel).where(UserModel.email == email.value)).one_or_none()
        return self._to_domain(model) if model else None

    def exists_by_email(self, email: EmailAddress) -> bool:
        return bool(self._session.scalar(select(exists().where(UserModel.email == email.value))))

    def find_support_staff_by_workspace(self, workspace_id: uuid.UUID) -> list[User]:
        stmt = (
            select(UserModel)
            .where(UserModel.workspace_id == workspace_id, UserModel.role.in_(SUPPORT_ROLES))
            .order_by(UserModel.full_name.asc())
        )
        return [self._to_domain(m) for m in self._session.scalars(stmt).all()]

    def search(self, criteria: UserSearchCriteria, page: PageRequest) -> Page[User]:
        conditions = [UserModel.workspace_id == criteria.workspace_id]
        if criteria.role is not None:
            conditions.append(UserModel.role == criteria.role)
        if criteria.specialist_group is not None:
            conditions.append(UserModel.specialist_group == criteria.specialist_group)
        if criteria.is_active is True:
            conditions.append(UserModel.status == UserStatus.ACTIVE)
        elif criteria.is_active is False:
            conditions.append(UserModel.status != UserStatus.ACTIVE)
        term = (criteria.search or "").strip()
        if term:
            escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            conditions.append(
                or_(UserModel.full_name.ilike(pattern, escape="\\"), UserModel.email.ilike(pattern, escape="\\"))
            )
        total = self._session.scalar(select(func.count()).select_from(UserModel).where(*conditions)) or 0
        page.ensure_in_range(total)
        stmt = (
            select(UserModel)
            .where(*conditions)
            .order_by(UserModel.full_name.asc(), UserModel.id.asc())
            .offset(page.offset)
            .limit(page.size)
        )
        items = [self._to_domain(m) for m in self._session.scalars(stmt).all()]
        return Page(items=items, page=page.page, size=page.size, total=total)

    @staticmethod
    def _to_domain(model: UserModel) -> User:
        return User(
            id=model.id,
            email=EmailAddress(model.email),
            password_hash=PasswordHash(model.password_hash),
            **{name: getattr(model, name) for name in _FIELDS},
        )
