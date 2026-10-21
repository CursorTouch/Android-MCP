"""Constants: device connection states and Android key codes."""

from enum import IntEnum, StrEnum


class DeviceState(StrEnum):
    """The state column of ``adb devices``."""

    DEVICE = "device"
    OFFLINE = "offline"
    UNAUTHORIZED = "unauthorized"
    AUTHORIZING = "authorizing"
    CONNECTING = "connecting"
    BOOTLOADER = "bootloader"
    RECOVERY = "recovery"
    SIDELOAD = "sideload"
    UNKNOWN = "unknown"

    @classmethod
    def _missing_(cls, value):
        # adb adds states between releases, and "no permissions (...)" is not a single word.
        return cls.UNKNOWN


class KeyCode(IntEnum):
    """Android ``KEYCODE_*`` values accepted by ``input keyevent``.

    Only the keys a device-control tool needs. Values are from
    https://developer.android.com/reference/android/view/KeyEvent.
    """

    HOME = 3
    BACK = 4
    DPAD_UP = 19
    DPAD_DOWN = 20
    DPAD_LEFT = 21
    DPAD_RIGHT = 22
    DPAD_CENTER = 23
    VOLUME_UP = 24
    VOLUME_DOWN = 25
    POWER = 26
    CAMERA = 27
    TAB = 61
    SPACE = 62
    ENTER = 66
    DELETE = 67
    FORWARD_DELETE = 112
    MENU = 82
    SEARCH = 84
    VOLUME_MUTE = 164
    APP_SWITCH = 187

    @classmethod
    def parse(cls, name: str) -> "KeyCode":
        """Look a key up by the name a person would use: ``"back"``, ``"Volume Up"``, ``"recent"``.

        Case, spaces and hyphens do not matter. The shorter names the original tool accepted
        also work: ``up``/``down``/``left``/``right``/``center`` for the d-pad, ``recent`` for the
        app switcher, ``del`` for delete.

        Raises:
            ValueError: if ``name`` is not a known key, listing the ones that are.
        """
        normalized = name.strip().lower().replace(" ", "_").replace("-", "_")
        normalized = _KEY_ALIASES.get(normalized, normalized).upper()
        try:
            return cls[normalized]
        except KeyError:
            known = ", ".join(key.name.lower() for key in cls)
            raise ValueError(f"unknown key {name!r}. Known keys: {known}") from None


_KEY_ALIASES = {
    "up": "dpad_up",
    "down": "dpad_down",
    "left": "dpad_left",
    "right": "dpad_right",
    "center": "dpad_center",
    "recent": "app_switch",
    "recents": "app_switch",
    "del": "delete",
}
