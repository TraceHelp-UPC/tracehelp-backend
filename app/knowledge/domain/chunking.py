"""Fragmentación (chunking) de manuales con solapamiento y citas exactas (T23, DocumentChunkingDomainService).

Reglas:
- Los fragmentos agrupan párrafos completos hasta unos TARGET_CHARS caracteres.
- Un fragmento no mezcla páginas (PDF) ni secciones (Markdown); así la cita "pág. 14, párr. 3" es exacta.
- Un párrafo más largo que MAX_CHARS se divide por oraciones; una oración gigante, por palabras.
- Cada fragmento repite al inicio las últimas oraciones del anterior (hasta OVERLAP_CHARS) si son de la misma
  página o sección, para no perder el contexto entre fragmentos. Nunca se corta una oración.
- La cita apunta al primer párrafo nuevo del fragmento (no al texto repetido por el solapamiento).
"""
import re
from dataclasses import dataclass

from app.knowledge.domain.technical_document import KnowledgeChunk
from app.knowledge.domain.value_objects import CitationMetadata

TARGET_CHARS = 1000
MAX_CHARS = 1500
OVERLAP_CHARS = 200
MIN_CHUNK_CHARS = 20  # fragmentos más cortos (por ejemplo, un número de página suelto) se descartan

_SENTENCE_END = re.compile(r"(?<=[.!?:;])\s+(?=[\"'¿¡(\[]?[A-ZÁÉÍÓÚÑ0-9])")


@dataclass(frozen=True)
class ExtractedParagraph:
    """Párrafo extraído del manual con su ubicación. page_number es None en Markdown."""

    text: str
    paragraph_number: int
    page_number: int | None = None
    section_title: str | None = None

    @property
    def location(self) -> tuple[int | None, str | None]:
        return self.page_number, self.section_title


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def _split_long(text: str, limit: int) -> list[str]:
    """Divide un texto largo en piezas de hasta limit caracteres, por oraciones y, si hace falta, por palabras."""
    pieces: list[str] = []
    for sentence in split_sentences(text) or [text]:
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            pieces.append(sentence)

    merged: list[str] = []
    for piece in pieces:
        if merged and len(merged[-1]) + 1 + len(piece) <= limit:
            merged[-1] = f"{merged[-1]} {piece}"
        else:
            merged.append(piece)
    return merged


def _overlap_tail(text: str) -> str:
    """Últimas oraciones completas del fragmento que caben en OVERLAP_CHARS."""
    tail: list[str] = []
    size = 0
    for sentence in reversed(split_sentences(text)):
        if size + len(sentence) > OVERLAP_CHARS:
            break
        tail.insert(0, sentence)
        size += len(sentence) + 1
    return " ".join(tail)


class DocumentChunkingDomainService:
    def chunk(self, paragraphs: list[ExtractedParagraph], *, source_file: str) -> list[KnowledgeChunk]:
        chunks: list[KnowledgeChunk] = []
        buffer: list[str] = []
        first: ExtractedParagraph | None = None
        overlap = ""

        def flush() -> None:
            nonlocal buffer, first, overlap
            body = "\n\n".join(buffer).strip()
            if first is not None and len(body) >= MIN_CHUNK_CHARS:
                content = f"{overlap}\n\n{body}" if overlap else body
                chunks.append(
                    KnowledgeChunk(
                        chunk_index=len(chunks),
                        content=content,
                        citation=CitationMetadata(
                            source_file=source_file,
                            page_number=first.page_number,
                            paragraph_number=first.paragraph_number,
                            section_title=first.section_title,
                        ),
                    )
                )
                overlap = _overlap_tail(body)
            buffer, first = [], None

        for paragraph in paragraphs:
            text = re.sub(r"[ \t]+", " ", paragraph.text).strip()
            if not text:
                continue
            # Cambio de página o de sección: se cierra el fragmento y no se arrastra solapamiento
            if first is not None and paragraph.location != first.location:
                flush()
                overlap = ""
            elif first is None and chunks and paragraph.location != (chunks[-1].citation.page_number, chunks[-1].citation.section_title):
                overlap = ""

            for piece in _split_long(text, MAX_CHARS) if len(text) > MAX_CHARS else [text]:
                current = sum(len(p) for p in buffer) + 2 * len(buffer)
                if buffer and current + len(piece) > TARGET_CHARS:
                    flush()
                if first is None:
                    first = paragraph
                buffer.append(piece)
        flush()
        return chunks
