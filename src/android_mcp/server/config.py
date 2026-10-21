"""Which device the server drives, and the options read from the environment."""

from collections.abc import Mapping
from dataclasses import dataclass

from android_mcp.mobile import normalize_wifi_address

CONNECTIONS = ("auto", "usb", "wifi")

# Variables whose value means "yes" for the on/off options.
_TRUE = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class DevicePreference:
    """Which device to use, and where the choice came from.

    Attributes:
        connection: ``auto``, ``usb`` or ``wifi``; how to pick a device when no serial is set.
        serial: The device to use, or ``None`` to choose among those attached.
        source: The option or variable that set this, for messages.
    """

    connection: str = "auto"
    serial: str | None = None
    source: str = "auto-detect"


def _clean(value: str | None) -> str | None:
    """Treat unset and blank the same: MCP hosts pass blanks for options left empty."""
    if value is None:
        return None
    return value.strip() or None


def _connection(value: str | None, *, source: str) -> str:
    cleaned = _clean(value)
    if cleaned is None:
        return "auto"
    cleaned = cleaned.lower()
    if cleaned not in CONNECTIONS:
        raise ValueError(
            f"Invalid connection type {value!r} from {source}. "
            f"Use one of: {', '.join(CONNECTIONS)}."
        )
    return cleaned


def resolve_preference(
    *,
    device: str | None = None,
    connection: str | None = None,
    wifi: str | None = None,
    usb: str | None = None,
    env: Mapping[str, str],
) -> DevicePreference:
    """Work out which device to use from the command line and the environment.

    The command line beats the environment. Within the command line the order is ``wifi``,
    ``usb``, then ``device``. The environment variables are ``ANDROID_MCP_DEVICE``,
    ``ANDROID_MCP_CONNECTION`` and ``ANDROID_MCP_HOST``.

    Args:
        device: ``--device``: a serial or ``host:port``.
        connection: ``--connection``: ``auto``, ``usb`` or ``wifi``.
        wifi: ``--wifi``: a host, or ``""`` when the flag has no host (the environment's
            ``ANDROID_MCP_HOST`` is then used). ``None`` when the flag is absent.
        usb: ``--usb``: a serial, or ``""`` for any USB device. ``None`` when absent.
        env: The environment variables.

    Raises:
        ValueError: if a connection type is not one of ``auto``, ``usb``, ``wifi``.
    """
    env_device = _clean(env.get("ANDROID_MCP_DEVICE"))
    env_connection = _connection(env.get("ANDROID_MCP_CONNECTION"), source="ANDROID_MCP_CONNECTION")
    env_host = _clean(env.get("ANDROID_MCP_HOST"))

    if wifi is not None:
        serial = normalize_wifi_address(_clean(wifi) or env_host)
        return DevicePreference("wifi", serial, "--wifi")
    if usb is not None:
        return DevicePreference("usb", _clean(usb), "--usb")

    chosen = _connection(connection, source="--connection") if _clean(connection) else None
    if _clean(device):
        return DevicePreference(chosen or "auto", _clean(device), "--device")
    if env_device:
        return DevicePreference(chosen or env_connection, env_device, "ANDROID_MCP_DEVICE")
    if (chosen or env_connection) == "wifi" or (chosen is None and env_host):
        serial = normalize_wifi_address(env_host)
        return DevicePreference("wifi", serial, "ANDROID_MCP_CONNECTION/ANDROID_MCP_HOST")
    return DevicePreference(chosen or env_connection, None, "auto-detect")


def screenshot_quantized(env: Mapping[str, str]) -> bool:
    """Whether ``SCREENSHOT_QUANTIZED`` asks for smaller, 256-colour screenshots."""
    return (_clean(env.get("SCREENSHOT_QUANTIZED")) or "").lower() in _TRUE
