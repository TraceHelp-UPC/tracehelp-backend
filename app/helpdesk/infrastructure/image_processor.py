"""Validación y compresión de capturas de pantalla con Pillow."""
import io
from pathlib import PurePath

from PIL import Image, ImageOps, UnidentifiedImageError

from app.helpdesk.application.ports import IImageProcessor, ProcessedImage
from app.helpdesk.domain.exceptions import InvalidVisualEvidenceError

MAX_SIDE_PX = 1600  # suficiente para leer texto de errores con OCR
_FORMATS = {"PNG": ("image/png", ".png"), "JPEG": ("image/jpeg", ".jpg")}
Image.MAX_IMAGE_PIXELS = 40_000_000  # evita imágenes gigantes maliciosas


class PillowImageProcessor(IImageProcessor):
    def process(self, content: bytes, file_name: str) -> ProcessedImage:
        try:
            with Image.open(io.BytesIO(content)) as probe:
                probe.verify()
            image = Image.open(io.BytesIO(content))
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise InvalidVisualEvidenceError(
                f"El archivo '{file_name}' no es una imagen válida. Solo se aceptan PNG o JPG."
            ) from exc

        if image.format not in _FORMATS:
            raise InvalidVisualEvidenceError(
                f"Formato de imagen no permitido en '{file_name}'. Solo se aceptan PNG o JPG."
            )
        source_format = image.format
        mime_type, extension = _FORMATS[source_format]

        image = ImageOps.exif_transpose(image)
        resized = max(image.size) > MAX_SIDE_PX
        if resized:
            image.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        if source_format == "JPEG":
            image.convert("RGB").save(buffer, format="JPEG", quality=85, optimize=True)
        else:
            image.save(buffer, format="PNG", optimize=True)
        processed = buffer.getvalue()

        # Si recomprimir no reduce el tamaño, se conserva el original
        if not resized and len(processed) >= len(content):
            processed = content

        stem = PurePath(file_name or "captura").stem[:200] or "captura"
        return ProcessedImage(content=processed, mime_type=mime_type, file_name=f"{stem}{extension}")
