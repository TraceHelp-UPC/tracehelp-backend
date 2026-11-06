"""Pruebas unitarias de la fragmentación de manuales (T23, DocumentChunkingDomainService)."""
from app.knowledge.domain.chunking import (
    MAX_CHARS,
    OVERLAP_CHARS,
    TARGET_CHARS,
    DocumentChunkingDomainService,
    ExtractedParagraph,
    split_sentences,
)

chunker = DocumentChunkingDomainService()


def _sentence(i: int) -> str:
    return f"Paso {i}: ejecuta el comando de verificación número {i} y confirma que la conexión responde correctamente."


def _paragraph(text: str, number: int, page: int | None = 1, section: str | None = None) -> ExtractedParagraph:
    return ExtractedParagraph(text=text, paragraph_number=number, page_number=page, section_title=section)


def test_small_paragraphs_of_the_same_page_are_grouped():
    paragraphs = [_paragraph(_sentence(i), i) for i in range(1, 4)]
    chunks = chunker.chunk(paragraphs, source_file="Manual_VPN.pdf")

    assert len(chunks) == 1
    assert chunks[0].citation.label == "Manual_VPN.pdf, pág. 1, párr. 1"
    assert all(_sentence(i) in chunks[0].content for i in range(1, 4))


def test_chunks_do_not_mix_pages_and_cite_the_right_page():
    paragraphs = [_paragraph(_sentence(1), 1, page=1), _paragraph(_sentence(2), 1, page=2), _paragraph(_sentence(3), 2, page=2)]
    chunks = chunker.chunk(paragraphs, source_file="Manual.pdf")

    assert [(c.citation.page_number, c.citation.paragraph_number) for c in chunks] == [(1, 1), (2, 1)]
    assert _sentence(1) not in chunks[1].content  # sin solapamiento entre páginas


def test_markdown_sections_are_cited_by_title():
    paragraphs = [
        _paragraph("Instala el cliente VPN desde el portal de software.", 1, page=None, section="Instalación"),
        _paragraph("Si aparece el error 809, abre los puertos UDP 500 y 4500.", 1, page=None, section="Error 809"),
    ]
    chunks = chunker.chunk(paragraphs, source_file="guia.md")
    assert [c.citation.label for c in chunks] == [
        "guia.md, sección «Instalación», párr. 1",
        "guia.md, sección «Error 809», párr. 1",
    ]


def test_long_content_is_split_near_the_target_size_with_sentence_overlap():
    paragraphs = [_paragraph(_sentence(i), i) for i in range(1, 30)]
    chunks = chunker.chunk(paragraphs, source_file="Manual.pdf")

    assert len(chunks) > 2
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    for previous, current in zip(chunks, chunks[1:]):
        tail = split_sentences(previous.content)[-1]
        assert current.content.startswith(tail), "el fragmento debe repetir la última oración del anterior"
        assert len(current.content) <= TARGET_CHARS + MAX_CHARS + OVERLAP_CHARS


def test_citation_points_to_the_first_new_paragraph_not_the_overlap():
    paragraphs = [_paragraph(_sentence(i), i) for i in range(1, 30)]
    chunks = chunker.chunk(paragraphs, source_file="Manual.pdf")
    second = chunks[1]
    number = second.citation.paragraph_number
    body = second.content.split("\n\n", 1)[1]
    assert body.startswith(_sentence(number))


def test_a_huge_paragraph_is_split_by_sentences_without_cutting_them():
    text = " ".join(_sentence(i) for i in range(1, 40))
    chunks = chunker.chunk([_paragraph(text, 7)], source_file="Manual.pdf")

    assert len(chunks) > 1
    assert all(c.citation.paragraph_number == 7 for c in chunks)
    for chunk in chunks:
        for sentence in split_sentences(chunk.content):
            assert sentence.endswith(".")


def test_a_giant_sentence_without_punctuation_is_split_by_words():
    text = " ".join(["palabra"] * 600)  # ~4800 caracteres sin puntos
    chunks = chunker.chunk([_paragraph(text, 1)], source_file="Manual.pdf")
    assert len(chunks) >= 3
    assert all(len(c.content) <= MAX_CHARS + OVERLAP_CHARS + 2 for c in chunks)


def test_tiny_fragments_and_empty_paragraphs_are_skipped():
    chunks = chunker.chunk([_paragraph("  ", 1), _paragraph("14", 2)], source_file="Manual.pdf")
    assert chunks == []
