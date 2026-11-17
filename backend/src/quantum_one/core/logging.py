"""Logging estruturado (JSON) com mascaramento obrigatório de segredos."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable, MutableMapping
from typing import Any

import structlog

from quantum_one.core.redaction import Redactor


def _redaction_processor(redactor: Redactor) -> structlog.types.Processor:
    def processor(
        _: Any, __: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        redacted: dict[str, Any] = redactor.redact(dict(event_dict))
        return redacted

    return processor


def configure_logging(service: str, level: str, secret_values: Iterable[str] = ()) -> None:
    redactor = Redactor(secret_values)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level, force=True)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            # o mascaramento roda POR ÚLTIMO, depois de a exceção virar texto
            _redaction_processor(redactor),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
