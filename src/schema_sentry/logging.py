import logging
import re
import sys
from contextlib import suppress
from typing import Any

import structlog
from structlog.typing import EventDict, WrappedLogger

REDACTED = "[REDACTED]"
_SENSITIVE_FIELD = re.compile(
    r"(?:password|passwd|pwd|secret|token|api[_-]?key|authorization|webhook)",
    re.IGNORECASE,
)
_URL_CREDENTIAL = re.compile(
    r"(?P<prefix>[a-z][a-z0-9+.-]*://[^:/@\s]+:)(?P<secret>[^@\s]+)(?P<suffix>@)",
    re.IGNORECASE,
)
_INLINE_SECRET = re.compile(
    r"(?P<prefix>(?:password|passwd|pwd|secret|token|api[_-]?key)\s*[=:]\s*)"
    r"(?P<secret>[^\s,;&]+)",
    re.IGNORECASE,
)
_AUTHORIZATION = re.compile(
    r"(?P<prefix>\b(?:Basic|Bearer)\s+)[A-Za-z0-9._~+/=-]+",
    re.IGNORECASE,
)


class _CurrentStdout:
    """Forward writes without retaining a replaced or closed stdout object."""

    def write(self, message: str) -> int:
        return sys.stdout.write(message)

    def flush(self) -> None:
        sys.stdout.flush()


_CURRENT_STDOUT = _CurrentStdout()


def _redact_string(value: str) -> str:
    value = _URL_CREDENTIAL.sub(rf"\g<prefix>{REDACTED}\g<suffix>", value)
    value = _INLINE_SECRET.sub(rf"\g<prefix>{REDACTED}", value)
    return _AUTHORIZATION.sub(rf"\g<prefix>{REDACTED}", value)


def _redact_value(value: Any, *, field_name: str | None = None) -> Any:
    if field_name and _SENSITIVE_FIELD.search(field_name):
        return REDACTED
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, dict):
        return {key: _redact_value(item, field_name=str(key)) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def redact_sensitive_values(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Remove credentials from structured fields and exception text."""

    return {
        key: _redact_value(value, field_name=key)
        for key, value in event_dict.items()
    }


def log_source_failure(
    error: Exception,
    *,
    source_key: str,
    scan_id: str,
    duration_ms: int = 0,
) -> None:
    with suppress(OSError, ValueError):
        structlog.get_logger(__name__).error(
            "source_connection_failed",
            source_key=source_key,
            scan_id=scan_id,
            duration_ms=duration_ms,
            status="FAILED",
            error=f"{type(error).__name__}: {error}",
        )


def configure_logging(level: str = "INFO") -> None:
    """Configure standard-library and structlog output as one-line JSON."""

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, stream=_CURRENT_STDOUT, force=True)
    structlog.configure(
        processors=[
            redact_sensitive_values,
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
