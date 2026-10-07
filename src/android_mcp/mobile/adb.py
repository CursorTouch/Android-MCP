"""Locate adb in one place and share the choice with adbutils.

adbutils (which uiautomator2 uses underneath) checks ``ADBUTILS_ADB_PATH``, then ``PATH``,
then its bundled adb when the wheel ships one (Windows only). It does not search Android
SDK roots. The server's own ``subprocess`` calls used a bare ``"adb"``, which only works
when adb is on ``PATH``. MCP hosts started from a desktop GUI often give the server a
different ``PATH`` from the user's terminal, so a machine with Android Studio installed
still reported "adb not found".

This module adds the SDK locations Android Studio writes to (plus the Homebrew and
``/usr/local`` bin directories) and publishes the result through ``ADBUTILS_ADB_PATH`` so
adbutils and our subprocess calls run the same binary.
"""
import os
import shutil
from typing import Optional

_ADB_EXE = "adb.exe" if os.name == "nt" else "adb"

# Explicit overrides, most specific first. ANDROID_MCP_ADB_PATH is this server's own knob
# (and the one manifest.json wires to its user_config); ADBUTILS_ADB_PATH is adbutils'.
OVERRIDE_VARS = ("ANDROID_MCP_ADB_PATH", "ADBUTILS_ADB_PATH")

# Common non-SDK installs (brew install --cask android-platform-tools, manual installs).
_POSIX_BIN_DIRS = () if os.name == "nt" else ("/opt/homebrew/bin", "/usr/local/bin")


class AdbNotFoundError(RuntimeError):
    """Raised when no usable adb binary could be located."""


def _clean(value: Optional[str]) -> Optional[str]:
    """Treat unset and blank environment values the same (MCP hosts pass blanks)."""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _is_executable(path: Optional[str]) -> bool:
    return bool(path) and os.path.isfile(path) and os.access(path, os.X_OK)


def sdk_roots() -> list[str]:
    """Android SDK roots to search, most explicit first, without duplicates.

    Returns:
        ``ANDROID_HOME``, ``ANDROID_SDK_ROOT``, then the default location Android Studio
        installs to on each platform. Unset and blank entries are dropped.
    """
    home = os.path.expanduser("~")
    local_app_data = _clean(os.environ.get("LOCALAPPDATA"))
    roots = [
        _clean(os.environ.get("ANDROID_HOME")),
        _clean(os.environ.get("ANDROID_SDK_ROOT")),
        os.path.join(home, "Library", "Android", "sdk"),  # macOS
        os.path.join(home, "Android", "Sdk"),  # Linux
        os.path.join(local_app_data, "Android", "Sdk") if local_app_data else None,  # Windows
    ]
    return list(dict.fromkeys(root for root in roots if root))


def search_dirs() -> list[str]:
    """Directories probed for adb after ``PATH``, in order."""
    dirs = [os.path.join(root, "platform-tools") for root in sdk_roots()]
    dirs.extend(_POSIX_BIN_DIRS)
    return dirs


def explicit_adb() -> Optional[str]:
    """Return the adb named by an override variable, if any is set.

    Returns:
        The first non-blank value among :data:`OVERRIDE_VARS`, or ``None``.

    Raises:
        AdbNotFoundError: when that value does not name an executable file. A typo or a
            directory must fail visibly instead of being replaced by another adb.
    """
    for name in OVERRIDE_VARS:
        value = _clean(os.environ.get(name))
        if value is None:
            continue
        if not _is_executable(value):
            raise AdbNotFoundError(f"{name} is set to {value!r}, which is not an executable file.")
        return value
    return None


def find_adb() -> Optional[str]:
    """Find the adb binary.

    Resolution order: an explicit override (:func:`explicit_adb`), ``PATH``, then each of
    :func:`search_dirs`. ``PATH`` comes before the SDK so an installation that already works
    keeps being used.

    Returns:
        The path to an executable adb, or ``None`` when nothing usable was found.

    Raises:
        AdbNotFoundError: only when an override variable is set to something unusable.
    """
    explicit = explicit_adb()
    if explicit:
        return explicit

    on_path = shutil.which("adb")
    if on_path:
        return on_path

    for directory in search_dirs():
        candidate = os.path.join(directory, _ADB_EXE)
        if _is_executable(candidate):
            return candidate

    return None


def publish(path: str) -> None:
    """Make adbutils use ``path`` when it starts the adb server for uiautomator2."""
    if os.environ.get("ADBUTILS_ADB_PATH") != path:
        os.environ["ADBUTILS_ADB_PATH"] = path


def adb_path() -> str:
    """Return the adb binary to run, and make adbutils use the same one.

    Returns:
        The path to an executable adb.

    Raises:
        AdbNotFoundError: when adb is neither on ``PATH`` nor in a known location.
    """
    path = find_adb()
    if path is None:
        raise AdbNotFoundError(
            "adb not found. Install Android platform-tools, then either put adb on PATH, "
            "point ANDROID_HOME or ANDROID_SDK_ROOT at the SDK, or set ANDROID_MCP_ADB_PATH "
            f"to the adb binary. Searched PATH ({os.environ.get('PATH', '')!r}) and: "
            + ", ".join(search_dirs())
        )
    publish(path)
    return path
