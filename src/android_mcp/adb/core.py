"""Low-level adb functions: locate the binary, run commands, list devices.

Everything the layers above need from a device goes through here: shell commands, screen capture
and the UI hierarchy dump. Touch, key and text input are in :mod:`.input`.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .enums import DeviceState
from .errors import AdbCommandError, AdbError, AdbNotFoundError, ScreenNotIdleError

# The one explicit knob. A host that launches the server from a desktop GUI often hands it a
# different PATH from the user's terminal, so this lets the user name the binary outright.
OVERRIDE_VAR = "ANDROID_MCP_ADB_PATH"

_ADB_EXE = "adb.exe" if os.name == "nt" else "adb"

# Where a manual or Homebrew install of platform-tools lands. Not on PATH for GUI-launched hosts.
_POSIX_BIN_DIRS = () if os.name == "nt" else (Path("/opt/homebrew/bin"), Path("/usr/local/bin"))

# Without this, every adb call from a windowless host flashes a console window on Windows.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def _env(name: str) -> str | None:
    """Read an environment variable, treating unset and blank the same (hosts pass blanks)."""
    return os.environ.get(name, "").strip() or None


def _is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _sdk_roots() -> list[Path]:
    """Android SDK roots to search, most explicit first, without duplicates.

    ``ANDROID_HOME`` and ``ANDROID_SDK_ROOT`` come first, then the default location Android
    Studio installs to on macOS, Linux and Windows.
    """
    home = Path.home()
    roots = [
        _env("ANDROID_HOME"),
        _env("ANDROID_SDK_ROOT"),
        home / "Library" / "Android" / "sdk",  # macOS
        home / "Android" / "Sdk",  # Linux
    ]
    local_app_data = _env("LOCALAPPDATA")
    if local_app_data:
        roots.append(Path(local_app_data) / "Android" / "Sdk")  # Windows
    return list(dict.fromkeys(Path(root) for root in roots if root))


def _search_dirs() -> list[Path]:
    """Directories probed for adb after ``PATH``, in order."""
    return [root / "platform-tools" for root in _sdk_roots()] + list(_POSIX_BIN_DIRS)


def find_adb() -> str:
    """Find the adb binary to run.

    Resolution order: the ``ANDROID_MCP_ADB_PATH`` override, ``PATH``, then each Android SDK
    ``platform-tools`` directory. ``PATH`` comes before the SDK so an installation that already
    works keeps being used.

    Returns:
        The path to an executable adb.

    Raises:
        AdbNotFoundError: if the override is set but does not name an executable file (a typo
            must fail visibly, not be replaced by some other adb), or if no adb is found.
    """
    override = _env(OVERRIDE_VAR)
    if override is not None:
        if not _is_executable(Path(override)):
            raise AdbNotFoundError(
                f"{OVERRIDE_VAR} is set to {override!r}, which is not an executable file."
            )
        return override

    on_path = shutil.which("adb")
    if on_path:
        return on_path

    searched = _search_dirs()
    for directory in searched:
        candidate = directory / _ADB_EXE
        if _is_executable(candidate):
            return str(candidate)

    raise AdbNotFoundError(
        "adb not found. Install Android platform-tools, then either put adb on PATH, point "
        f"ANDROID_HOME or ANDROID_SDK_ROOT at the SDK, or set {OVERRIDE_VAR} to the adb binary. "
        f"Searched PATH ({os.environ.get('PATH', '')}) and: "
        + ", ".join(str(directory) for directory in searched)
    )


def _execute(args: tuple[str, ...], serial: str | None, timeout: float) -> bytes:
    """Run adb and return its raw stdout. See :func:`run` for the arguments and errors."""
    command = [find_adb()]
    if serial is not None:
        command += ["-s", serial]
    command += args

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            # The MCP server speaks over stdin; a child that inherited it could eat protocol bytes.
            stdin=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as error:
        raise AdbCommandError(command, None, f"no result after {timeout}s") from error

    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise AdbCommandError(command, completed.returncode, detail)
    return completed.stdout


def run(*args: str, serial: str | None = None, timeout: float = 30) -> str:
    """Run ``adb`` with ``args`` and return its stdout.

    Args:
        *args: Everything after ``adb``, e.g. ``"devices", "-l"``.
        serial: Target device, passed as ``-s <serial>``. Omit for commands that need none.
        timeout: Seconds to wait before giving up on the command.

    Returns:
        The command's standard output, decoded as UTF-8 with ``\\r\\n`` read as ``\\n``.

    Raises:
        AdbNotFoundError: if adb cannot be located.
        AdbCommandError: if adb exits non-zero or does not finish within ``timeout``.
    """
    output = _execute(args, serial, timeout)
    return output.decode("utf-8", errors="replace").replace("\r\n", "\n")


def run_bytes(*args: str, serial: str | None = None, timeout: float = 30) -> bytes:
    """Run ``adb`` with ``args`` and return its stdout untouched, for binary output.

    Takes the same arguments and raises the same errors as :func:`run`.
    """
    return _execute(args, serial, timeout)


@dataclass(frozen=True)
class Device:
    """One line of ``adb devices -l``.

    Attributes:
        serial: The id adb knows the device by: ``emulator-5554``, a USB serial, or ``host:port``.
        state: Whether the device is ready, offline, waiting for authorization, and so on.
        model: The ``model:`` field adb reports, when it reports one.
    """

    serial: str
    state: DeviceState
    model: str | None = None


def list_devices() -> list[Device]:
    """List the devices adb can see.

    Returns:
        Every attached device in adb's order, whatever its state. Callers that need a usable
        one should check for :attr:`DeviceState.DEVICE`.

    Raises:
        AdbNotFoundError: if adb cannot be located.
        AdbCommandError: if ``adb devices`` fails.
    """
    devices = []
    for line in run("devices", "-l").splitlines():
        fields = line.split()
        # Skips the header, blank lines, and the "* daemon started" notices adb prints.
        if len(fields) < 2 or line.startswith(("*", "List of devices")):
            continue
        details = dict(field.split(":", 1) for field in fields[2:] if ":" in field)
        devices.append(Device(fields[0], DeviceState(fields[1]), details.get("model")))
    return devices


def shell(command: str, *, serial: str | None = None, timeout: float = 30) -> str:
    """Run ``command`` in the device's shell and return its output.

    Args:
        command: One shell command line, interpreted by the device's shell.
        serial: Target device. Omit when exactly one device is attached.
        timeout: Seconds to wait before giving up on the command.

    Returns:
        The command's standard output.

    Raises:
        AdbNotFoundError: if adb cannot be located.
        AdbCommandError: if the command exits non-zero, adb fails, or the timeout passes.
    """
    return run("shell", command, serial=serial, timeout=timeout)


def screencap(*, serial: str | None = None, timeout: float = 30) -> bytes:
    """Capture the device's screen.

    Uses ``exec-out`` rather than ``shell`` because ``shell`` can rewrite line endings inside
    binary output and corrupt the PNG.

    Returns:
        The screenshot as PNG bytes.

    Raises:
        AdbNotFoundError: if adb cannot be located.
        AdbCommandError: if the capture fails or the timeout passes.
    """
    return run_bytes("exec-out", "screencap", "-p", serial=serial, timeout=timeout)


def dump_hierarchy(*, serial: str | None = None, timeout: float = 30) -> str:
    """Dump the screen's UI hierarchy as the XML ``uiautomator dump`` produces.

    Writes to ``/dev/tty`` so the XML comes back on stdout, with no file left on the device.

    Returns:
        The XML document, from ``<?xml`` to its closing tag. adb's trailing "UI hierchary dumped
        to" notice is dropped.

    Raises:
        AdbNotFoundError: if adb cannot be located.
        AdbCommandError: if the command fails or the timeout passes.
        ScreenNotIdleError: if the screen keeps changing, so uiautomator gives up after about ten
            seconds. Retrying does not help while the cause (a video, a running timer, an
            animation) is still on screen.
        AdbError: if uiautomator exits normally but prints some other error instead of XML, as it
            does when the screen is off or has no window ("null root node").
    """
    output = run("exec-out", "uiautomator", "dump", "/dev/tty", serial=serial, timeout=timeout)
    start, end = output.find("<?xml"), output.rfind(">")
    if start == -1 or end < start:
        # uiautomator waits for one quiet second within ten and has no option to skip that.
        if "could not get idle state" in output:
            raise ScreenNotIdleError(
                "the screen never went idle: something on it (a video, a running timer, an "
                "animation) keeps changing, so uiautomator gave up waiting to dump it"
            )
        raise AdbError(f"uiautomator dump returned no hierarchy: {output.strip()[:200]!r}")
    return output[start : end + 1]


def connect(address: str, *, timeout: float = 15) -> None:
    """Connect adb to a device over the network.

    Args:
        address: ``host`` or ``host:port``. adb assumes port 5555 when there is none.
        timeout: Seconds to wait for the connection.

    Raises:
        AdbNotFoundError: if adb cannot be located.
        AdbCommandError: if the command itself fails or times out.
        AdbError: if adb ran but could not connect. It reports that in its output and still
            exits 0, so the output is what is checked.
    """
    output = run("connect", address, timeout=timeout).strip()
    if not output.lower().startswith(("connected to", "already connected to")):
        raise AdbError(output or f"adb connect {address} printed nothing")


def connect_mdns_peers(*, timeout: float = 5) -> list[str]:
    """Connect to every device advertising wireless debugging that is not connected yet.

    Android 11 and later advertise ``_adb-tls-connect`` over mDNS once wireless debugging is
    paired, but adb does not connect to them by itself.

    Returns:
        The ``host:port`` addresses connected. Empty when mDNS is unavailable or nothing is
        advertised; neither is an error. A peer that refuses is skipped.
    """
    try:
        output = run("mdns", "services", timeout=timeout)
    except AdbCommandError:
        return []
    connected = []
    for line in output.splitlines():
        fields = line.split()
        # "<service name>  _adb-tls-connect._tcp  <ip>:<port>"
        if len(fields) >= 3 and "_adb-tls-connect" in fields[1]:
            try:
                connect(fields[-1], timeout=timeout)
            except AdbError:
                continue
            connected.append(fields[-1])
    return connected


def expand_notifications(*, serial: str | None = None) -> None:
    """Pull down the notification shade (and expand quick settings if the device has them)."""
    shell("cmd statusbar expand-notifications", serial=serial)
