import smtplib
from email.message import EmailMessage
from email.utils import make_msgid

from schema_sentry.application.notification_service import (
    AlertMessage,
    DeliveryFailure,
    ProviderReceipt,
)
from schema_sentry.domain.enums import AlertChannel


def build_multipart_email(
    message: AlertMessage,
    sender: str,
    recipients: tuple[str, ...],
) -> EmailMessage:
    mime = EmailMessage()
    mime["Subject"] = message.subject
    mime["From"] = sender
    mime["To"] = ", ".join(recipients)
    mime["Message-ID"] = make_msgid()
    mime.set_content(message.text)
    mime.add_alternative(message.html, subtype="html")
    return mime


class EmailNotifier:
    channel = AlertChannel.EMAIL

    def __init__(
        self,
        *,
        host: str,
        port: int,
        sender: str,
        recipients: tuple[str, ...],
    ) -> None:
        self.host = host
        self.port = port
        self.sender = sender
        self.recipients = recipients

    def send(self, message: AlertMessage) -> ProviderReceipt:
        mime = build_multipart_email(message, self.sender, self.recipients)
        try:
            with smtplib.SMTP(self.host, self.port, timeout=5) as smtp:
                refused = smtp.send_message(mime)
        except (OSError, smtplib.SMTPException) as exc:
            raise DeliveryFailure("email_delivery_failed") from exc
        if refused:
            raise DeliveryFailure("smtp_recipients_refused")
        return ProviderReceipt(provider_message_id=mime["Message-ID"])
