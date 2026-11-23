"""MCP client for the monitoring tools.

Two modes:

- ``direct`` (default): calls the MCP tool functions in-process. Used by
  the tests and the eval runner — fast and deterministic.
- ``stdio``: talks to ``ai_ops_copilot.mcp_server`` over the real MCP
  stdio protocol, spawning it as a subprocess. Used by the CLI demo to
  show the actual protocol working end to end.

Both modes expose the same async methods, so the agent does not care
which transport is in use.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class MonitoringClient:
    """Async client for the MCP monitoring tools."""

    def __init__(self, mode: str = "direct"):
        if mode not in ("direct", "stdio"):
            raise ValueError("mode must be 'direct' or 'stdio'")
        self.mode = mode
        self._session: ClientSession | None = None
        self._stdio_ctx = None

    async def __aenter__(self) -> "MonitoringClient":
        if self.mode == "stdio":
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "ai_ops_copilot.mcp_server"],
            )
            self._stdio_ctx = stdio_client(params)
            read, write = await self._stdio_ctx.__aenter__()
            self._session = ClientSession(read, write)
            await self._session.__aenter__()
            await self._session.initialize()
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session is not None:
            await self._session.__aexit__(*exc)
            self._session = None
        if self._stdio_ctx is not None:
            await self._stdio_ctx.__aexit__(*exc)
            self._stdio_ctx = None

    async def _call(self, name: str, arguments: dict):
        """Call one MCP tool by name, on whichever transport is active."""
        if self.mode == "stdio":
            assert self._session is not None, "client not entered"
            result = await self._session.call_tool(name, arguments)
            # Prefer the structured result when the SDK provides one.
            structured = getattr(result, "structured_content", None)
            if structured is not None:
                return structured
            # Otherwise the result is one JSON value per text block
            # (a list return becomes one block per element).
            import json

            values = [
                json.loads(block.text)
                for block in result.content
                if block.type == "text"
            ]
            if len(values) == 1:
                return values[0]
            return values
        # Direct mode: call the tool function in-process.
        from . import mcp_server

        fn = getattr(mcp_server, name)
        result = fn(**arguments)
        if asyncio.iscoroutine(result):
            result = await result
        return result

    async def get_metrics(self, service: str) -> dict:
        return await self._call("get_service_metrics", {"service": service})

    async def get_logs(
        self, service: str, level: str = "ERROR", limit: int = 5
    ) -> list:
        result = await self._call(
            "get_service_logs",
            {"service": service, "level": level, "limit": limit},
        )
        return result["logs"]

    async def get_alerts(self, service: str | None = None) -> list:
        result = await self._call("get_active_alerts", {"service": service})
        return result["alerts"]


@asynccontextmanager
async def monitoring_client(mode: str = "direct"):
    """Convenience async context manager for a MonitoringClient."""
    client = MonitoringClient(mode=mode)
    try:
        yield await client.__aenter__()
    finally:
        await client.__aexit__()
