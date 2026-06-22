"""services.metrics_service — facade stub for platform metrics."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def get_metrics() -> Dict[str, Any]:
    """Return a stub metrics snapshot."""
    return {
        "total_users": 0,
        "total_lands": 0,
        "total_transactions": 0,
        "uptime_seconds": 0,
    }


def get_metrics_service():
    """Return a metrics-service singleton (stub).

    Some callers expect a service object instead of a function call.
    """
    return _MetricsServiceStub()


class _MetricsServiceStub:
    """Stub metrics service object."""

    def get_metrics(self) -> Dict[str, Any]:
        return get_metrics()

    def increment(self, name: str, value: int = 1) -> None:
        logger.info("Metrics stub increment: %s += %d", name, value)

    def gauge(self, name: str, value: float) -> None:
        logger.info("Metrics stub gauge: %s = %.2f", name, value)

    def timing(self, name: str, seconds: float) -> None:
        logger.info("Metrics stub timing: %s = %.3fs", name, seconds)


__all__ = ["get_metrics", "get_metrics_service"]
