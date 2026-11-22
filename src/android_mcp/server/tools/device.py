"""ListDevices, ConnectDevice and Device: choosing which device to drive."""

from typing import Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..session import Session

NO_DEVICES = "No devices found. Ensure a device is connected and ADB is running."


def register(mcp: FastMCP, session: Session) -> None:
    def list_devices() -> str:
        with session.operation(connect=False) as mobile:
            devices = mobile.list_devices()
        if not devices:
            return NO_DEVICES
        return "\n".join(f"{device.serial}\t{device.state}" for device in devices)

    mcp.tool(
        list_devices,
        name="ListDevices",
        description="List available ADB devices",
        annotations=ToolAnnotations(
            title="List Devices",
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )

    def connect_device(serial: str) -> str:
        with session.operation(connect=False):
            device = session.connect_to(serial)
        return f"Connected to {device.serial}"

    mcp.tool(
        connect_device,
        name="ConnectDevice",
        description=(
            "Connect to an ADB device by serial number, or by host:port for a device on the network"
        ),
        annotations=ToolAnnotations(
            title="Connect Device",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )

    def device(
        action: Literal["list", "connect", "disconnect", "switch"],
        serial: str | None = None,
        to: Literal["wifi", "usb"] | None = None,
    ) -> str:
        if action == "list":
            return list_devices()
        with session.operation(connect=False) as mobile:
            if action == "connect":
                if serial:
                    found = session.connect_to(serial)
                else:
                    found = session.connect_configured()
                return f"Connected to {found.serial}"
            if action == "switch":
                if to is None:
                    raise ValueError("switch needs `to`: 'wifi' or 'usb'.")
                if serial:
                    session.connect_to(serial)
                elif not mobile.is_connected:
                    session.connect_configured()
                if to == "wifi":
                    return f"Now connected over Wi-Fi at {mobile.switch_to_wifi().serial}"
                return f"Now connected over USB as {mobile.switch_to_usb().serial}"
            mobile.disconnect()
            return "Disconnected from device."

    mcp.tool(
        device,
        name="Device",
        description=(
            "Manage ADB devices: list, connect, disconnect, or switch the connected device "
            "between USB and Wi-Fi. switch with to=wifi needs the phone on USB and on a Wi-Fi "
            "network; the cable can then be unplugged. switch with to=usb needs it plugged in."
        ),
        annotations=ToolAnnotations(
            title="Device",
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=False,
            open_world_hint=False,
        ),
    )
