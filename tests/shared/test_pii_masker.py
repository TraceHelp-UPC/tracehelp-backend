"""Pruebas del módulo de anonimización PII (T27, CON03).

Las reglas de expresiones regulares se prueban sin spaCy para que el resultado sea determinista.
Las pruebas de nombres de personas se omiten si el modelo es_core_news_sm no está instalado.
"""
import pytest

from app.shared.domain.pii import PiiCategory, SanitizedText, UnsealedTextError, ensure_sealed
from app.shared.infrastructure.pii_masker import SEAL_PREFIX, RegexSpacyPiiMasker, _load_spacy

SECRET = "clave-de-pruebas-del-sello-pii-0123456789"
regex_only = RegexSpacyPiiMasker(SECRET, spacy_model=None)


def _masked(text: str) -> str:
    return regex_only.mask(text).text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Mi correo es carlos.mendoza@empresa.pe", "Mi correo es [REDACTED_EMAIL]"),
        ("Rechazado desde 10.4.2.18 por el firewall", "Rechazado desde [REDACTED_IP] por el firewall"),
        ("Servidor fe80::1ff:fe23:4567:890a sin respuesta", "Servidor [REDACTED_IP] sin respuesta"),
        ("mi DNI 45872319.", "mi DNI [REDACTED_DNI]."),
        ("Documento de identidad: 07234561", "Documento de identidad: [REDACTED_DNI]"),
        ("password=Sup3rS3creta!", "password=[REDACTED_CREDENTIAL]"),
        ('{"contraseña": "Hola2026"}', '{"contraseña": "[REDACTED_CREDENTIAL]"}'),
        ("mi clave es Lima#2026, no funciona", "mi clave es [REDACTED_CREDENTIAL], no funciona"),
        ("Authorization: Bearer abcDEF123456ghiJKL789", "Authorization: Bearer [REDACTED_TOKEN]"),
        ("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.c2lnbmF0dXJh", "jwt [REDACTED_TOKEN]"),
        ("api key AIzaSyA1234567890abcdefghijklmnopqrstu", "api key [REDACTED_TOKEN]"),
        ("postgres://admin:Secreta1@db.local:5432/erp", "postgres://[REDACTED_CREDENTIAL]@db.local:5432/erp"),
        ("Acceso denegado para CORP\\jperez", "Acceso denegado para CORP\\[REDACTED_USER]"),
        ("usuario: mtorres no puede ingresar", "usuario: [REDACTED_USER] no puede ingresar"),
        ("Llamar al 987 654 321", "Llamar al [REDACTED_PHONE]"),
        ("Celular +51 912345678", "Celular [REDACTED_PHONE]"),
    ],
)
def test_masks_sensitive_data(text, expected):
    assert _masked(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Error 0x80070005 al iniciar sesión",
        "Error 80070005 en la actualización",
        "VPN Error 809 a las 10:30:45",
        "Versión 10.0.19045 de Windows",
        "La contraseña es incorrecta, vuelve a intentarlo",
        "Reporte generado el 20261105",
        "El usuario no puede abrir Outlook",
        "Ticket TK-0042 abierto",
    ],
)
def test_keeps_technical_text_that_is_not_personal_data(text):
    assert _masked(text) == text


def test_counts_redactions_without_keeping_original_values():
    result = regex_only.mask("Correo a@b.pe, IP 10.0.0.1 y DNI 45872319")
    assert result.redactions == {PiiCategory.EMAIL: 1, PiiCategory.IP_ADDRESS: 1, PiiCategory.DNI: 1}
    assert result.redaction_count == 3 and result.had_sensitive_data
    assert "45872319" not in repr(result)


def test_masking_is_idempotent():
    once = _masked("token: abc123XYZ987 y correo a@b.pe")
    assert _masked(once) == once


def test_mask_many_keeps_order():
    results = regex_only.mask_many(["sin datos", "IP 192.168.1.10"])
    assert [r.text for r in results] == ["sin datos", "IP [REDACTED_IP]"]


# ----------------------------------------------------------------------------- sello de auditoría
def test_seal_verifies_the_sanitized_text():
    result = regex_only.mask("IP 10.0.0.1")
    assert result.audit_seal.startswith(SEAL_PREFIX)
    assert regex_only.verify(result)
    assert ensure_sealed(result, regex_only) == "IP [REDACTED_IP]"


def test_tampered_text_fails_verification():
    result = regex_only.mask("IP 10.0.0.1")
    tampered = SanitizedText(text="IP 10.0.0.1", audit_seal=result.audit_seal)
    assert not regex_only.verify(tampered)
    with pytest.raises(UnsealedTextError):
        ensure_sealed(tampered, regex_only)


def test_seal_from_another_key_is_rejected():
    other = RegexSpacyPiiMasker("otra-clave-distinta-de-la-original-123", spacy_model=None)
    assert not regex_only.verify(other.mask("hola"))


def test_plain_strings_cannot_be_sent():
    with pytest.raises(UnsealedTextError):
        ensure_sealed("texto sin anonimizar", regex_only)  # type: ignore[arg-type]


def test_requires_a_strong_secret():
    with pytest.raises(ValueError):
        RegexSpacyPiiMasker("corta", spacy_model=None)


def test_missing_spacy_model_falls_back_to_regex():
    masker = RegexSpacyPiiMasker(SECRET, spacy_model="modelo_que_no_existe")
    assert not masker.uses_ner
    assert masker.mask("IP 10.0.0.1").text == "IP [REDACTED_IP]"


# ----------------------------------------------------------------------------- nombres de personas (spaCy)
needs_spacy = pytest.mark.skipif(_load_spacy("es_core_news_sm") is None, reason="Modelo es_core_news_sm no instalado")


@needs_spacy
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hola, soy Carlos Mendoza y no puedo entrar.", "Hola, soy [REDACTED_PERSON] y no puedo entrar."),
        ("El usuario Karim Ramírez reporta el error.", "El usuario [REDACTED_PERSON] reporta el error."),
        ("Excel se cierra al abrir el archivo de Roberto.", "Excel se cierra al abrir el archivo de [REDACTED_PERSON]."),
    ],
)
def test_masks_person_names_with_spacy(text, expected):
    assert RegexSpacyPiiMasker(SECRET).mask(text).text == expected


@needs_spacy
@pytest.mark.parametrize(
    "text",
    [
        "Conexión rechazada por el servidor.",
        "Outlook no sincroniza el correo.",
        "No conecta la VPN, Active Directory rechaza mi cuenta.",
    ],
)
def test_spacy_does_not_mask_common_words_or_products(text):
    assert RegexSpacyPiiMasker(SECRET).mask(text).text == text
