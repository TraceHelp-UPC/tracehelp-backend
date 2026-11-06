"""Extracción de texto de manuales PDF (PyMuPDF) y Markdown (markdown-it-py) conservando página y párrafo (T23).

PDF: cada bloque de texto de PyMuPDF es un párrafo; el número de párrafo se reinicia en cada página.
     Se descartan números de página sueltos y encabezados o pies de página que se repiten en muchas páginas.
Markdown: cada párrafo, elemento de lista, bloque de código o tabla es un párrafo; el número se reinicia en cada
     sección y se guarda el título de la sección (el Markdown no tiene páginas).
"""
import re
from collections import Counter

from app.knowledge.application.ports import DocumentParsingError, IDocumentParser
from app.knowledge.domain.chunking import ExtractedParagraph
from app.knowledge.domain.enums import DocumentFormat

_PAGE_NUMBER = re.compile(r"^(?:p[aá]g(?:ina)?\.?\s*)?\d{1,4}(?:\s*(?:/|de|of)\s*\d{1,4})?$", re.I)


def _clean_block(text: str) -> str:
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # palabras cortadas con guion al final de la línea
    text = re.sub(r"\s*\n\s*", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class PdfMarkdownParserAdapter(IDocumentParser):
    def parse(self, content: bytes, document_format: DocumentFormat) -> list[ExtractedParagraph]:
        if document_format is DocumentFormat.PDF:
            return self._parse_pdf(content)
        return self._parse_markdown(content)

    # ------------------------------------------------------------------ PDF
    @staticmethod
    def _parse_pdf(content: bytes) -> list[ExtractedParagraph]:
        import pymupdf

        try:
            document = pymupdf.open(stream=content, filetype="pdf")
        except Exception as exc:  # noqa: BLE001 - PyMuPDF lanza varios tipos según el daño del archivo
            raise DocumentParsingError("El PDF está dañado o no se puede abrir.") from exc

        with document:
            if document.needs_pass:
                raise DocumentParsingError("El PDF está protegido con contraseña. Cárgalo sin protección.")
            pages: list[list[str]] = []
            for page in document:
                blocks = page.get_text("blocks", sort=True)
                pages.append([_clean_block(b[4]) for b in blocks if b[6] == 0 and _clean_block(b[4])])

        if not any(pages):
            raise DocumentParsingError(
                "El PDF no tiene texto seleccionable (parece escaneado). Cárgalo con texto o en Markdown."
            )

        # Encabezados y pies que aparecen en al menos la mitad de las páginas (mínimo 3) no aportan contenido
        repeated = Counter(text for blocks in pages for text in set(blocks))
        threshold = max(3, len(pages) // 2)
        boilerplate = {text for text, count in repeated.items() if count >= threshold and len(pages) >= 3}

        paragraphs: list[ExtractedParagraph] = []
        for page_number, blocks in enumerate(pages, start=1):
            number = 0
            for text in blocks:
                if text in boilerplate or _PAGE_NUMBER.match(text):
                    continue
                number += 1
                paragraphs.append(ExtractedParagraph(text=text, page_number=page_number, paragraph_number=number))
        return paragraphs

    # ------------------------------------------------------------------ Markdown
    @staticmethod
    def _parse_markdown(content: bytes) -> list[ExtractedParagraph]:
        from markdown_it import MarkdownIt

        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentParsingError("El Markdown no está en UTF-8.") from exc

        tokens = MarkdownIt("commonmark").enable("table").parse(text)
        paragraphs: list[ExtractedParagraph] = []
        section: str | None = None
        number = 0
        list_depth = 0
        table_rows: list[str] | None = None
        row: list[str] = []

        def add(value: str) -> None:
            nonlocal number
            value = value.strip()
            if value:
                number += 1
                paragraphs.append(ExtractedParagraph(text=value, paragraph_number=number, section_title=section))

        def inline_text(token) -> str:
            parts = []
            for child in token.children or []:
                if child.type in ("text", "code_inline"):
                    parts.append(child.content)
                elif child.type in ("softbreak", "hardbreak"):
                    parts.append(" ")
                elif child.type == "image":
                    parts.append(child.content)
            return re.sub(r"\s+", " ", "".join(parts)).strip()

        for i, token in enumerate(tokens):
            if token.type == "heading_open":
                section = inline_text(tokens[i + 1])[:200] or section
                number = 0
            elif token.type in ("bullet_list_open", "ordered_list_open"):
                list_depth += 1
            elif token.type in ("bullet_list_close", "ordered_list_close"):
                list_depth -= 1
            elif token.type == "table_open":
                table_rows = []
            elif token.type == "tr_open":
                row = []
            elif token.type == "tr_close" and table_rows is not None:
                table_rows.append(" | ".join(row))
            elif token.type == "table_close" and table_rows is not None:
                add("\n".join(table_rows))
                table_rows = None
            elif token.type == "inline":
                previous = tokens[i - 1].type if i else ""
                if table_rows is not None:
                    row.append(inline_text(token))
                elif previous == "paragraph_open":
                    value = inline_text(token)
                    add(f"- {value}" if list_depth else value)
            elif token.type in ("fence", "code_block"):
                add(token.content)

        if not paragraphs:
            raise DocumentParsingError("El Markdown no tiene texto que se pueda indexar.")
        return paragraphs
