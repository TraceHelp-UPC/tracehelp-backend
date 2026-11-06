"""Pruebas del adaptador de extracción de PDF (PyMuPDF) y Markdown (markdown-it-py) (T23)."""
import pymupdf
import pytest

from app.knowledge.application.ports import DocumentParsingError
from app.knowledge.domain.enums import DocumentFormat
from app.knowledge.infrastructure.parsing.pdf_markdown_parser import PdfMarkdownParserAdapter

parser = PdfMarkdownParserAdapter()


def build_pdf(pages: list[list[str]], *, header: str | None = None, password: str | None = None) -> bytes:
    """PDF con un bloque de texto por párrafo; opcionalmente un encabezado repetido y un número de página."""
    document = pymupdf.open()
    for number, paragraphs in enumerate(pages, start=1):
        page = document.new_page()
        y = 60
        if header:
            page.insert_text((72, 40), header, fontsize=9)
        for paragraph in paragraphs:
            page.insert_textbox(pymupdf.Rect(72, y, 520, y + 60), paragraph, fontsize=11)
            y += 90
        page.insert_text((300, 800), str(number), fontsize=9)
    options = {}
    if password:
        options = {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": password, "user_pw": password}
    data = document.tobytes(**options)
    document.close()
    return data


def test_pdf_paragraphs_keep_page_and_paragraph_numbers():
    pdf = build_pdf(
        [
            ["Para conectar la VPN abre el cliente corporativo.", "Ingresa con tu usuario de red."],
            ["Si aparece el error 809 revisa los puertos UDP 500 y 4500."],
        ]
    )
    paragraphs = parser.parse(pdf, DocumentFormat.PDF)

    assert [(p.page_number, p.paragraph_number) for p in paragraphs] == [(1, 1), (1, 2), (2, 1)]
    assert paragraphs[2].text == "Si aparece el error 809 revisa los puertos UDP 500 y 4500."


def test_pdf_repeated_headers_and_page_numbers_are_ignored():
    pdf = build_pdf([[f"Contenido de la página {i}."] for i in range(1, 5)], header="Manual interno - Confidencial")
    texts = [p.text for p in parser.parse(pdf, DocumentFormat.PDF)]
    assert texts == [f"Contenido de la página {i}." for i in range(1, 5)]


def test_pdf_without_text_is_rejected():
    document = pymupdf.open()
    document.new_page()
    with pytest.raises(DocumentParsingError, match="escaneado"):
        parser.parse(document.tobytes(), DocumentFormat.PDF)


def test_password_protected_pdf_is_rejected():
    with pytest.raises(DocumentParsingError, match="contraseña"):
        parser.parse(build_pdf([["Secreto"]], password="clave123"), DocumentFormat.PDF)


def test_damaged_pdf_is_rejected():
    with pytest.raises(DocumentParsingError):
        parser.parse(b"%PDF-1.7 esto no es un pdf completo", DocumentFormat.PDF)


MARKDOWN = """# Guía de VPN

Esta guía explica cómo **conectar** la [VPN corporativa](https://intranet).

## Error 809

Si aparece el error 809:

1. Abre los puertos UDP 500 y 4500.
2. Reinicia el servicio de acceso remoto.

```powershell
Restart-Service RasMan
```

| Código | Causa |
| ------ | ----- |
| 809    | Puertos bloqueados |
"""


def test_markdown_paragraphs_keep_section_titles():
    paragraphs = parser.parse(MARKDOWN.encode(), DocumentFormat.MARKDOWN)
    summary = [(p.section_title, p.paragraph_number, p.text) for p in paragraphs]

    assert summary == [
        ("Guía de VPN", 1, "Esta guía explica cómo conectar la VPN corporativa."),
        ("Error 809", 1, "Si aparece el error 809:"),
        ("Error 809", 2, "- Abre los puertos UDP 500 y 4500."),
        ("Error 809", 3, "- Reinicia el servicio de acceso remoto."),
        ("Error 809", 4, "Restart-Service RasMan"),
        ("Error 809", 5, "Código | Causa\n809 | Puertos bloqueados"),
    ]
    assert all(p.page_number is None for p in paragraphs)


def test_markdown_without_text_is_rejected():
    with pytest.raises(DocumentParsingError):
        parser.parse(b"# Solo un titulo\n", DocumentFormat.MARKDOWN)
