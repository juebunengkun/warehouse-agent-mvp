from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from dw_agent.config import PROJECT_ROOT

ToolCall = tuple[str, dict[str, Any]]


def call_mcp_tool(tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    return call_mcp_tools([(tool_name, arguments or {})])[0]


def call_mcp_tools(calls: list[ToolCall]) -> list[Any]:
    return _run_async(_call_mcp_tools_async(calls))


async def _call_mcp_tools_async(calls: list[ToolCall]) -> list[Any]:
    env = os.environ.copy()
    src_path = str(PROJECT_ROOT / "src")
    root_path = str(PROJECT_ROOT)
    env["PYTHONPATH"] = os.pathsep.join([src_path, root_path, env.get("PYTHONPATH", "")])

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=PROJECT_ROOT,
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            outputs = []
            for tool_name, arguments in calls:
                result = await session.call_tool(tool_name, arguments)
                outputs.append(_decode_tool_result(result))
            return outputs


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


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - re-raised in caller thread.
            result["error"] = exc

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if "error" in result:
        raise result["error"]
    return result["value"]
