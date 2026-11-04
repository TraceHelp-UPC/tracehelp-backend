"""Pruebas de integración de POST /api/v1/tickets (T14, US10, TS04). Requieren TEST_DATABASE_URL."""
import io

from PIL import Image

from app.helpdesk.domain.events import TicketRegistered
from app.helpdesk.infrastructure.persistence.models import TicketModel
from app.shared.infrastructure.event_bus import event_bus

URL = "/api/v1/tickets"
FORM = {"title": "No puedo ingresar al ERP", "description": "Error 0x80070005 al iniciar sesión", "impact_level": "HIGH"}


def _image(fmt="PNG", size=(800, 600)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 60, 90)).save(buffer, format=fmt)
    return buffer.getvalue()


def test_register_text_only_ticket(api_client, db_session, workspace_and_users, auth_headers):
    _, collaborator, _ = workspace_and_users
    response = api_client.post(URL, data=FORM, headers=auth_headers(db_session, collaborator))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"].startswith("TK-")
    assert body["status"] == "OPEN" and body["priority"] == "HIGH"
    assert body["reporter_id"] == str(collaborator.id)
    assert body["evidences"] == []
    assert db_session.get(TicketModel, body["id"]) is not None


def test_register_ticket_with_screenshot(api_client, db_session, workspace_and_users, auth_headers):
    _, collaborator, _ = workspace_and_users
    files = [("screenshots", ("error.png", _image(), "image/png"))]
    response = api_client.post(URL, data=FORM, files=files, headers=auth_headers(db_session, collaborator))

    assert response.status_code == 201, response.text
    evidence = response.json()["evidences"][0]
    assert evidence["mime_type"] == "image/png" and evidence["file_name"] == "error.png"


def test_large_screenshot_is_resized(api_client, db_session, workspace_and_users, auth_headers):
    _, collaborator, _ = workspace_and_users
    original = _image("JPEG", (4000, 3000))
    files = [("screenshots", ("captura.jpeg", original, "image/jpeg"))]
    response = api_client.post(URL, data=FORM, files=files, headers=auth_headers(db_session, collaborator))

    assert response.status_code == 201, response.text
    evidence = response.json()["evidences"][0]
    assert evidence["file_name"] == "captura.jpg"
    assert evidence["size_bytes"] < len(original)


def test_rejects_files_that_are_not_images(api_client, db_session, workspace_and_users, auth_headers):
    _, collaborator, _ = workspace_and_users
    files = [("screenshots", ("virus.png", b"esto no es una imagen", "image/png"))]
    response = api_client.post(URL, data=FORM, files=files, headers=auth_headers(db_session, collaborator))
    assert response.status_code == 400


def test_rejects_unsupported_image_format(api_client, db_session, workspace_and_users, auth_headers):
    _, collaborator, _ = workspace_and_users
    files = [("screenshots", ("error.gif", _image("GIF"), "image/gif"))]
    response = api_client.post(URL, data=FORM, files=files, headers=auth_headers(db_session, collaborator))
    assert response.status_code == 400


def test_rejects_missing_required_fields(api_client, db_session, workspace_and_users, auth_headers):
    _, collaborator, _ = workspace_and_users
    response = api_client.post(URL, data={"title": "Sin descripción", "impact_level": "LOW"}, headers=auth_headers(db_session, collaborator))
    assert response.status_code == 422


def test_rejects_blank_description(api_client, db_session, workspace_and_users, auth_headers):
    _, collaborator, _ = workspace_and_users
    response = api_client.post(URL, data={**FORM, "description": "   "}, headers=auth_headers(db_session, collaborator))
    assert response.status_code == 400


def test_requires_authentication(api_client):
    assert api_client.post(URL, data=FORM).status_code == 401


def test_publishes_ticket_registered_event(api_client, db_session, workspace_and_users, auth_headers):
    _, collaborator, _ = workspace_and_users
    received = []
    event_bus.subscribe(TicketRegistered, received.append)
    try:
        response = api_client.post(URL, data=FORM, headers=auth_headers(db_session, collaborator))
    finally:
        event_bus.unsubscribe(TicketRegistered, received.append)
    assert response.status_code == 201
    assert len(received) == 1 and str(received[0].ticket_id) == response.json()["id"]
