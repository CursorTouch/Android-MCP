"""The MCP server: tools over :mod:`android_mcp.mobile`, and the choice of device."""

from .app import build_server
from .config import DevicePreference, resolve_preference

__all__ = ["DevicePreference", "build_server", "resolve_preference"]
