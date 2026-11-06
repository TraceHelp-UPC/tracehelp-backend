"""Mide la precisión del OCR con capturas reales (T26).

Prepara una carpeta con capturas PNG/JPG y, junto a cada una, un .txt con el mismo nombre que contenga el texto
que se ve en la imagen (transcrito a mano). Ejemplo:

    capturas/
        vpn-error-809.png
        vpn-error-809.txt
        outlook-0x800ccc0e.jpg
        outlook-0x800ccc0e.txt

Uso (dentro de Docker, la carpeta debe estar dentro del proyecto para que el contenedor la vea):
    docker compose exec api python -m app.scripts.evaluate_ocr capturas
    docker compose exec api python -m app.scripts.evaluate_ocr capturas --min-accuracy 0.85

Métricas por captura:
    precisión de caracteres  similitud entre el texto esperado y el extraído (0 a 1, difflib)
    palabras recuperadas     porcentaje de palabras del texto esperado que aparecen en el extraído
    códigos detectados       códigos de error esperados (0x..., Error 809, ORA-...) que el OCR encontró
Las capturas sin .txt solo informan legibilidad, confianza y tiempo.
El comando termina con código 1 si la precisión promedio queda por debajo de --min-accuracy.
"""
import argparse
import re
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from app.smart_triage.domain.value_objects import extract_error_codes
from app.smart_triage.infrastructure.ocr.tesseract_ocr_adapter import TesseractOcrAdapter

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"\s+", " ", text).strip()


def _words(text: str) -> list[str]:
    return re.findall(r"[\wáéíóúñü]+", _normalize(text))


def evaluate(folder: Path, min_accuracy: float) -> int:
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS)
    if not images:
        print(f"No hay capturas PNG/JPG en {folder}")
        return 1

    ocr = TesseractOcrAdapter()
    accuracies, recalls, code_hits, code_total = [], [], 0, 0
    print(f"{'captura':40} {'legible':>7} {'conf.':>6} {'seg.':>5} {'precisión':>9} {'palabras':>8} códigos")
    for image in images:
        started = time.perf_counter()
        result = ocr.extract(image.read_bytes())
        elapsed = time.perf_counter() - started

        expected_file = image.with_suffix(".txt")
        accuracy_txt = recall_txt = codes_txt = "-"
        if expected_file.exists():
            expected = expected_file.read_text(encoding="utf-8")
            accuracy = SequenceMatcher(None, _normalize(expected), _normalize(result.text)).ratio()
            expected_words = _words(expected)
            found_words = set(_words(result.text))
            recall = sum(w in found_words for w in expected_words) / len(expected_words) if expected_words else 1.0
            expected_codes = extract_error_codes(expected)
            hits = sum(code in result.error_codes for code in expected_codes)
            accuracies.append(accuracy)
            recalls.append(recall)
            code_hits += hits
            code_total += len(expected_codes)
            accuracy_txt, recall_txt = f"{accuracy:.2f}", f"{recall:.0%}"
            codes_txt = f"{hits}/{len(expected_codes)}" if expected_codes else "-"

        print(
            f"{image.name[:40]:40} {'sí' if result.is_legible else 'no':>7} {result.mean_confidence:>6.1f} "
            f"{elapsed:>5.1f} {accuracy_txt:>9} {recall_txt:>8} {codes_txt}"
        )

    if not accuracies:
        print("\nNinguna captura tiene su .txt de referencia; no se calculó la precisión.")
        return 0

    mean_accuracy = sum(accuracies) / len(accuracies)
    print(f"\nPrecisión promedio de caracteres: {mean_accuracy:.2%} ({len(accuracies)} capturas con referencia)")
    print(f"Palabras recuperadas en promedio: {sum(recalls) / len(recalls):.2%}")
    if code_total:
        print(f"Códigos de error detectados: {code_hits}/{code_total} ({code_hits / code_total:.0%})")
    if mean_accuracy < min_accuracy:
        print(f"La precisión está por debajo del mínimo de {min_accuracy:.0%}.")
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Mide la precisión del OCR con capturas reales.")
    parser.add_argument("folder", type=Path, help="Carpeta con las capturas y sus .txt de referencia")
    parser.add_argument("--min-accuracy", type=float, default=0.80, help="Precisión mínima aceptada (0 a 1)")
    args = parser.parse_args()
    if not args.folder.is_dir():
        parser.error(f"No existe la carpeta {args.folder}")
    sys.exit(evaluate(args.folder, args.min_accuracy))


if __name__ == "__main__":
    main()
