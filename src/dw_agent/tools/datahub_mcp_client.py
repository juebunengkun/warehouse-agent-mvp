from __future__ import annotations

import asyncio
import json
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

MockResponse = dict[str, Any] | Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class DataHubMcpClient:
    enabled: bool = False
    gms_url: str = "http://localhost:8080"
    token: str | None = None
    command: str = "uvx"
    package: str = "mcp-server-datahub@latest"
    timeout: int = 10
    mock_responses: dict[str, MockResponse] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> DataHubMcpClient:
        enabled = os.getenv("DATAHUB_MCP_ENABLED", "false").lower() == "true"
        timeout_value = os.getenv("DATAHUB_TIMEOUT", "10")
        return cls(
            enabled=enabled,
            gms_url=os.getenv("DATAHUB_GMS_URL", "http://localhost:8080"),
            token=os.getenv("DATAHUB_GMS_TOKEN") or None,
            command=os.getenv("DATAHUB_MCP_COMMAND", "uvx"),
            package=os.getenv("DATAHUB_MCP_PACKAGE", "mcp-server-datahub@latest"),
            timeout=int(timeout_value) if timeout_value.isdigit() else 10,
        )

    def is_enabled(self) -> bool:
        return self.enabled

    def list_tools(self) -> list[dict[str, Any]]:
        if self.mock_responses:
            return [{"name": name, "source": "mock"} for name in sorted(self.mock_responses)]
        if not self.enabled:
            return []
        if not self.token:
            return []
        return _run_async(self._list_tools_async(), timeout=self.timeout)

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        if tool_name in self.mock_responses:
            return self._mock_call(tool_name, arguments)
        if not self.enabled:
            return _error(tool_name, "DataHub MCP is disabled.", token=self.token)
        if not self.token:
            return _error(tool_name, "DATAHUB_GMS_TOKEN is required when DataHub MCP is enabled.", token=self.token)
        try:
            return _run_async(self._call_tool_async(tool_name, arguments), timeout=self.timeout)
        except Exception as exc:
            return _error(tool_name, f"{type(exc).__name__}: {exc}", token=self.token)

    def _mock_call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        response = self.mock_responses[tool_name]
        if callable(response):
            return response(arguments)
        return dict(response)

    async def _list_tools_async(self) -> list[dict[str, Any]]:
        params = self._server_params()
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": getattr(tool, "description", None),
                    }
                    for tool in tools.tools
                ]

    async def _call_tool_async(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        params = self._server_params()
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                decoded = _decode_tool_result(result)
                if isinstance(decoded, dict):
                    return decoded
                return {"passed": True, "tool": tool_name, "result": decoded, "warnings": [], "errors": []}

    def _server_params(self) -> StdioServerParameters:
        env = os.environ.copy()
        env["DATAHUB_GMS_URL"] = self.gms_url
        if self.token:
            env["DATAHUB_GMS_TOKEN"] = self.token
        return StdioServerParameters(
            command=self.command,
            args=[self.package],
            env=env,
        )


def _error(tool_name: str, message: str, *, token: str | None = None) -> dict[str, Any]:
    return {
        "passed": False,
        "tool": tool_name,
        "errors": [_redact(message, token)],
        "warnings": [],
    }


def _decode_tool_result(result) -> Any:
    if not result.content:
        return None
    decoded_items = []
    for item in result.content:
        text = getattr(item, "text", None)
        if text is None:
            decoded_items.append(item)
            continue
        try:
            decoded_items.append(json.loads(text))
        except json.JSONDecodeError:
            decoded_items.append(text)
    if len(decoded_items) == 1:
        return decoded_items[0]
    return decoded_items


def _run_async(coro, *, timeout: int):
    async def with_timeout():
        return await asyncio.wait_for(coro, timeout=timeout)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(with_timeout())

    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(with_timeout())
        except BaseException as exc:  # pragma: no cover - re-raised in caller thread.
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout + 1)

    if "error" in result:
        raise result["error"]
    if "value" not in result:
        raise TimeoutError(f"DataHub MCP call timed out after {timeout} seconds.")
    return result.get("value")


def _redact(message: str, token: str | None = None) -> str:
    tokens = [item for item in [token, os.getenv("DATAHUB_GMS_TOKEN")] if item]
    for item in tokens:
        message = message.replace(str(item), "<redacted>")
    return message
