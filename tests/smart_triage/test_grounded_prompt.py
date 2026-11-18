"""Pruebas del prompt fundamentado (T31)."""
import dataclasses

import pytest

from app.shared.domain.pii import UnsealedTextError
from app.smart_triage.application.grounded_prompt import SYSTEM_INSTRUCTION, build_prompt
from tests.smart_triage.test_evidence_retrieval_service import masker


def test_fragments_are_numbered_with_their_citation():
    prompt = build_prompt(
        masker.mask("No conecta la VPN, error 809"),
        [
            ("Manual.pdf, pág. 1, párr. 17", masker.mask("Abre los puertos UDP 500 y 4500.")),
            ("guia.md, sección «Cuenta bloqueada», párr. 1", masker.mask("Espera 15 minutos.")),
        ],
    )
    text = prompt.render(masker)
    assert '"""\nNo conecta la VPN, error 809\n"""' in text
    assert "[F1] Fuente: Manual.pdf, pág. 1, párr. 17\nAbre los puertos UDP 500 y 4500." in text
    assert "[F2] Fuente: guia.md, sección «Cuenta bloqueada», párr. 1\nEspera 15 minutos." in text


def test_personal_data_never_reaches_the_prompt():
    prompt = build_prompt(
        masker.mask("Soy ana.diaz@empresa.pe, mi IP es 192.168.1.20"),
        [("guia.md, párr. 1", masker.mask("Escribe a soporte.vpn@empresa.pe"))],
    )
    text = prompt.render(masker)
    assert "ana.diaz@empresa.pe" not in text and "192.168.1.20" not in text and "soporte.vpn@empresa.pe" not in text


def test_unsealed_text_stops_the_prompt():
    incident = masker.mask("La VPN no conecta")
    tampered = dataclasses.replace(incident, text="La VPN no conecta, mi clave es Secreta123")
    with pytest.raises(UnsealedTextError):
        build_prompt(tampered, []).render(masker)


def test_system_instruction_requires_citations_and_allows_declining():
    assert "ÚNICAMENTE" in SYSTEM_INSTRUCTION and "[F2]" in SYSTEM_INSTRUCTION
    assert '"answerable": false' in SYSTEM_INSTRUCTION
    assert "contraseñas" in SYSTEM_INSTRUCTION
