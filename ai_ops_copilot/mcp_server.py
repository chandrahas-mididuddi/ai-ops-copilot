"""MCP monitoring tool server.

Exposes the fictional monitoring data as MCP tools using the real MCP
Python SDK (``mcp`` >= 2, ``MCPServer``). Run it over stdio:

    python -m ai_ops_copilot.mcp_server

Tools:
- ``get_service_metrics`` — current metrics for one service.
- ``get_service_logs`` — recent logs for one service, filtered by level.
- ``get_active_alerts`` — active alerts, optionally for one service.

The tool functions are plain Python functions, so the in-process client
(``mcp_client.py``) can call them directly without a subprocess. The
stdio server path is the real MCP protocol — see README.md.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from .monitoring import MonitoringStore

mcp = MCPServer("ai-ops-monitoring")

_store = MonitoringStore()


@mcp.tool()
def get_service_metrics(service: str) -> dict:
    """Current metrics for a service (latency, error rate, CPU, queue depth)."""
    return _store.get_metrics(service)


@mcp.tool()
def get_service_logs(service: str, level: str = "ERROR", limit: int = 5) -> dict:
    """Recent logs for a service, filtered by level (ERROR, WARN, INFO)."""
    return {"logs": _store.get_logs(service, level=level, limit=limit)}


@mcp.tool()
def get_active_alerts(service: str | None = None) -> dict:
    """Active alerts, optionally filtered to one service."""
    return {"alerts": _store.get_alerts(service)}


if __name__ == "__main__":
    mcp.run()
