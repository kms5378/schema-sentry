from email.message import EmailMessage

from schema_sentry.application.notification_service import AlertMessage
from schema_sentry.infrastructure.notifications.email import EmailNotifier, build_multipart_email


def message() -> AlertMessage:
    return AlertMessage(
        subject="Breaking schema drift",
        text="public.purchases.amount changed",
        html="<p>public.purchases.amount changed</p>",
        dashboard_url="https://schema.example.com/",
    )


def test_email_contains_text_and_html_alternatives() -> None:
    mime = build_multipart_email(message(), "schema@example.com", ("owner@example.com",))

    assert mime.get_content_type() == "multipart/alternative"
    assert {part.get_content_type() for part in mime.iter_parts()} == {
        "text/plain",
        "text/html",
    }


def test_email_notifier_sends_message(monkeypatch) -> None:
    sent: list[EmailMessage] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            assert (host, port, timeout) == ("mailpit", 1025, 5)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def send_message(self, mime: EmailMessage):
            sent.append(mime)
            return {}

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    notifier = EmailNotifier(
        host="mailpit",
        port=1025,
        sender="schema@example.com",
        recipients=("owner@example.com",),
    )

    receipt = notifier.send(message())

    assert len(sent) == 1
    assert receipt.provider_message_id == sent[0]["Message-ID"]
