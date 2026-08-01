import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from airflow.sdk.exceptions import AirflowException

HTTP_TIMEOUT_SECONDS = 5


@dataclass(frozen=True, slots=True)
class JsonResponse:
    status: int
    body: dict[str, Any]


def post_json(path: str, payload: dict[str, str]) -> JsonResponse:
    base_url = os.environ.get("SCHEMA_SENTRY_API_URL", "http://api:8000").rstrip("/")
    api_key = os.environ["SCHEMA_SENTRY_API_KEY"]
    request = Request(
        f"{base_url}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
        method="POST",
    )

    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:  # noqa: S310
            return JsonResponse(response.status, _decode_body(response.read()))
    except HTTPError as exc:
        return JsonResponse(exc.code, _decode_body(exc.read()))
    except OSError as exc:
        raise AirflowException("Schema Sentry API is unavailable") from exc


def _decode_body(raw_body: bytes) -> dict[str, Any]:
    if not raw_body:
        return {}
    decoded = json.loads(raw_body)
    if not isinstance(decoded, dict):
        raise AirflowException("Schema Sentry returned an invalid JSON object")
    return decoded
