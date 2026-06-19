"""
Smart Land Management Copilot — Project Metrics Service
=========================================================
Tracks and reports system performance, API health, and
development KPIs for the PM dashboard.
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import deque

logger = logging.getLogger(__name__)


class ProjectMetricsService:
    """
    Collects and reports system metrics for the project management dashboard.
    Tracks API latency, search accuracy, prediction confidence, and more.
    """

    def __init__(self, max_history: int = 1000):
        self._api_latency_history: deque = deque(maxlen=max_history)
        self._search_count = 0
        self._prediction_count = 0
        self._chat_count = 0
        self._error_count = 0
        self._start_time = datetime.now()
        self._last_api_call: Optional[datetime] = None
        self._api_failures: deque = deque(maxlen=100)

    def record_api_call(
        self,
        endpoint: str,
        latency_ms: float,
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Record an API call metric."""
        self._api_latency_history.append({
            "timestamp": datetime.now().isoformat(),
            "endpoint": endpoint,
            "latency_ms": round(latency_ms, 2),
            "success": success,
        })
        if not success:
            self._error_count += 1
            self._api_failures.append({
                "timestamp": datetime.now().isoformat(),
                "endpoint": endpoint,
                "error": str(error),
            })
        self._last_api_call = datetime.now()

    def record_search(self) -> None:
        self._search_count += 1

    def record_prediction(self) -> None:
        self._prediction_count += 1

    def record_chat(self) -> None:
        self._chat_count += 1

    def get_dashboard(self) -> Dict:
        """Generate the full PM dashboard metrics."""
        uptime = (datetime.now() - self._start_time).total_seconds()
        avg_latency = self._average_latency()
        p95_latency = self._percentile_latency(95)
        error_rate = (self._error_count / max(self._search_count + self._chat_count, 1)) * 100

        return {
            "system": {
                "status": "Operational" if error_rate < 10 else "Degraded" if error_rate < 30 else "Down",
                "uptime_seconds": round(uptime),
                "uptime_formatted": str(timedelta(seconds=int(uptime))),
                "version": "4.0",
                "total_requests": self._search_count + self._prediction_count + self._chat_count,
            },
            "api_performance": {
                "avg_latency_ms": round(avg_latency, 2),
                "p95_latency_ms": round(p95_latency, 2),
                "total_calls": len(self._api_latency_history),
                "error_rate_pct": round(error_rate, 2),
                "last_call": self._last_api_call.isoformat() if self._last_api_call else "Never",
            },
            "usage_stats": {
                "total_searches": self._search_count,
                "total_predictions": self._prediction_count,
                "total_chats": self._chat_count,
                "searches_per_minute": self._per_minute(self._search_count, uptime),
                "chats_per_minute": self._per_minute(self._chat_count, uptime),
            },
            "recent_errors": list(self._api_failures)[-5:],
        }

    def _average_latency(self) -> float:
        if not self._api_latency_history:
            return 0.0
        return sum(h["latency_ms"] for h in self._api_latency_history) / len(self._api_latency_history)

    def _percentile_latency(self, percentile: int) -> float:
        if not self._api_latency_history:
            return 0.0
        latencies = sorted(h["latency_ms"] for h in self._api_latency_history)
        idx = max(0, int(len(latencies) * percentile / 100) - 1)
        return latencies[idx]

    @staticmethod
    def _per_minute(count: int, uptime_seconds: float) -> float:
        minutes = uptime_seconds / 60.0
        return round(count / minutes, 2) if minutes > 0 else 0.0


# Singleton instance
_metrics_service: Optional[ProjectMetricsService] = None


def get_metrics_service() -> ProjectMetricsService:
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = ProjectMetricsService()
    return _metrics_service