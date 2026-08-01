import json

import httpx

from schema_sentry.application.notification_service import AlertMessage
from schema_sentry.infrastructure.notifications.slack import SlackNotifier


def test_slack_sends_block_kit_payload() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, headers={"x-slack-req-id": "req-123"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    notifier = SlackNotifier("https://hooks.slack.test/services/secret", client=client)
    message = AlertMessage(
        subject="Breaking schema drift",
        text="public.purchases.amount changed",
        html="<p>changed</p>",
        dashboard_url="https://schema.example.com/",
    )

    receipt = notifier.send(message)

    assert receipt.provider_message_id == "req-123"
    assert captured["blocks"][0]["type"] == "header"
    assert captured["blocks"][-1]["elements"][0]["url"] == message.dashboard_url
