"""Value Object TriageClassification y heurística de respaldo para la clasificación del triaje (US27, T41)."""
from dataclasses import dataclass

from app.helpdesk.domain.enums import ImpactLevel, TicketPriority
from app.helpdesk.domain.exceptions import InvalidTicketDataError

DEFAULT_CATEGORY = "General"

VALID_CATEGORIES: frozenset[str] = frozenset(
    {
        "Conectividad y Red",
        "Accesos y Credenciales",
        "Software Corporativo y ERP",
        "Hardware y Periféricos",
        "Correo y Colaboración",
        "Seguridad y Permisos",
        DEFAULT_CATEGORY,
    }
)

_PRIORITY_BY_IMPACT: dict[ImpactLevel, TicketPriority] = {
    ImpactLevel.LOW: TicketPriority.LOW,
    ImpactLevel.MEDIUM: TicketPriority.MEDIUM,
    ImpactLevel.HIGH: TicketPriority.HIGH,
}

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Conectividad y Red", ("vpn", "red", "wifi", "internet", "dns", "gateway", "tls", "ip", "conexion", "conexión")),
    (
        "Accesos y Credenciales",
        ("contraseña", "password", "credencial", "login", "acceso", "bloquead", "autenticacion", "autenticación", "mfa"),
    ),
    ("Software Corporativo y ERP", ("erp", "sap", "crm", "sistema", "factura", "modulo", "módulo", "licencia")),
    ("Hardware y Periféricos", ("impresora", "monitor", "teclado", "laptop", "disco", "bateria", "batería", "usb")),
    ("Correo y Colaboración", ("outlook", "correo", "email", "teams", "calendario", "buzon", "buzón")),
    ("Seguridad y Permisos", ("permiso", "rol", "antivirus", "firewall", "phishing", "certificado")),
)

_CRITICAL_KEYWORDS: tuple[str, ...] = (
    "caido",
    "caído",
    "produccion",
    "producción",
    "masivo",
    "toda la empresa",
    "bloqueo total",
    "critico",
    "crítico",
)


@dataclass(frozen=True)
class TriageClassification:
    """Clasificación estructurada de categoría y prioridad generada en el triaje (US27, T41)."""

    category: str
    priority: TicketPriority
    is_fallback: bool = False

    def __post_init__(self) -> None:
        cleaned = (self.category or "").strip()
        if not cleaned:
            raise InvalidTicketDataError("La categoría de clasificación no puede estar vacía.")
        if cleaned not in VALID_CATEGORIES:
            raise InvalidTicketDataError(
                f"La categoría '{cleaned}' no pertenece al catálogo permitido: {', '.join(sorted(VALID_CATEGORIES))}."
            )
        if not isinstance(self.priority, TicketPriority):
            try:
                object.__setattr__(self, "priority", TicketPriority(str(self.priority).upper()))
            except ValueError as exc:
                raise InvalidTicketDataError(f"Prioridad inválida: {self.priority}.") from exc
        object.__setattr__(self, "category", cleaned)

    @classmethod
    def fallback_for_impact(cls, impact_level: ImpactLevel) -> "TriageClassification":
        """Respaldo seguro cuando el LLM o la descripción no permiten identificar una categoría (US27 Escenario 3)."""
        return cls(
            category=DEFAULT_CATEGORY,
            priority=_PRIORITY_BY_IMPACT[impact_level],
            is_fallback=True,
        )

    @classmethod
    def from_structured_output(
        cls,
        raw_category: str | None,
        raw_priority: str | TicketPriority | None,
        *,
        impact_level: ImpactLevel,
    ) -> "TriageClassification":
        """Construye la clasificación desde la salida estructurada del modelo o aplica el respaldo por impacto."""
        cleaned_cat = (raw_category or "").strip()
        if cleaned_cat not in VALID_CATEGORIES or cleaned_cat == DEFAULT_CATEGORY:
            return cls.fallback_for_impact(impact_level)

        priority: TicketPriority
        if isinstance(raw_priority, TicketPriority):
            priority = raw_priority
        elif raw_priority:
            try:
                priority = TicketPriority(str(raw_priority).strip().upper())
            except ValueError:
                priority = _PRIORITY_BY_IMPACT[impact_level]
        else:
            priority = _PRIORITY_BY_IMPACT[impact_level]

        return cls(category=cleaned_cat, priority=priority, is_fallback=False)

    @classmethod
    def infer_from_incident(
        cls,
        *,
        title: str,
        description: str,
        impact_level: ImpactLevel,
        affected_module: str | None = None,
    ) -> "TriageClassification":
        """Clasifica el incidente por catálogo y prioridad o usa General + impacto declarado si no es identificable."""
        corpus = f"{title or ''} {description or ''} {affected_module or ''}".lower()

        matched_category: str | None = None
        for category_name, keywords in _CATEGORY_KEYWORDS:
            if any(kw in corpus for kw in keywords):
                matched_category = category_name
                break

        if matched_category is None:
            return cls.fallback_for_impact(impact_level)

        priority = _PRIORITY_BY_IMPACT[impact_level]
        if impact_level is ImpactLevel.HIGH and any(kw in corpus for kw in _CRITICAL_KEYWORDS):
            priority = TicketPriority.CRITICAL

        return cls(category=matched_category, priority=priority, is_fallback=False)
