import asyncio

import pytest

from ai_ops_copilot.mcp_client import MonitoringClient
from ai_ops_copilot.monitoring import infer_service


def test_metrics_for_known_service(store):
    metrics = store.get_metrics("checkout-api")
    assert metrics["latency_p95_ms"] == 1420
    assert metrics["cpu_pct"] == 91


def test_metrics_unknown_service_raises(store):
    with pytest.raises(KeyError):
        store.get_metrics("no-such-service")


def test_logs_filtered_by_level(store):
    errors = store.get_logs("payments-gateway", level="ERROR")
    assert len(errors) == 1
    assert "5xx" in errors[0]["msg"]
    infos = store.get_logs("payments-gateway", level="INFO")
    assert len(infos) == 2


def test_alerts_all_and_filtered(store):
    assert len(store.get_alerts()) == 6
    checkout = store.get_alerts("checkout-api")
    assert len(checkout) == 1
    assert checkout[0]["service"] == "checkout-api"


def test_infer_service_keywords():
    assert infer_service("checkout is slow") == "checkout-api"
    assert infer_service("TLS certificate expires soon") == "pricing-engine"
    assert infer_service("the office coffee machine is broken") is None


def test_direct_client_returns_metrics():
    async def _run():
        async with MonitoringClient(mode="direct") as client:
            return await client.get_metrics("inventory-sync")

    metrics = asyncio.run(_run())
    assert metrics["consumer_lag"] == 45200


def test_direct_client_returns_logs_and_alerts():
    async def _run():
        async with MonitoringClient(mode="direct") as client:
            logs = await client.get_logs("pricing-engine", level="WARN")
            alerts = await client.get_alerts("pricing-engine")
            return logs, alerts

    logs, alerts = asyncio.run(_run())
    assert len(logs) == 1
    assert "certificate" in logs[0]["msg"]
    assert len(alerts) == 2


def test_direct_client_unknown_service_raises():
    async def _run():
        async with MonitoringClient(mode="direct") as client:
            await client.get_metrics("no-such-service")

    with pytest.raises(KeyError):
        asyncio.run(_run())


def test_stdio_client_round_trip():
    """The real MCP stdio protocol: spawn the server, call a tool."""
    async def _run():
        async with MonitoringClient(mode="stdio") as client:
            metrics = await client.get_metrics("checkout-api")
            alerts = await client.get_alerts("checkout-api")
            return metrics, alerts

    metrics, alerts = asyncio.run(_run())
    assert metrics["latency_p95_ms"] == 1420
    assert len(alerts) == 1
    assert alerts[0]["id"] == "alert-checkout-latency"
