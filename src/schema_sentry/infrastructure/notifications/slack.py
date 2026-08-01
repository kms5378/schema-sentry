import httpx

from schema_sentry.application.notification_service import (
    AlertMessage,
    DeliveryFailure,
    ProviderReceipt,
)
from schema_sentry.domain.enums import AlertChannel


def build_slack_blocks(message: AlertMessage) -> dict[str, object]:
    return {
        "text": message.subject,
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": message.subject},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": message.text},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open Schema Sentry"},
                        "url": message.dashboard_url,
                    }
                ],
            },
        ],
    }


class SlackNotifier:
    channel = AlertChannel.SLACK

    def __init__(self, webhook_url: str, *, client: httpx.Client | None = None) -> None:
        self.webhook_url = webhook_url
        self.client = client or httpx.Client(timeout=5.0)

    def send(self, message: AlertMessage) -> ProviderReceipt:
        try:
            response = self.client.post(self.webhook_url, json=build_slack_blocks(message))
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DeliveryFailure("slack_delivery_failed") from exc
        return ProviderReceipt(provider_message_id=response.headers.get("x-slack-req-id"))
