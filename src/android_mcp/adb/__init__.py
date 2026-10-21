"""Android Debug Bridge (adb) layer: talks to devices and knows nothing about MCP.

Usage:
    import android_mcp.adb as adb

    device = adb.list_devices()[0]
    adb.tap(540, 1200, serial=device.serial)
    png = adb.screencap(serial=device.serial)
"""

from .core import (
    OVERRIDE_VAR,
    Device,
    connect,
    connect_mdns_peers,
    dump_hierarchy,
    expand_notifications,
    find_adb,
    list_devices,
    run,
    run_bytes,
    screencap,
    shell,
)
from .enums import DeviceState, KeyCode
from .errors import AdbCommandError, AdbError, AdbNotFoundError, ScreenNotIdleError
from .input import (
    UntypeableTextError,
    check_typeable,
    clear_text,
    drag,
    long_press,
    press_key,
    swipe,
    tap,
    type_text,
)
from .keyboard import (
    INSTALL_HINT,
    KEYBOARD_IME,
    KEYBOARD_PACKAGE,
    KEYBOARD_URL,
    is_keyboard_installed,
    keyboard_session,
)

__all__ = [
    "INSTALL_HINT",
    "KEYBOARD_IME",
    "KEYBOARD_PACKAGE",
    "KEYBOARD_URL",
    "OVERRIDE_VAR",
    "AdbCommandError",
    "AdbError",
    "AdbNotFoundError",
    "Device",
    "DeviceState",
    "KeyCode",
    "ScreenNotIdleError",
    "UntypeableTextError",
    "check_typeable",
    "clear_text",
    "connect",
    "connect_mdns_peers",
    "drag",
    "dump_hierarchy",
    "expand_notifications",
    "find_adb",
    "is_keyboard_installed",
    "keyboard_session",
    "list_devices",
    "long_press",
    "press_key",
    "run",
    "run_bytes",
    "screencap",
    "shell",
    "swipe",
    "tap",
    "type_text",
]
