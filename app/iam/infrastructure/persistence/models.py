"""Modelos ORM del contexto IAM (tablas iam_*).

Por ahora solo workspaces y usuarios, necesarios para las llaves foráneas de Helpdesk.
La lógica de dominio de IAM se implementa en la T05.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.iam.domain.enums import AvailabilityStatus, RoleName, UserStatus


def _enum(enum_cls, name: str) -> Enum:
    return Enum(enum_cls, name=name, native_enum=False, length=30, create_constraint=True, validate_strings=True)


class WorkspaceModel(Base):
    __tablename__ = "iam_workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    subdomain: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class UserModel(Base):
    __tablename__ = "iam_users"
    __table_args__ = (Index("ix_iam_users_workspace_id_role", "workspace_id", "role"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("iam_workspaces.id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[RoleName] = mapped_column(_enum(RoleName, "role_name"), nullable=False, default=RoleName.COLLABORATOR)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[UserStatus] = mapped_column(_enum(UserStatus, "user_status"), nullable=False, default=UserStatus.ACTIVE)
    availability_status: Mapped[AvailabilityStatus] = mapped_column(
        _enum(AvailabilityStatus, "availability_status"), nullable=False, default=AvailabilityStatus.AVAILABLE
    )
    notify_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    notify_inapp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    external_ad_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
