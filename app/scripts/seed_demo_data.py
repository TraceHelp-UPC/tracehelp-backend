"""Crea el workspace de demostración y un usuario por rol (T04).

Es idempotente: si el workspace o algún usuario ya existe, no lo duplica.

Uso:
    docker compose exec api python -m app.scripts.seed_demo_data
    docker compose exec api python -m app.scripts.seed_demo_data --password "OtraClave123"
"""
import argparse
import uuid

from sqlalchemy import select

from app.core.database import SessionLocal
from app.iam.domain.enums import RoleName
from app.iam.domain.user import User
from app.iam.domain.value_objects import EmailAddress, PlainPassword
from app.iam.infrastructure.persistence.models import WorkspaceModel
from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.infrastructure.security.bcrypt_password_hasher import BcryptPasswordHasher

WORKSPACE = {"name": "Empresa Demo S.A.C.", "subdomain": "demo"}
DEFAULT_PASSWORD = "TraceHelp2026"

USERS = [
    ("Carlos Mendoza", "colaborador@demo.tracehelp.pe", RoleName.COLLABORATOR, "Finanzas"),
    ("Karim Ramírez", "analista@demo.tracehelp.pe", RoleName.ANALYST_L1, "Mesa de Ayuda"),
    ("Carlos Reátegui", "especialista@demo.tracehelp.pe", RoleName.SPECIALIST_L2, "Infraestructura"),
    ("Roberto Pérez", "lider@demo.tracehelp.pe", RoleName.IT_LEADER, "Gerencia de TI"),
]


def seed(password: str) -> None:
    hasher = BcryptPasswordHasher()
    plain = PlainPassword(password)
    with SessionLocal() as session:
        workspace = session.scalars(
            select(WorkspaceModel).where(WorkspaceModel.subdomain == WORKSPACE["subdomain"])
        ).one_or_none()
        if workspace is None:
            workspace = WorkspaceModel(id=uuid.uuid4(), **WORKSPACE)
            session.add(workspace)
            session.flush()
            print(f"Workspace creado: {workspace.name}")

        users = SqlAlchemyUserRepository(session)
        for full_name, email, role, department in USERS:
            address = EmailAddress(email)
            if users.exists_by_email(address):
                print(f"Ya existe: {email}")
                continue
            users.save(
                User.register(
                    workspace_id=workspace.id,
                    full_name=full_name,
                    email=address,
                    password_hash=hasher.hash(plain),
                    role=role,
                    department=department,
                )
            )
            print(f"Usuario creado: {email} ({role.value})")
        session.commit()
    print(f"Listo. Contraseña de los usuarios nuevos: {password}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga datos de demostración de TraceHelp.")
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    seed(parser.parse_args().password)
