"""Pruebas de integración de la carga y el estado de manuales (T22, TS01). Requieren TEST_DATABASE_URL."""
import uuid

import pytest

from app.iam.domain.enums import RoleName
from app.iam.infrastructure.persistence.models import UserModel, WorkspaceModel
from app.knowledge.domain.events import TechnicalDocumentUploaded
from app.knowledge.domain.value_objects import MAX_DOCUMENT_BYTES
from app.knowledge.infrastructure.persistence.document_storage import DatabaseDocumentStorage
from app.knowledge.infrastructure.persistence.models import KbDocumentModel
from app.shared.infrastructure.event_bus import event_bus
from tests.conftest import FAKE_HASH

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
MARKDOWN = "# Guía VPN\n\nPaso 1: abre el cliente de VPN.\n".encode()


def _user(db_session, workspace_id, role: RoleName) -> UserModel:
    user = UserModel(
        id=uuid.uuid4(), workspace_id=workspace_id, full_name=f"{role.value} Demo",
        email=f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@demo.pe", password_hash=FAKE_HASH, role=role, department="TI",
    )
    db_session.add(user)
    db_session.flush()
    return user


@pytest.fixture()
def people(db_session, workspace_and_users, auth_headers):
    workspace, collaborator, analyst = workspace_and_users
    leader = _user(db_session, workspace.id, RoleName.IT_LEADER)
    return {
        "workspace": workspace,
        "leader": (leader, auth_headers(db_session, leader)),
        "analyst": (analyst, auth_headers(db_session, analyst)),
        "collaborator": (collaborator, auth_headers(db_session, collaborator)),
    }


def _upload(api_client, people, *, who="leader", name="Manual_VPN.pdf", content=PDF, mime="application/pdf", workspace_id=None, title=None):
    workspace_id = workspace_id or people["workspace"].id
    data = {"title": title} if title else {}
    return api_client.post(
        f"/api/v1/workspaces/{workspace_id}/documents",
        files={"file": (name, content, mime)},
        data=data,
        headers=people[who][1],
    )


def test_leader_uploads_pdf_and_gets_202_with_job(api_client, db_session, people):
    response = _upload(api_client, people)

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["status_url"] == f"/api/v1/documents/jobs/{body['job_id']}"
    assert response.headers["location"] == body["status_url"]

    model = db_session.get(KbDocumentModel, uuid.UUID(body["document_id"]))
    assert model.job_id == uuid.UUID(body["job_id"])
    assert model.uploaded_by == people["leader"][0].id
    assert DatabaseDocumentStorage(db_session).load(model.storage_uri) == PDF


def test_markdown_is_accepted_with_custom_title(api_client, people):
    response = _upload(api_client, people, name="guia-vpn.md", content=MARKDOWN, mime="text/markdown", title="Guía de VPN")
    assert response.status_code == 202, response.text
    job = api_client.get(response.json()["status_url"], headers=people["leader"][1]).json()
    assert job["title"] == "Guía de VPN" and job["format"] == "MARKDOWN"


def test_job_status_reports_the_document(api_client, people):
    upload = _upload(api_client, people).json()
    response = api_client.get(upload["status_url"], headers=people["leader"][1])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] == upload["job_id"] and body["document_id"] == upload["document_id"]
    assert body["status"] == "PENDING" and body["chunk_count"] == 0
    assert body["file_name"] == "Manual_VPN.pdf" and body["size_bytes"] == len(PDF)


def test_list_documents_of_the_workspace(api_client, people):
    _upload(api_client, people, name="primero.pdf")
    _upload(api_client, people, name="segundo.md", content=MARKDOWN, mime="text/markdown")
    response = api_client.get(f"/api/v1/workspaces/{people['workspace'].id}/documents", headers=people["analyst"][1])

    assert response.status_code == 200, response.text
    assert [d["file_name"] for d in response.json()] == ["segundo.md", "primero.pdf"]


@pytest.mark.parametrize(
    ("name", "content", "mime"),
    [
        ("manual.docx", b"PK\x03\x04contenido", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("captura.png", b"\x89PNG\r\n", "image/png"),
        ("falso.pdf", b"esto no es un pdf", "application/pdf"),
        ("vacio.md", b"", "text/markdown"),
    ],
)
def test_rejects_unsupported_or_invalid_files(api_client, db_session, people, name, content, mime):
    response = _upload(api_client, people, name=name, content=content, mime=mime)
    assert response.status_code == 400, response.text
    assert db_session.query(KbDocumentModel).filter_by(workspace_id=people["workspace"].id).count() == 0


def test_rejects_files_over_25_mb(api_client, people):
    response = _upload(api_client, people, content=PDF + b"0" * MAX_DOCUMENT_BYTES)
    assert response.status_code == 400
    assert "25 MB" in response.json()["detail"]


def test_requires_a_valid_token(api_client, people):
    response = api_client.post(
        f"/api/v1/workspaces/{people['workspace'].id}/documents", files={"file": ("m.pdf", PDF, "application/pdf")}
    )
    assert response.status_code == 401
    bad = api_client.post(
        f"/api/v1/workspaces/{people['workspace'].id}/documents",
        files={"file": ("m.pdf", PDF, "application/pdf")},
        headers={"Authorization": "Bearer token-invalido"},
    )
    assert bad.status_code == 401


@pytest.mark.parametrize("who", ["analyst", "collaborator"])
def test_only_kb_writers_can_upload(api_client, people, who):
    assert _upload(api_client, people, who=who).status_code == 403


def test_collaborators_cannot_read_documents(api_client, people):
    upload = _upload(api_client, people).json()
    assert api_client.get(upload["status_url"], headers=people["collaborator"][1]).status_code == 403


def test_other_workspaces_are_not_found(api_client, people):
    assert _upload(api_client, people, workspace_id=uuid.uuid4()).status_code == 404
    listing = api_client.get(f"/api/v1/workspaces/{uuid.uuid4()}/documents", headers=people["leader"][1])
    assert listing.status_code == 404


def test_jobs_from_another_workspace_are_not_found(api_client, db_session, auth_headers, people):
    upload = _upload(api_client, people).json()
    other = WorkspaceModel(id=uuid.uuid4(), name="Otra Empresa", subdomain=f"otra-{uuid.uuid4().hex[:6]}")
    db_session.add(other)
    db_session.flush()
    outsider = _user(db_session, other.id, RoleName.IT_LEADER)
    assert api_client.get(upload["status_url"], headers=auth_headers(db_session, outsider)).status_code == 404


def test_unknown_job_returns_404(api_client, people):
    assert api_client.get(f"/api/v1/documents/jobs/{uuid.uuid4()}", headers=people["leader"][1]).status_code == 404


def test_publishes_uploaded_event_after_commit(api_client, people):
    received = []
    event_bus.subscribe(TechnicalDocumentUploaded, received.append)
    try:
        body = _upload(api_client, people).json()
    finally:
        event_bus.unsubscribe(TechnicalDocumentUploaded, received.append)
    assert len(received) == 1
    assert str(received[0].job_id) == body["job_id"] and str(received[0].document_id) == body["document_id"]
