"""Fictional monitoring data store.

Static, deterministic metrics, logs and alerts for the fictional
Meridian Retail services, loaded from ``data/monitoring.yaml``. This is
the data source behind the MCP monitoring tools — it never touches a
real monitoring system.
"""

from __future__ import annotations

import copy
import os

import yaml

DEFAULT_MONITORING_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "monitoring.yaml",
)

KNOWN_SERVICES = [
    "checkout-api",
    "payments-gateway",
    "inventory-sync",
    "notification-service",
    "pricing-engine",
]


def infer_service(text: str) -> str | None:
    """Best-guess service for a request, from service names and keywords."""
    lowered = text.lower()
    for service in KNOWN_SERVICES:
        if service in lowered:
            return service
    keywords = {
        "checkout": "checkout-api",
        "payment": "payments-gateway",
        "inventory": "inventory-sync",
        "stock": "inventory-sync",
        "notification": "notification-service",
        "pricing": "pricing-engine",
        "price": "pricing-engine",
        "certificate": "pricing-engine",
        "cert": "pricing-engine",
        "tls": "pricing-engine",
    }
    for word, service in keywords.items():
        if word in lowered:
            return service
    return None


class MonitoringStore:
    """Read-only access to the fictional monitoring data."""

    def __init__(self, path: str = DEFAULT_MONITORING_PATH):
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        self._services: dict = raw["services"]

    def service_names(self) -> list[str]:
        return list(self._services)

    def get_metrics(self, service: str) -> dict:
        if service not in self._services:
            raise KeyError(f"unknown service: {service}")
        return copy.deepcopy(self._services[service]["metrics"])

    def get_logs(
        self, service: str, level: str = "ERROR", limit: int = 5
    ) -> list[dict]:
        if service not in self._services:
            raise KeyError(f"unknown service: {service}")
        logs = self._services[service]["logs"]
        if level:
            logs = [log for log in logs if log["level"] == level.upper()]
        return copy.deepcopy(logs[:limit])

    def get_alerts(self, service: str | None = None) -> list[dict]:
        alerts: list[dict] = []
        for name, data in self._services.items():
            if service is not None and name != service:
                continue
            for alert in data["alerts"]:
                alerts.append({"service": name, **copy.deepcopy(alert)})
        return alerts
