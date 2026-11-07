"""Steps de la feature de gestión de la base de conocimiento (T20, US06).

La ingesta real corre en un hilo aparte con Gemini; en las pruebas el worker está apagado y el step
"the ingestion of the manual finishes" ejecuta el mismo servicio de ingesta con embeddings simulados.
"""
import io
import zipfile

import pymupdf
from behave import given, then, when
from PIL import Image

from app.iam.infrastructure.persistence.user_repository import SqlAlchemyUserRepository
from app.iam.interfaces.rest.dependencies import get_token_provider
from app.knowledge.application.document_ingestion_service import DocumentIngestionService
from app.knowledge.domain.value_objects import MAX_DOCUMENT_BYTES
from app.knowledge.infrastructure.parsing.pdf_markdown_parser import PdfMarkdownParserAdapter
from app.knowledge.infrastructure.persistence.document_storage import DatabaseDocumentStorage
from app.knowledge.infrastructure.persistence.technical_document_repository import (
    SqlAlchemyTechnicalDocumentRepository,
)
from app.shared.infrastructure.event_bus import InMemoryEventBus
from tests.knowledge.test_document_parser import build_pdf
from tests.knowledge.test_ingestion_pipeline import FakeEmbeddings, masker

MIME = {".pdf": "application/pdf", ".md": "text/markdown"}


def _headers(context, role: str) -> dict:
    user = SqlAlchemyUserRepository(context.session).find_by_id(context.users[role].id)
    token, _ = get_token_provider().issue_access_token(user)
    return {"Authorization": f"Bearer {token}"}


def _documents_url(context) -> str:
    return f"/api/v1/workspaces/{context.workspace.id}/documents"


def _inventory(context) -> list[dict]:
    response = context.client.get(_documents_url(context), headers=_headers(context, "IT_LEADER"))
    assert response.status_code == 200, response.text
    return response.json()


def _document(context, title: str) -> dict:
    match = [d for d in _inventory(context) if d["title"] == title]
    assert match, f'"{title}" no aparece en la base de conocimiento: {[d["title"] for d in _inventory(context)]}'
    return match[0]


def _set_file(context, name: str, content: bytes, mime: str | None = None) -> None:
    suffix = name[name.rfind("."):].lower()
    context.manual = (name, content, mime or MIME.get(suffix, "application/octet-stream"))


# --- Archivos -------------------------------------------------------------------------------------------------

@given('a PDF manual "{name}" with {pages:d} pages of text')
def step_pdf_manual(context, name, pages):
    content = build_pdf(
        [[f"Página {n}: para resolver el incidente {n} reinicia el servicio y vuelve a ingresar al sistema."] for n in range(1, pages + 1)]
    )
    _set_file(context, name, content)


@given('a Markdown manual "{name}" with {sections:d} sections')
def step_markdown_manual(context, name, sections):
    body = "\n\n".join(
        f"## Tema {n}\n\nPara resolver el problema del tema {n} cierra la aplicación, espera un minuto y vuelve a abrirla."
        for n in range(1, sections + 1)
    )
    _set_file(context, name, body.encode("utf-8"))


@given('a file "{name}" with {kind}')
def step_other_file(context, name, kind):
    if kind == "a Word document":
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as docx:
            docx.writestr("word/document.xml", "<w:document>Manual</w:document>")
        content = buffer.getvalue()
    elif kind == "a PNG image":
        buffer = io.BytesIO()
        Image.new("RGB", (40, 20), "white").save(buffer, format="PNG")
        content = buffer.getvalue()
    elif kind in ("plain text", "text that is not a PDF"):
        content = "Pasos para conectarse a la VPN corporativa.".encode()
    elif kind == "no content":
        content = b""
    else:
        raise AssertionError(f"Archivo de prueba no definido: {kind}")
    _set_file(context, name, content)


@given('a PDF manual "{name}" larger than 25 MB')
def step_huge_pdf(context, name):
    _set_file(context, name, build_pdf([["Manual enorme."]]) + b"0" * MAX_DOCUMENT_BYTES)


@given('a scanned PDF manual "{name}" without selectable text')
def step_scanned_pdf(context, name):
    document = pymupdf.open()
    page = document.new_page()
    page.draw_rect(pymupdf.Rect(72, 72, 520, 760), color=(0.2, 0.2, 0.2), fill=(0.9, 0.9, 0.9))  # simula una imagen
    content = document.tobytes()
    document.close()
    _set_file(context, name, content)


# --- Acciones -------------------------------------------------------------------------------------------------

def _upload(context, role: str, title: str | None = None) -> None:
    name, content, mime = context.manual
    data = {"title": title} if title else {}
    context.response = context.client.post(
        _documents_url(context), files={"file": (name, content, mime)}, data=data, headers=_headers(context, role)
    )
    if context.response.status_code == 202:
        context.last_document_id = context.response.json()["document_id"]


@when('the "{role}" uploads the manual with the title "{title}"')
def step_upload_with_title(context, role, title):
    _upload(context, role, title)


@when('the "{role}" uploads the manual')
def step_upload(context, role):
    _upload(context, role)


@when("the ingestion of the manual finishes")
def step_run_ingestion(context):
    service = DocumentIngestionService(
        session=context.session,
        documents=SqlAlchemyTechnicalDocumentRepository(context.session),
        storage=DatabaseDocumentStorage(context.session),
        parser=PdfMarkdownParserAdapter(),
        masker=masker,
        embeddings=FakeEmbeddings(),
        events=InMemoryEventBus(),
    )
    service.process(context.last_document_id)


@when('the "{role}" opens the knowledge base')
def step_open_inventory(context, role):
    context.response = context.client.get(_documents_url(context), headers=_headers(context, role))


# --- Verificaciones -------------------------------------------------------------------------------------------

@then('the knowledge base shows "{title}" in status "{status}"')
def step_inventory_status(context, title, status):
    document = _document(context, title)
    assert document["status"] == status, document


@then('the manual "{title}" has {count:d} fragments')
def step_fragments(context, title, count):
    assert _document(context, title)["chunk_count"] == count


@then('the fragments of "{title}" cite the pages of "{file_name}"')
def step_fragment_citations(context, title, file_name):
    import uuid

    document = SqlAlchemyTechnicalDocumentRepository(context.session).find_by_id(
        uuid.UUID(_document(context, title)["document_id"]), with_chunks=True
    )
    labels = [c.citation.label for c in document.chunks]
    assert labels == [f"{file_name}, pág. {n}, párr. 1" for n in range(1, len(labels) + 1)], labels


@then('the manual "{title}" explains that "{text}"')
def step_failure_reason(context, title, text):
    document = _document(context, title)
    assert text in (document["error_message"] or ""), document


@then("the knowledge base is empty")
def step_empty_inventory(context):
    assert _inventory(context) == []


@then('the inventory lists "{title}"')
def step_inventory_lists(context, title):
    assert title in [d["title"] for d in context.response.json()]
