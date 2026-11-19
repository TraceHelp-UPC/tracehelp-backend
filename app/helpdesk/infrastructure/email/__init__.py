"""Fábrica de adaptadores de correo para notificaciones (US19, T91, D14)."""
import logging

from app.core.config import Settings, get_settings
from app.helpdesk.application.ports import IEmailSender
from app.helpdesk.infrastructure.email.background_email_sender import BackgroundEmailSender
from app.helpdesk.infrastructure.email.log_email_sender import LogEmailSender, mask_email
from app.helpdesk.infrastructure.email.smtp_email_sender import SmtpEmailSender

logger = logging.getLogger(__name__)

_override_sender: IEmailSender | None = None
_cached_sender: IEmailSender | None = None


def build_email_sender(settings: Settings | None = None) -> IEmailSender:
    """Construye el adaptador de correo según EMAIL_BACKEND y SMTP_HOST (D14)."""
    cfg = settings or get_settings()
    backend = (cfg.email_backend or "log").strip().lower()
    if backend == "smtp":
        host = (cfg.smtp_host or "").strip()
        if host:
            return BackgroundEmailSender(
                SmtpEmailSender(
                    host=host,
                    port=cfg.smtp_port,
                    from_address=cfg.email_from,
                    username=cfg.smtp_username,
                    password=cfg.smtp_password,
                    use_tls=cfg.smtp_use_tls,
                )
            )
        logger.warning("EMAIL_BACKEND=smtp pero SMTP_HOST está vacío; se usará LogEmailSender.")
    return LogEmailSender()


def get_email_sender() -> IEmailSender:
    """Devuelve el adaptador de correo activo (permite inyección dinámica en pruebas con set_email_sender)."""
    global _cached_sender
    if _override_sender is not None:
        return _override_sender
    if _cached_sender is None:
        _cached_sender = build_email_sender()
    return _cached_sender


def set_email_sender(sender: IEmailSender) -> None:
    """Inyecta un adaptador de correo (por ejemplo FakeEmailSender en pruebas)."""
    global _override_sender
    _override_sender = sender


def reset_email_sender() -> None:
    """Limpia la inyección de pruebas y el adaptador cacheado."""
    global _override_sender, _cached_sender
    _override_sender = None
    if isinstance(_cached_sender, BackgroundEmailSender):
        _cached_sender.shutdown(wait=False)
    _cached_sender = None


__all__ = [
    "BackgroundEmailSender",
    "LogEmailSender",
    "SmtpEmailSender",
    "build_email_sender",
    "get_email_sender",
    "mask_email",
    "reset_email_sender",
    "set_email_sender",
]
