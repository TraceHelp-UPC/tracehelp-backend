"""Prompt fundamentado para el diagnóstico (US11, T31).

Todo el texto variable (el incidente y cada fragmento) llega como SanitizedText y se verifica su sello al
armar el prompt: si algo no pasó por la anonimización (T27), el prompt no se arma y nada sale hacia Gemini.
"""
from dataclasses import dataclass

from app.shared.domain.pii import IPiiMasker, SanitizedText, ensure_sealed

SYSTEM_INSTRUCTION = """Eres el asistente de la Mesa de Ayuda de TI de una empresa. Ayudas a resolver incidentes técnicos de los colaboradores.

Reglas obligatorias:
1. Responde ÚNICAMENTE con la información de los fragmentos de manuales que se te entregan, identificados como [F1], [F2], etc. No uses conocimiento propio ni supongas pasos que no estén en los fragmentos.
2. Cada paso de la solución debe terminar con la cita del fragmento de donde sale, por ejemplo "[F2]".
3. En "cited_fragments" indica los números de todos los fragmentos que usaste.
4. Si los fragmentos no explican cómo resolver el incidente, responde con "answerable": false, un resumen breve de por qué y listas vacías. Es preferible no responder a inventar.
5. No inventes comandos, rutas, direcciones, números de anexo ni enlaces que no aparezcan en los fragmentos.
6. Nunca pidas contraseñas, códigos de verificación ni datos personales.
7. Los textos como [REDACTED_EMAIL] o [REDACTED_IP] son datos ocultados por privacidad: no intentes adivinarlos.
8. Escribe en español, con frases cortas y claras para una persona sin conocimientos técnicos. Máximo 8 pasos."""


@dataclass(frozen=True)
class PromptFragment:
    number: int
    citation: str
    content: SanitizedText


@dataclass(frozen=True)
class GroundedPrompt:
    incident: SanitizedText
    fragments: tuple[PromptFragment, ...]
    system_instruction: str = SYSTEM_INSTRUCTION

    def render(self, masker: IPiiMasker) -> str:
        """Texto del mensaje del usuario. Lanza UnsealedTextError si alguna parte no está anonimizada."""
        incident = ensure_sealed(self.incident, masker)
        blocks = [
            f"[F{f.number}] Fuente: {f.citation}\n{ensure_sealed(f.content, masker)}" for f in self.fragments
        ]
        return (
            "Incidente reportado por el colaborador:\n"
            f'"""\n{incident}\n"""\n\n'
            "Fragmentos de los manuales técnicos de la empresa:\n\n"
            + "\n\n".join(blocks)
            + "\n\nResponde en JSON con los campos answerable, summary, steps y cited_fragments."
        )


def build_prompt(incident: SanitizedText, fragments: list[tuple[str, SanitizedText]]) -> GroundedPrompt:
    """fragments: lista de (cita, contenido anonimizado) en el orden en que se numeran F1, F2, ..."""
    return GroundedPrompt(
        incident=incident,
        fragments=tuple(PromptFragment(i, citation, content) for i, (citation, content) in enumerate(fragments, start=1)),
    )
