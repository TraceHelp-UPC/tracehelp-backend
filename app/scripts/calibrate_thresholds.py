"""Script de calibración empírica de umbrales de similitud coseno (US11, T33).

Ejecuta las 18 consultas de validación de docs/manuales-prueba/README.md contra
EvidenceRetrievalService e imprime la tabla Markdown con el best_score, nivel de
confianza y cita del primer fragmento recuperado.

Uso:
    python -m app.scripts.calibrate_thresholds --workspace-id <UUID>
"""
import argparse
import uuid
from dataclasses import dataclass

from app.core.database import SessionLocal
from app.shared.infrastructure.event_bus import InMemoryEventBus
from app.smart_triage.application.evidence_retrieval_service import RetrieveEvidenceCommand
from app.smart_triage.interfaces.rest.dependencies import build_evidence_retrieval_service


@dataclass(frozen=True)
class ValidationQuery:
    number: int
    query: str
    expected_target: str
    in_domain: bool


VALIDATION_QUERIES: tuple[ValidationQuery, ...] = (
    ValidationQuery(1, "Me sale el error 809 al conectarme a la VPN desde mi casa", "PDF, pág. 1 o 2 (2.1 Error 809)", True),
    ValidationQuery(2, "La VPN dice que el usuario o la contraseña no son válidos, error 691", "PDF, pág. 2 (2.2)", True),
    ValidationQuery(3, "Error 789, la capa de seguridad encontró un error de procesamiento L2TP", "PDF, pág. 2 (2.3)", True),
    ValidationQuery(4, "El ERP muestra ORA-12541 TNS no listener", "PDF, pág. 3 (3.1)", True),
    ValidationQuery(5, "La factura electrónica fue rechazada con el código FE-2335", "PDF, pág. 3 o 4 (3.4)", True),
    ValidationQuery(6, "No puedo abrir la carpeta de Contabilidad en la unidad S, acceso denegado 0x80070005", "PDF, pág. 5 (4.1)", True),
    ValidationQuery(7, "Borré sin querer un archivo de la carpeta compartida, ¿cómo lo recupero?", "PDF, pág. 5 (4.3)", True),
    ValidationQuery(8, "Error 0x00000709 al poner la impresora como predeterminada", "PDF, pág. 5 o 6 (5.2)", True),
    ValidationQuery(9, "Olvidé mi contraseña del correo", "Markdown, sección «Restablecer la contraseña»", True),
    ValidationQuery(10, "Mi cuenta se bloquea sola varias veces al día", "Markdown, sección «Cuenta bloqueada»", True),
    ValidationQuery(11, "Cambié de celular y no puedo aprobar el inicio de sesión en Authenticator", "Markdown, sección «Verificación en dos pasos (MFA)»", True),
    ValidationQuery(12, "Outlook me pide la contraseña una y otra vez", "Markdown, sección «Outlook no se conecta»", True),
    ValidationQuery(13, "No puedo enviar correos porque mi buzón está lleno", "Markdown, sección «Buzón lleno»", True),
    ValidationQuery(14, "En las reuniones de Teams no me escuchan", "Markdown, sección «Microsoft Teams: audio y cámara»", True),
    ValidationQuery(15, "La silla de mi escritorio rechina", "LOW_CONFIDENCE", False),
    ValidationQuery(16, "¿Cuándo pagan la gratificación de diciembre?", "LOW_CONFIDENCE", False),
    ValidationQuery(17, "El aire acondicionado de la sala 3 no enfría", "LOW_CONFIDENCE", False),
    ValidationQuery(18, "Quiero solicitar mis vacaciones", "LOW_CONFIDENCE", False),
)


def run_calibration(workspace_id: uuid.UUID) -> list[dict]:
    results: list[dict] = []
    with SessionLocal() as session:
        service = build_evidence_retrieval_service(session, InMemoryEventBus())
        for item in VALIDATION_QUERIES:
            evaluation = service.retrieve_and_evaluate(RetrieveEvidenceCommand(workspace_id=workspace_id, query=item.query))
            top_citation = evaluation.retrieved[0].citation.label if evaluation.retrieved else "—"
            results.append(
                {
                    "number": item.number,
                    "query": item.query,
                    "expected": item.expected_target,
                    "best_score": evaluation.best_score,
                    "level": evaluation.level.value,
                    "top_citation": top_citation,
                }
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Calibración de umbrales de similitud RAG (T33)")
    parser.add_argument("--workspace-id", required=True, type=uuid.UUID, help="UUID del workspace con los manuales cargados")
    args = parser.parse_args()

    rows = run_calibration(args.workspace_id)
    print("| # | Consulta | Esperado | best_score | Nivel | Primer fragmento |")
    print("| --- | --- | --- | --- | --- | --- |")
    for r in rows:
        print(
            f"| {r['number']} | {r['query']} | {r['expected']} | {r['best_score']:.4f} | {r['level']} | {r['top_citation']} |"
        )


if __name__ == "__main__":
    main()
