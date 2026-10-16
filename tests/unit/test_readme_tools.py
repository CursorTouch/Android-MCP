"""Keep the documented tool names aligned with the public MCP interface."""
import asyncio
from pathlib import Path
import re

from fastmcp import Client

from android_mcp.__main__ import mcp


def test_readme_lists_available_tools() -> None:
    async def list_names() -> set[str]:
        async with Client(mcp) as client:
            return {tool.name for tool in await client.list_tools()}

    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text(encoding="utf-8")
    section = readme.split("## 🛠️ Available Tools\n", 1)[1].split("\n## ", 1)[0]
    documented = re.findall(r"^- `([^`]+)`:", section, flags=re.MULTILINE)
    assert len(documented) == len(set(documented)), "Each tool should be listed once"
    assert set(documented) == asyncio.run(list_names())
