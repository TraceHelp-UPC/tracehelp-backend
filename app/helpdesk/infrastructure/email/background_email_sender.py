"""Envoltorio asíncrono en segundo plano para envíos SMTP sin bloquear la petición HTTP (US19 §2.4)."""
import logging
from concurrent.futures import Future, ThreadPoolExecutor

from app.helpdesk.application.ports import EmailMessage, IEmailSender

logger = logging.getLogger(__name__)


class BackgroundEmailSender(IEmailSender):
    """Despacha envíos en un hilo dedicado. Registra solo el nombre de clase de la excepción y no reintenta."""

    def __init__(self, inner: IEmailSender) -> None:
        self._inner = inner
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="email-sender")

    def send(self, message: EmailMessage) -> None:
        self.submit(message)

    def submit(self, message: EmailMessage) -> Future[None]:
        return self._executor.submit(self._send_safe, message)

    def _send_safe(self, message: EmailMessage) -> None:
        try:
            self._inner.send(message)
        except Exception as exc:  # noqa: BLE001 - los errores de correo no rompen el flujo ni exponen secretos
            logger.warning("Error al enviar correo de notificación: %s", type(exc).__name__)

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait)
