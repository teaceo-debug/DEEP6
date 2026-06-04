from __future__ import annotations

import logging

import structlog


def _merge_context_processor():
    contextvars = getattr(structlog, "contextvars", None)
    if contextvars is not None and hasattr(contextvars, "merge_contextvars"):
        return contextvars.merge_contextvars

    threadlocal = getattr(structlog, "threadlocal", None)
    if threadlocal is not None and hasattr(threadlocal, "merge_threadlocal"):
        return threadlocal.merge_threadlocal

    def _noop(_logger, _method_name, event_dict):
        return event_dict

    return _noop


def configure_logging(dev_mode: bool = False) -> None:
    """Configure structlog for the application.

    Args:
        dev_mode: If True, use human-readable console output.
                  If False, use JSON output for production.
    """
    shared_processors = [
        _merge_context_processor(),
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if dev_mode:
        processors = shared_processors + [structlog.dev.ConsoleRenderer()]
    else:
        processors = shared_processors + [structlog.processors.JSONRenderer()]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(module_name: str) -> structlog.BoundLogger:
    """Get a logger bound with module context."""
    return structlog.get_logger(module=module_name)
