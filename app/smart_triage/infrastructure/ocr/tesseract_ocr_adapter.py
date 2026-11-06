"""Adaptador OCR con Tesseract local (spa + eng), ya instalado en la imagen Docker (T26).

Preprocesamiento antes de reconocer el texto:
    1. Corrige la orientación EXIF y aplana la transparencia sobre fondo blanco.
    2. Escala de grises.
    3. Invierte las capturas en modo oscuro (Tesseract reconoce mejor texto oscuro sobre fondo claro).
    4. Ampliación x2 de las capturas pequeñas, porque el texto de las interfaces suele medir 10-12 px.
    5. Ajuste automático de contraste.

Si la primera lectura no es legible, se reintenta con el modo de texto disperso (--psm 11), que funciona mejor
en ventanas con texto repartido en varias zonas. La imagen nunca sale del servidor.
"""
import io
import logging
from dataclasses import dataclass

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError

from app.smart_triage.application.ports import IOcrExtractor
from app.smart_triage.domain.exceptions import InvalidScreenshotError
from app.smart_triage.domain.value_objects import CONFIDENT_WORD_THRESHOLD, OcrExtractionResult

logger = logging.getLogger(__name__)

UPSCALE_BELOW_PX = 1200  # lado mayor por debajo del cual se amplía la imagen
UPSCALE_FACTOR = 2
DARK_MODE_BRIGHTNESS = 110  # brillo medio (0-255) por debajo del cual se considera modo oscuro
MAX_PIXELS = 40_000_000


@dataclass(frozen=True)
class _Reading:
    text: str
    mean_confidence: float
    confident_words: int


class TesseractOcrAdapter(IOcrExtractor):
    def __init__(self, languages: str = "spa+eng", timeout_seconds: int = 20) -> None:
        self._languages = languages
        self._timeout = timeout_seconds

    def extract(self, content: bytes) -> OcrExtractionResult:
        image = self.preprocess(content)
        reading = self._read(image, psm=3)
        if not self._is_legible(reading):
            sparse = self._read(image, psm=11)
            if sparse.confident_words > reading.confident_words:
                reading = sparse
        return OcrExtractionResult.from_text(
            reading.text, mean_confidence=reading.mean_confidence, confident_word_count=reading.confident_words
        )

    # ------------------------------------------------------------------ preprocesamiento
    @staticmethod
    def preprocess(content: bytes) -> Image.Image:
        """Devuelve la imagen en escala de grises, ampliada y con contraste ajustada, lista para Tesseract."""
        try:
            with Image.open(io.BytesIO(content)) as probe:
                probe.verify()
            image = Image.open(io.BytesIO(content))
            if image.width * image.height > MAX_PIXELS:
                raise InvalidScreenshotError("La imagen es demasiado grande para analizarla.")
            image.load()
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise InvalidScreenshotError("El archivo no es una imagen PNG o JPG válida.") from exc

        image = ImageOps.exif_transpose(image)
        if image.mode in ("RGBA", "LA", "P"):
            image = image.convert("RGBA")
            background = Image.new("RGBA", image.size, "white")
            image = Image.alpha_composite(background, image)
        gray = image.convert("L")

        if ImageStat.Stat(gray).mean[0] < DARK_MODE_BRIGHTNESS:
            gray = ImageOps.invert(gray)
        if max(gray.size) < UPSCALE_BELOW_PX:
            gray = gray.resize((gray.width * UPSCALE_FACTOR, gray.height * UPSCALE_FACTOR), Image.Resampling.LANCZOS)
        return ImageOps.autocontrast(gray, cutoff=1)

    # ------------------------------------------------------------------ lectura
    def _read(self, image: Image.Image, *, psm: int) -> _Reading:
        import pytesseract

        try:
            data = pytesseract.image_to_data(
                image,
                lang=self._languages,
                config=f"--oem 1 --psm {psm}",
                output_type=pytesseract.Output.DICT,
                timeout=self._timeout,
            )
        except RuntimeError:  # pytesseract lanza RuntimeError cuando se agota el tiempo
            logger.warning("Tesseract superó el tiempo máximo de %s s", self._timeout)
            return _Reading(text="", mean_confidence=0.0, confident_words=0)

        lines: dict[tuple[int, int, int], list[str]] = {}
        confidences: list[float] = []
        confident_words = 0
        for i, word in enumerate(data["text"]):
            word = (word or "").strip()
            confidence = float(data["conf"][i])
            if not word or confidence < 0:
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(word)
            confidences.append(confidence)
            if confidence >= CONFIDENT_WORD_THRESHOLD and any(c.isalnum() for c in word):
                confident_words += 1

        text_lines: list[str] = []
        previous_paragraph = None
        for (block, paragraph, _), words in sorted(lines.items()):
            if previous_paragraph is not None and (block, paragraph) != previous_paragraph:
                text_lines.append("")  # línea en blanco entre párrafos
            text_lines.append(" ".join(words))
            previous_paragraph = (block, paragraph)

        mean = sum(confidences) / len(confidences) if confidences else 0.0
        return _Reading(text="\n".join(text_lines), mean_confidence=mean, confident_words=confident_words)

    @staticmethod
    def _is_legible(reading: _Reading) -> bool:
        return OcrExtractionResult.from_text(
            reading.text, mean_confidence=reading.mean_confidence, confident_word_count=reading.confident_words
        ).is_legible
