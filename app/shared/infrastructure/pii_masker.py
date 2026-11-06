"""Adaptador de anonimización con expresiones regulares y spaCy, y sello HMAC de auditoría (T27).

Orden de aplicación (importa: cada regla trabaja sobre el resultado de la anterior):
    1. Llaves privadas, credenciales en URLs y pares clave=valor (password=..., token: ...).
    2. Tokens: Bearer, JWT y claves de API conocidas o cadenas aleatorias largas.
    3. Correos, IP (v4 y v6), DNI, teléfonos y usuarios (DOMINIO\\usuario, usuario: x).
    4. Nombres de personas detectados por spaCy (es_core_news_sm, etiqueta PER).

Si el modelo de spaCy no está instalado, se registra una advertencia y se aplican solo las expresiones regulares.
El sello es HMAC-SHA256 del texto anonimizado con PII_AUDIT_SECRET; prueba que el texto salió de este módulo.
"""
import hashlib
import hmac
import logging
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings
from app.shared.domain.pii import PLACEHOLDERS, IPiiMasker, PiiCategory, SanitizedText

logger = logging.getLogger(__name__)

SEAL_PREFIX = "hmac-sha256:v1:"
C = PiiCategory


@dataclass(frozen=True)
class _Rule:
    category: PiiCategory
    pattern: re.Pattern
    # Grupo con el dato sensible; el resto de la coincidencia (por ejemplo, "password=") se conserva
    group: int | str = 0
    # Filtro opcional: recibe la coincidencia y devuelve False si no se debe ocultar
    accept: Callable[[re.Match], bool] | None = None


# ----------------------------------------------------------------------------- filtros
_ERROR_CONTEXT = re.compile(r"(?:error|err|c[oó]digo|code|hresult|ticket|tk|incidente|n[uú]mero|nro|#)\W{0,3}$", re.I)
_DNI_CONTEXT = re.compile(r"(?:dni|documento|doc\.?\s*de\s*identidad|d\.n\.i\.?)\W{0,5}$", re.I)


def _looks_like_dni(match: re.Match) -> bool:
    """Un número de 8 dígitos se trata como DNI salvo que sea claramente un código de error o una fecha."""
    before = match.string[max(0, match.start() - 25) : match.start()]
    if _DNI_CONTEXT.search(before):
        return True
    if _ERROR_CONTEXT.search(before):
        return False
    digits = match.group(0)
    year, month, day = int(digits[:4]), int(digits[4:6]), int(digits[6:])
    is_date = 1990 <= year <= 2099 and 1 <= month <= 12 and 1 <= day <= 31
    return not is_date


def _looks_like_secret(match: re.Match) -> bool:
    """Para 'mi clave es X', X debe parecer una contraseña: 4 o más caracteres con un dígito o un símbolo."""
    return len(match.group("value")) >= 4 and bool(re.search(r"[\d!@#$%^&*()_+=\-{}\[\]|\\:;\"'<>,.?/~`]", match.group("value")))


def _random_looking(match: re.Match) -> bool:
    """Cadenas largas con letras y dígitos mezclados (claves de API, hashes de sesión)."""
    value = match.group(0)
    return any(c.isdigit() for c in value) and any(c.isalpha() for c in value) and not value.isdigit()


_SECRET_KEYS = (
    r"password|passwd|pwd|pass|contrase(?:ñ|n)a|clave|passcode|secret|secreto|"
    r"api[_-]?key|apikey|access[_-]?key|client[_-]?secret|private[_-]?key"
)
_TOKEN_KEYS = r"token|access[_-]?token|refresh[_-]?token|session[_-]?id|sessionid|cookie|authorization"

_RULES: tuple[_Rule, ...] = (
    _Rule(C.TOKEN, re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    # usuario:clave@ dentro de una URL (postgres://admin:Secreta1@host)
    _Rule(C.CREDENTIAL, re.compile(r"(?<=://)(?P<value>[^\s:/@]+:[^\s@/]+)(?=@)"), group="value"),
    # password=..., "token": "...", Contraseña: ...
    _Rule(
        C.CREDENTIAL,
        re.compile(rf"\b(?:{_SECRET_KEYS})\b[\"']?\s*[:=]\s*[\"']?(?P<value>[^\s\"',;]+)", re.I),
        group="value",
    ),
    _Rule(
        C.TOKEN,
        re.compile(rf"\b(?:{_TOKEN_KEYS})\b[\"']?\s*[:=]\s*[\"']?(?:Bearer\s+)?(?P<value>[^\s\"',;]+)", re.I),
        group="value",
    ),
    # "mi contraseña es Hola123", "the password is P@ss"
    _Rule(
        C.CREDENTIAL,
        re.compile(rf"\b(?:{_SECRET_KEYS})\s+(?:es|era|is|actual|nueva)\s+(?P<value>\S+?)(?=[.,;:!?)]*(?:\s|$))", re.I),
        group="value",
        accept=_looks_like_secret,
    ),
    _Rule(C.TOKEN, re.compile(r"\bBearer\s+(?P<value>[A-Za-z0-9\-._~+/]{8,}=*)"), group="value"),
    _Rule(C.TOKEN, re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*")),
    _Rule(
        C.TOKEN,
        re.compile(
            r"\b(?:AIza[0-9A-Za-z\-_]{35}|sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{30,}|"
            r"xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|re_[A-Za-z0-9_]{20,})\b"
        ),
    ),
    _Rule(C.TOKEN, re.compile(r"(?<![\w-])[A-Za-z0-9_\-+]{32,}={0,2}(?![\w-])"), accept=_random_looking),
    _Rule(C.EMAIL, re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b")),
    _Rule(
        C.IP_ADDRESS,
        re.compile(r"(?<![\w.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\w]|\.\d)"),
    ),
    _Rule(
        C.IP_ADDRESS,
        re.compile(
            r"(?<![\w:])(?:(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}|"
            r"(?:[0-9A-Fa-f]{1,4}:){1,6}:(?:[0-9A-Fa-f]{1,4}:){0,5}[0-9A-Fa-f]{1,4}|::1)(?![\w:])"
        ),
    ),
    _Rule(C.DNI, re.compile(r"(?<![\w\-/])(?<!\d\.)\d{8}(?![\w\-/]|\.\d)"), accept=_looks_like_dni),
    # Celulares de Perú: 9 dígitos que empiezan con 9, con o sin +51
    _Rule(C.PHONE, re.compile(r"(?<![\w+])(?:\+?51[\s-]?)?9\d{2}[\s-]?\d{3}[\s-]?\d{3}(?!\d)")),
    _Rule(C.USERNAME, re.compile(r"\b[A-Z][A-Z0-9-]{1,14}\\(?P<value>[A-Za-z][\w.$-]{1,63})"), group="value"),
    _Rule(
        C.USERNAME,
        re.compile(r"\b(?:usuario|user(?:name)?|login|cuenta|account)\b\s*[:=]\s*(?P<value>[A-Za-z][\w.\\-]{1,63})", re.I),
        group="value",
    ),
)

# Palabras que spaCy suele confundir con nombres de personas en tickets de soporte
_NOT_PERSONS = {
    "hola", "buenos días", "buenas tardes", "buenas noches", "saludos", "gracias", "estimado", "estimada",
    "error", "windows", "outlook", "excel", "word", "teams", "office", "microsoft", "google", "chrome",
    "sap", "erp", "vpn", "active directory", "azure", "linux", "oracle", "jira", "zoom", "onedrive",
    "sharepoint", "powerpoint", "gmail", "android", "iphone", "wifi", "dns", "dhcp", "tracehelp",
}
_GREETINGS = {"hola", "buenos", "buenas", "saludos", "estimado", "estimada", "gracias"}


def _seal(secret: str, text: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()
    return SEAL_PREFIX + digest


@lru_cache(maxsize=2)
def _load_spacy(model_name: str):
    try:
        import spacy

        # Solo se necesita el reconocedor de entidades
        return spacy.load(model_name, disable=["parser", "lemmatizer", "attribute_ruler", "morphologizer"])
    except Exception:  # noqa: BLE001 - sin el modelo se continúa solo con expresiones regulares
        logger.warning("No se pudo cargar el modelo spaCy '%s'; la anonimización usará solo expresiones regulares.", model_name)
        return None


class RegexSpacyPiiMasker(IPiiMasker):
    def __init__(self, secret_key: str, *, spacy_model: str | None = "es_core_news_sm") -> None:
        if not secret_key or len(secret_key) < 16:
            raise ValueError("PII_AUDIT_SECRET debe tener al menos 16 caracteres.")
        self._secret = secret_key
        self._nlp = _load_spacy(spacy_model) if spacy_model else None

    @property
    def uses_ner(self) -> bool:
        return self._nlp is not None

    # ------------------------------------------------------------------ API pública
    def mask(self, text: str) -> SanitizedText:
        return self.mask_many([text])[0]

    def mask_many(self, texts: Sequence[str]) -> list[SanitizedText]:
        partial = [self._apply_rules(t or "") for t in texts]
        if self._nlp is not None:
            docs = self._nlp.pipe([p[0] for p in partial], batch_size=32)
            partial = [self._mask_persons(doc, text, counts) for doc, (text, counts) in zip(docs, partial, strict=True)]
        return [
            SanitizedText(text=text, audit_seal=_seal(self._secret, text), redactions=dict(counts))
            for text, counts in partial
        ]

    def verify(self, sanitized: SanitizedText) -> bool:
        return hmac.compare_digest(sanitized.audit_seal or "", _seal(self._secret, sanitized.text))

    # ------------------------------------------------------------------ reglas
    @staticmethod
    def _apply_rules(text: str) -> tuple[str, Counter]:
        counts: Counter = Counter()
        for rule in _RULES:
            placeholder = PLACEHOLDERS[rule.category]

            def replace(match: re.Match, rule=rule, placeholder=placeholder) -> str:
                if rule.accept is not None and not rule.accept(match):
                    return match.group(0)
                counts[rule.category] += 1
                if rule.group == 0:
                    return placeholder
                start, end = match.span(rule.group)
                offset = match.start()
                whole = match.group(0)
                return whole[: start - offset] + placeholder + whole[end - offset :]

            text = rule.pattern.sub(replace, text)
        return text, counts

    @staticmethod
    def _mask_persons(doc, text: str, counts: Counter) -> tuple[str, Counter]:
        spans = []
        for ent in doc.ents:
            if ent.label_ != "PER":
                continue
            tokens = list(ent)
            # spaCy suele incluir el saludo: "Hola Carlos" -> "Carlos"
            while tokens and tokens[0].text.lower().strip(",.") in _GREETINGS:
                tokens = tokens[1:]
            if not tokens:
                continue
            # Una sola palabra al inicio de una oración suele ser un sustantivo con mayúscula ("Conexión rechazada")
            if len(tokens) == 1 and (tokens[0].i == 0 or doc[tokens[0].i - 1].text in {".", "!", "?", ":", "\n"}):
                continue
            start, end = tokens[0].idx, tokens[-1].idx + len(tokens[-1].text)
            value = text[start:end]
            if (
                value.lower() in _NOT_PERSONS
                or "[" in value
                or any(ch.isdigit() for ch in value)
                or not any(ch.isupper() for ch in value)
                or len(value) < 3
            ):
                continue
            spans.append((start, end))

        for start, end in sorted(spans, reverse=True):
            text = text[:start] + PLACEHOLDERS[PiiCategory.PERSON] + text[end:]
            counts[PiiCategory.PERSON] += 1
        return text, counts


@lru_cache
def get_pii_masker() -> RegexSpacyPiiMasker:
    """Instancia compartida (cargar spaCy toma alrededor de un segundo)."""
    settings = get_settings()
    return RegexSpacyPiiMasker(settings.pii_audit_secret, spacy_model=settings.pii_spacy_model or None)
