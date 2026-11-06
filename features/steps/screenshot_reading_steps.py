"""Steps de la lectura de capturas con OCR (T26; escenario 5 de US10)."""
import io

from behave import given, then, when
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.smart_triage.infrastructure.ocr.tesseract_ocr_adapter import TesseractOcrAdapter


def _window(lines: list[str], *, dark: bool = False, blur: int = 0) -> bytes:
    background, foreground = ("#1e1e1e", "#e0e0e0") if dark else ("#f3f3f3", "#202020")
    image = Image.new("RGB", (560, 40 + 30 * len(lines)), background)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=13)
    for i, line in enumerate(lines):
        draw.text((16, 16 + i * 30), line, fill=foreground, font=font)
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@given("a screenshot of an error window with the lines:")
def step_screenshot_lines(context):
    context.screenshot = _window([row["line"] for row in context.table])


@given("a dark mode screenshot of an error window with the lines:")
def step_dark_screenshot_lines(context):
    context.screenshot = _window([row["line"] for row in context.table], dark=True)


@given("a blurry screenshot of an error")
def step_blurry_screenshot(context):
    context.screenshot = _window(["Error de autenticacion de dominio", "Codigo: 0x80070005"], blur=4)


@given("a screenshot without any text")
def step_blank_screenshot(context):
    buffer = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(buffer, format="PNG")
    context.screenshot = buffer.getvalue()


@when("the screenshot is analyzed")
def step_analyze(context):
    context.ocr_result = TesseractOcrAdapter().extract(context.screenshot)


@then('the extracted text contains "{text}"')
def step_text_contains(context, text):
    assert text in context.ocr_result.text, context.ocr_result.text


@then('the error codes "{codes}" are detected')
def step_error_codes(context, codes):
    expected = tuple(c.strip() for c in codes.split(","))
    assert context.ocr_result.error_codes == expected, context.ocr_result.error_codes


@then("the screenshot is marked as illegible")
def step_illegible(context):
    assert not context.ocr_result.is_legible, context.ocr_result


@then("the collaborator is asked for a clearer screenshot or a more detailed description")
def step_feedback(context):
    message = context.ocr_result.feedback_message
    assert message and "captura más nítida" in message and "describe el problema" in message, message
