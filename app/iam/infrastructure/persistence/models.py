"""Modelos ORM del contexto IAM (tablas iam_*)."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.iam.domain.enums import AvailabilityStatus, RoleName, UserStatus
from app.shared.domain.specialist_group import SpecialistGroup


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
    __table_args__ = (
        Index("ix_iam_users_workspace_id_role", "workspace_id", "role"),
        CheckConstraint(
            "specialist_group IS NULL OR role = 'SPECIALIST_L2'", name="specialist_group_role"
        ),
    )

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
    specialist_group: Mapped[SpecialistGroup | None] = mapped_column(
        _enum(SpecialistGroup, "specialist_group"), nullable=True
    )
    notify_email: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    notify_inapp: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    external_ad_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkspaceSettingsModel(Base):
    """Configuración por workspace (US07 RAG, US08 reglas de negocio). Todas las columnas de ajuste son nullable."""

    __tablename__ = "iam_workspace_settings"
    __table_args__ = (
        CheckConstraint(
            "similarity_threshold IS NULL OR similarity_threshold BETWEEN 0.50 AND 0.95",
            name="similarity_threshold_range",
        ),
        CheckConstraint(
            "self_service_threshold IS NULL OR self_service_threshold <= 0.99",
            name="self_service_threshold_max",
        ),
        CheckConstraint(
            "self_service_threshold IS NULL OR similarity_threshold IS NULL "
            "OR self_service_threshold >= similarity_threshold",
            name="self_service_ge_similarity",
        ),
        CheckConstraint(
            "retrieval_top_k IS NULL OR retrieval_top_k BETWEEN 1 AND 10",
            name="retrieval_top_k_range",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iam_workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    similarity_threshold: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    self_service_threshold: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    retrieval_top_k: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    strict_grounding: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("iam_users.id", ondelete="SET NULL"),
        nullable=True,
    )
