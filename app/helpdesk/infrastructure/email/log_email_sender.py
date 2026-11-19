"""Adaptador de correo por defecto (EMAIL_BACKEND=log): registra solo asunto y destinatario enmascarado."""
import logging

from app.helpdesk.application.ports import EmailMessage, IEmailSender

logger = logging.getLogger(__name__)


def mask_email(address: str) -> str:
    """Enmascara un correo electrónico como c***@empresa.com para logs sin PII."""
    addr = (address or "").strip()
    if "@" not in addr:
        return "***"
    local, domain = addr.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


class LogEmailSender(IEmailSender):
    """Registra el correo simulado sin exponer el cuerpo ni la dirección completa (D14, US19 §2.4)."""

    def send(self, message: EmailMessage) -> None:
        logger.info("Correo simulado: asunto=%s destinatario=%s", message.subject, mask_email(message.to))
