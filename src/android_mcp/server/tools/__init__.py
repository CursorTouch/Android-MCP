"""The MCP tools, grouped by what they do. Each module has a ``register(mcp, session)``."""

from . import device, input, screen

REGISTRARS = (device.register, screen.register, input.register)

__all__ = ["REGISTRARS"]
