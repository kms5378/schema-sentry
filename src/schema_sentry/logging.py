import logging
import sys

import structlog


def configure_logging(level: str = "INFO") -> None:
    """Configure standard-library and structlog output as one-line JSON."""

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric_level, stream=sys.stdout, force=True)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
