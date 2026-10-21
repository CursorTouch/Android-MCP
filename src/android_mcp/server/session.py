"""The server's one session: the device in use, the choice of device, and a lock around both."""

import threading
from collections.abc import Iterator
from contextlib import contextmanager

from fastmcp.exceptions import ToolError

import android_mcp.adb as adb
from android_mcp.mobile import Mobile, MobileError

from .config import DevicePreference


class Session:
    """Shares one :class:`Mobile` between tool calls.

    FastMCP runs tools on worker threads, so two calls can overlap. Every tool body runs through
    :meth:`operation`, which lets one at a time through: two taps or a tap and a dump interleaved
    on one device would each see the other's half-finished work.
    """

    def __init__(self, mobile: Mobile, preference: DevicePreference | None = None) -> None:
        self.mobile = mobile
        self.preference = preference or DevicePreference()
        self._lock = threading.RLock()

    def connect_to(self, serial: str) -> adb.Device:
        """Select ``serial``, connecting adb to it first when it is a network address."""
        if ":" in serial:
            return self.mobile.connect_wifi(serial)
        return self.mobile.connect(serial)

    def connect_configured(self) -> adb.Device:
        """Select the device the preference names, or pick one from those attached.

        Raises:
            MobileError: if none can be used; the message says how to choose one.
        """
        preference = self.preference
        if preference.serial:
            if preference.connection == "wifi":
                return self.mobile.connect_wifi(preference.serial)
            return self.connect_to(preference.serial)
        try:
            return self.mobile.connect(connection=preference.connection)
        except MobileError as error:
            raise MobileError(
                f"{error} Choose one with --device, --wifi, --usb or ANDROID_MCP_DEVICE."
            ) from None

    @contextmanager
    def operation(self, *, connect: bool = True) -> Iterator[Mobile]:
        """Run one tool call: alone, with a device connected, and with errors made readable.

        The device is connected on first use rather than at startup, so the server starts
        whether or not a device is attached yet.

        Args:
            connect: Connect to the preferred device first if none is connected. Pass ``False``
                for calls that work without one, such as listing devices.

        Raises:
            ToolError: for a failure the agent can act on (no device, a bad argument, adb
                refusing), carrying its message. Anything else is a bug and passes through.
        """
        with self._lock:
            try:
                if connect and not self.mobile.is_connected:
                    self.connect_configured()
                yield self.mobile
            except (MobileError, adb.AdbError, ValueError) as error:
                raise ToolError(str(error)) from error
