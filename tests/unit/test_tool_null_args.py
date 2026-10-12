"""Optional tool arguments must accept an explicit null. Run with: uv run --with pytest pytest tests"""
import asyncio

import pytest
from fastmcp import Client

import android_mcp.__main__ as server


class _DeviceReached(Exception):
    """Raised instead of touching a device, to show the call got past argument validation."""


def _list_tools():
    async def run():
        async with Client(server.mcp) as client:
            return await client.list_tools()

    return asyncio.run(run())


def _call(name: str, arguments: dict):
    async def run():
        async with Client(server.mcp) as client:
            return await client.call_tool(name, arguments, raise_on_error=False)

    return asyncio.run(run())


def _allows_null(schema: dict) -> bool:
    if schema.get("type") == "null" or "null" in (schema.get("type") or []):
        return True
    return any(_allows_null(option) for option in schema.get("anyOf", []))


def test_every_parameter_defaulting_to_none_allows_null() -> None:
    bad = [
        f"{tool.name}.{name}"
        for tool in _list_tools()
        for name, prop in tool.inputSchema.get("properties", {}).items()
        if "default" in prop and prop["default"] is None and not _allows_null(prop)
    ]
    assert bad == []


@pytest.mark.parametrize("tool", ["ClickBySelector", "WaitForElement"])
def test_selector_tools_accept_explicit_null(tool: str, monkeypatch: pytest.MonkeyPatch) -> None:
    reached = []

    def fake_require_device():
        reached.append(tool)
        raise _DeviceReached()

    monkeypatch.setattr(server, "require_device", fake_require_device)
    result = _call(
        tool, {"text": "OK", "resourceId": None, "className": None, "description": None}
    )
    message = result.content[0].text if result.content else ""
    assert "validation error" not in message
    assert reached == [tool]
