"""Typing text that ``input text`` cannot, through the optional ADBKeyboard app.

``input text`` only sends key events, so it cannot type CJK, emoji, Cyrillic and so on. The
ADBKeyboard app (https://github.com/senzhk/ADBKeyBoard) is an input method that commits text it
receives in a broadcast. This module drives it, and nothing here is needed unless the device has
it installed. It is licensed GPL-2.0, which is why it is not bundled: it is installed on the device
by the user, and only talked to over broadcasts.

The app is made the active keyboard only while text is being typed, then the keyboard that was
active before is put back, and the app is disabled again if it was not enabled to begin with.
"""

import base64
import re
import shlex
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from time import monotonic, sleep

from .core import shell
from .errors import AdbCommandError, AdbError

KEYBOARD_PACKAGE = "com.android.adbkeyboard"
KEYBOARD_IME = f"{KEYBOARD_PACKAGE}/.AdbIME"
KEYBOARD_URL = "https://github.com/senzhk/ADBKeyBoard/releases"
INSTALL_HINT = (
    f"To type other text, install the ADBKeyboard app on the device: download "
    f"keyboardservice-debug.apk from {KEYBOARD_URL} and run `adb install` on it."
)

# Characters per broadcast. Counted in code points, so a character is never split.
_CHUNK = 500
# How long to wait for the app to be ready. It starts its service when it is selected, which
# takes about 0.7 s on an emulator.
_READY_TIMEOUT = 5.0
_READY_POLL = 0.05
# Android lists a newly installed input method a moment late; wait this long for it.
_LISTED_TIMEOUT = 3.0
# When ``dumpsys`` does not report readiness at all (a format we do not know), wait this long.
_BLIND_WAIT = 1.0


def is_keyboard_installed(*, serial: str | None = None) -> bool:
    """Whether the ADBKeyboard app is installed on the device."""
    output = shell(f"pm list packages {KEYBOARD_PACKAGE}", serial=serial)
    return f"package:{KEYBOARD_PACKAGE}" in output.split()


def _current_ime(serial: str | None) -> str | None:
    """The active input method, or ``None`` when the device has none set."""
    value = shell("settings get secure default_input_method", serial=serial).strip()
    return None if value in ("", "null") else value


def _ime_ids(serial: str | None, *flags: str) -> list[str]:
    return shell(f"ime list -s {' '.join(flags)}".strip(), serial=serial).split()


def _wait_until_listed(serial: str | None) -> None:
    deadline = monotonic() + _LISTED_TIMEOUT
    while KEYBOARD_IME not in _ime_ids(serial, "-a"):
        if monotonic() >= deadline:
            raise AdbError(
                f"{KEYBOARD_IME} is installed but Android does not list it as an input method."
            )
        sleep(_READY_POLL)


def _ready(serial: str | None) -> bool | None:
    """Whether ADBKeyboard is bound and has a text field to commit into.

    Read from ``dumpsys input_method``: the app is the current method, it is bound, and an input
    connection to a focused field has started. Until then a broadcast is silently dropped, and
    the app never says whether it got one.

    Returns:
        ``True`` or ``False``, or ``None`` when the dump has none of these fields, which means a
        format this code does not know.
    """
    output = shell("dumpsys input_method", serial=serial)
    current = re.search(r"mCurId=(\S+)", output)
    bound = re.search(r"mBoundToMethod=(\w+)", output)
    connection = re.search(r"mStartedInputConnection=(\S+)", output)
    if current is None or bound is None:
        return None
    return (
        current.group(1) == KEYBOARD_IME
        and bound.group(1) == "true"
        and connection is not None
        and connection.group(1) != "null"
    )


def _wait_until_ready(serial: str | None, timeout: float) -> None:
    deadline = monotonic() + timeout
    while True:
        state = _ready(serial)
        if state:
            return
        if state is None:
            sleep(_BLIND_WAIT)
            return
        if monotonic() >= deadline:
            raise AdbError(
                f"ADBKeyboard was not ready after {timeout:g}s. Is a text field focused? "
                "Tap the field first."
            )
        sleep(_READY_POLL)


def _chunks(text: str) -> Iterator[str]:
    for start in range(0, len(text), _CHUNK):
        yield text[start : start + _CHUNK]


def _send(text: str, serial: str | None) -> None:
    for chunk in _chunks(text):
        encoded = base64.b64encode(chunk.encode("utf-8")).decode("ascii")
        output = shell(
            f"am broadcast -a ADB_INPUT_B64 --es msg {shlex.quote(encoded)}", serial=serial
        )
        if "Broadcast completed" not in output:
            raise AdbError(f"ADBKeyboard broadcast was not delivered: {output.strip()[:200]!r}")


def _restore(
    serial: str | None, original: str | None, *, switched: bool, enabled_by_us: bool
) -> None:
    """Undo what the session changed, and only that."""
    back = f"adb shell ime set {original}" if original else "adb shell ime reset"
    try:
        if switched:
            shell(f"ime set {original}" if original else "ime reset", serial=serial)
        if enabled_by_us:
            shell(f"ime disable {KEYBOARD_IME}", serial=serial)
    except AdbCommandError as error:
        raise AdbError(
            f"Could not put the original keyboard back ({error.detail}). The device may be left "
            f"using ADBKeyboard, which shows no keyboard; run `{back}`."
        ) from error


@contextmanager
def keyboard_session(
    *, serial: str | None = None, ready_timeout: float = _READY_TIMEOUT
) -> Iterator[Callable[[str], None]]:
    """Make ADBKeyboard the active keyboard, hand back a function that types, then undo it.

    Switching the keyboard takes about a second, so type everything in one session. A text field
    must already be focused.

    Yields:
        ``send(text)``, which types ``text`` into the focused field.

    Raises:
        AdbError: if the app is not installed or never becomes ready (usually because no text
            field is focused), if a broadcast is not delivered, or if the original keyboard
            cannot be put back.
    """
    if not is_keyboard_installed(serial=serial):
        raise AdbError(f"ADBKeyboard is not installed on the device. {INSTALL_HINT}")
    original = _current_ime(serial)
    was_enabled = KEYBOARD_IME in _ime_ids(serial)
    switched = enabled_by_us = False

    def restore() -> None:
        _restore(serial, original, switched=switched, enabled_by_us=enabled_by_us)

    try:
        if not was_enabled:
            _wait_until_listed(serial)
            shell(f"ime enable {KEYBOARD_IME}", serial=serial)
            enabled_by_us = True
        shell(f"ime set {KEYBOARD_IME}", serial=serial)
        switched = True
        _wait_until_ready(serial, ready_timeout)
        yield lambda text: _send(text, serial)
    except BaseException as error:
        try:
            restore()
        except AdbError as restore_error:
            error.add_note(str(restore_error))
        raise
    else:
        restore()
