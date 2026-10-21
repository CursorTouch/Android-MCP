"""Builds the MCP server: the FastMCP app, its instructions and the tools."""

from fastmcp import FastMCP

from android_mcp.mobile import Mobile

from .config import DevicePreference
from .session import Session
from .tools import REGISTRARS

INSTRUCTIONS = """\
Android device automation. Call Snapshot first: it lists the interactive elements on the \
screen, each with a label and the coordinates to tap, and with use_vision=true also returns a \
screenshot with the labels drawn on it. Act with Click, ClickBySelector, LongClick, Swipe, \
Drag, Type and Press, then Snapshot again to see the result. Use WaitForElement when content \
is still loading, and Wait to pause. The device is connected on first use; ListDevices, \
ConnectDevice and Device choose a different one."""


def build_server(
    preference: DevicePreference | None = None, mobile: Mobile | None = None
) -> FastMCP:
    """Create the server with every tool registered.

    Args:
        preference: Which device to use. Defaults to picking one of those attached.
        mobile: The service to drive. Defaults to a new one; tests pass their own.
    """
    session = Session(mobile or Mobile(), preference)
    server = FastMCP(name="android-mcp-beta", instructions=INSTRUCTIONS)
    for register in REGISTRARS:
        register(server, session)
    return server
