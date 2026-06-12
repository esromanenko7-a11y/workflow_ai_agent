import logging as std_logging
import sys

import structlog


def setup_logging(level: str = "INFO") -> None:
    """
    Настраивает структурные JSON-логи для приложения.

    level приходит из настроек, например: INFO, DEBUG, WARNING.
    """
    log_level = getattr(std_logging, level.upper(), std_logging.INFO)

    std_logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        cache_logger_on_first_use=True,
    )