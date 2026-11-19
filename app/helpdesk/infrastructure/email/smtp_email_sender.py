"""Adaptador SMTP usando únicamente la biblioteca estándar smtplib (D14, US19 §2.4)."""
import smtplib
from email.message import EmailMessage as MimeEmailMessage

from app.helpdesk.application.ports import EmailMessage, IEmailSender


class SmtpEmailSender(IEmailSender):
    def __init__(
        self,
        *,
        host: str,
        port: int = 587,
        from_address: str = "TraceHelp <no-reply@example.com>",
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        timeout: float = 10.0,
    ) -> None:
        self._host = host
        self._port = port
        self._from_address = from_address
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._timeout = timeout

    def send(self, message: EmailMessage) -> None:
        mime = MimeEmailMessage()
        mime["From"] = self._from_address
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text_body, subtype="plain", charset="utf-8")

        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as server:
            if self._use_tls:
                server.starttls()
            if self._username:
                server.login(self._username, self._password)
            server.send_message(mime)
