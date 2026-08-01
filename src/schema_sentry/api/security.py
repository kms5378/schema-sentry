import secrets
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from schema_sentry.config import Settings, get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


@dataclass(frozen=True, slots=True)
class OperatorIdentity:
    subject: str
    mechanism: Literal["api-key", "proxy", "bypass"]


def require_operator(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Security(api_key_header)] = None,
    x_authenticated_user: Annotated[str | None, Header()] = None,
) -> OperatorIdentity:
    if settings.environment == "development" and settings.auth_disabled:
        return OperatorIdentity(subject="local-development", mechanism="bypass")
    if x_api_key and secrets.compare_digest(x_api_key, settings.api_key.get_secret_value()):
        return OperatorIdentity(subject="api-client", mechanism="api-key")
    if settings.trust_proxy_auth and x_authenticated_user:
        return OperatorIdentity(subject=x_authenticated_user, mechanism="proxy")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="operator authentication required",
    )
