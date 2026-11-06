"""Pruebas del adaptador OCR con Tesseract y del value object OcrExtractionResult (T26).

Las pruebas del adaptador se omiten si Tesseract no está instalado (corren dentro de Docker).
"""
import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.smart_triage.domain.exceptions import InvalidScreenshotError
from app.smart_triage.domain.value_objects import OcrExtractionResult, extract_error_codes
from app.smart_triage.infrastructure.ocr.tesseract_ocr_adapter import TesseractOcrAdapter

needs_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no está instalado")

LINES = (
    "Error de autenticacion de dominio",
    "Codigo: 0x80070005 - Acceso denegado.",
    "VPN Error 809: no se pudo conectar al servidor.",
)


def _screenshot(*, dark=False, font_size=13, blur=0, fmt="PNG") -> bytes:
    """Ventana de error simulada con texto pequeño, como en una captura real."""
    background, foreground = ("#1e1e1e", "#e0e0e0") if dark else ("#f3f3f3", "#202020")
    image = Image.new("RGB", (520, 150), background)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=font_size)
    for i, line in enumerate(LINES):
        draw.text((16, 14 + i * 30), line, fill=foreground, font=font)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    buffer = io.BytesIO()
    image.save(buffer, format=fmt)
    return buffer.getvalue()


# ----------------------------------------------------------------------------- códigos de error (sin Tesseract)
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Codigo: 0x80070005 - Acceso denegado", ("0x80070005",)),
        ("error 0xc0000022 al iniciar", ("0xC0000022",)),
        ("VPN Error 809: no se pudo conectar", ("Error 809",)),
        ("Código de error: 1603", ("Error 1603",)),
        ("ORA-12541: TNS no listener", ("ORA-12541",)),
        ("java.lang.NullPointerException en la línea 4", ("NullPointerException",)),
        ("SQLSTATE[HY000] general error", ("SQLSTATE[HY000]",)),
        ("Error 809 y otra vez Error 809", ("Error 809",)),
        ("Todo funciona correctamente", ()),
    ],
)
def test_extracts_error_codes(text, expected):
    assert extract_error_codes(text) == expected


def test_result_is_legible_with_enough_confident_words():
    result = OcrExtractionResult.from_text("Acceso denegado al recurso", mean_confidence=91.2, confident_word_count=4)
    assert result.is_legible and result.feedback_message is None


@pytest.mark.parametrize(("confidence", "words"), [(30.0, 10), (90.0, 2), (0.0, 0)])
def test_result_asks_for_a_better_capture_when_not_legible(confidence, words):
    result = OcrExtractionResult.from_text("x y", mean_confidence=confidence, confident_word_count=words)
    assert not result.is_legible
    assert "captura más nítida" in result.feedback_message


def test_result_normalizes_whitespace():
    result = OcrExtractionResult.from_text("  Error   809\n\n\n\nVPN  ", mean_confidence=80, confident_word_count=3)
    assert result.text == "Error 809\n\nVPN"


# ----------------------------------------------------------------------------- preprocesamiento (sin Tesseract)
def test_preprocess_converts_to_grayscale_and_upscales_small_images():
    image = TesseractOcrAdapter.preprocess(_screenshot())
    assert image.mode == "L"
    assert image.size == (1040, 300)


def test_preprocess_inverts_dark_mode_screenshots():
    image = TesseractOcrAdapter.preprocess(_screenshot(dark=True))
    # Tras invertir, el fondo (esquina superior izquierda) debe ser claro
    assert image.getpixel((2, 2)) > 200


def test_preprocess_keeps_large_images_size():
    buffer = io.BytesIO()
    Image.new("RGB", (1600, 900), "white").save(buffer, format="PNG")
    assert TesseractOcrAdapter.preprocess(buffer.getvalue()).size == (1600, 900)


@pytest.mark.parametrize("content", [b"esto no es una imagen", b""])
def test_rejects_files_that_are_not_images(content):
    with pytest.raises(InvalidScreenshotError):
        TesseractOcrAdapter().extract(content)


# ----------------------------------------------------------------------------- Tesseract
@needs_tesseract
@pytest.mark.parametrize("kwargs", [{}, {"dark": True}, {"fmt": "JPEG"}])
def test_reads_text_and_error_codes_from_a_screenshot(kwargs):
    result = TesseractOcrAdapter().extract(_screenshot(**kwargs))

    assert result.is_legible, result
    assert "Acceso denegado" in result.text
    assert result.error_codes == ("0x80070005", "Error 809")
    assert result.mean_confidence > 80


@needs_tesseract
def test_blurry_screenshot_is_not_legible():
    result = TesseractOcrAdapter().extract(_screenshot(blur=4))
    assert not result.is_legible
    assert result.feedback_message is not None


@needs_tesseract
def test_screenshot_without_text_is_not_legible():
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(buffer, format="PNG")
    result = TesseractOcrAdapter().extract(buffer.getvalue())
    assert not result.is_legible and result.text == ""
