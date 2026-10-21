"""Touch, key and text input, sent with ``adb shell input``."""

import re
import shlex
import unicodedata

from .core import shell
from .enums import KeyCode
from .keyboard import INSTALL_HINT, is_keyboard_installed, keyboard_session


def tap(x: int, y: int, *, serial: str | None = None) -> None:
    """Tap the screen at pixel ``(x, y)``."""
    shell(f"input tap {x} {y}", serial=serial)


def long_press(x: int, y: int, *, duration_ms: int = 1000, serial: str | None = None) -> None:
    """Press and hold at pixel ``(x, y)`` for ``duration_ms`` milliseconds."""
    # ``input`` has no long-press command; a zero-distance swipe held for a while is one.
    shell(f"input swipe {x} {y} {x} {y} {duration_ms}", serial=serial)


def swipe(
    x1: int, y1: int, x2: int, y2: int, *, duration_ms: int = 300, serial: str | None = None
) -> None:
    """Swipe from ``(x1, y1)`` to ``(x2, y2)`` over ``duration_ms`` milliseconds."""
    shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}", serial=serial)


def drag(
    x1: int, y1: int, x2: int, y2: int, *, duration_ms: int = 500, serial: str | None = None
) -> None:
    """Press at ``(x1, y1)``, drag to ``(x2, y2)`` and release, e.g. to move an icon.

    Unlike :func:`swipe` this starts with a press-and-hold, so it picks things up. ``input
    draganddrop`` exists from Android 8.0 (API 26); earlier releases fail with an adb error.
    """
    shell(f"input draganddrop {x1} {y1} {x2} {y2} {duration_ms}", serial=serial)


def press_key(key: KeyCode | int, *, serial: str | None = None) -> None:
    """Press and release a hardware or navigation key, such as :attr:`KeyCode.BACK`."""
    shell(f"input keyevent {int(key)}", serial=serial)


def clear_text(*, serial: str | None = None) -> None:
    """Empty the focused text field, whatever its length and wherever the caret is.

    Selects everything with Ctrl+A and deletes it. ``input keycombination`` exists from Android 12;
    on an older device, which answers "Unknown command", this presses Delete and Forward Delete
    200 times each instead. That is slow (about three seconds) and leaves whatever is longer than
    200 characters.
    """
    output = shell(f"input keycombination {_CTRL_LEFT} {_KEY_A}", serial=serial)
    if "Unknown command" not in output:
        press_key(KeyCode.DELETE, serial=serial)
        return
    pair = f"{int(KeyCode.DELETE)} {int(KeyCode.FORWARD_DELETE)} "
    shell(f"input keyevent {(pair * _FALLBACK_CLEAR_LENGTH).strip()}", serial=serial)


_CTRL_LEFT, _KEY_A = 113, 29  # KEYCODE_CTRL_LEFT, KEYCODE_A
_FALLBACK_CLEAR_LENGTH = 200


class UntypeableTextError(ValueError):
    """``input text`` cannot type some of the text.

    Attributes:
        characters: Each character that is the problem, once, in order.
    """

    def __init__(self, characters: list[str]):
        self.characters = characters
        super().__init__(
            f"type_text cannot type {', '.join(map(repr, characters))} with `input text`, which "
            "types printable ASCII, newline, tab and accented Latin letters made from a grave, "
            "acute, circumflex, tilde or umlaut"
        )


def _normalize(text: str) -> str:
    """Use ``\\n`` for line breaks and refuse control characters, which nothing can type."""
    text = text.replace("\r\n", "\n")
    control = [
        char
        for char in dict.fromkeys(text)
        if char not in "\n\t" and unicodedata.category(char) in ("Cc", "Cs")
    ]
    if control:
        raise ValueError(
            f"type_text cannot type the control characters {', '.join(map(repr, control))}"
        )
    return text


def _require_keyboard(error: UntypeableTextError, serial: str | None) -> None:
    """Let ``error`` stand unless the ADBKeyboard app is installed to type the text instead."""
    if not is_keyboard_installed(serial=serial):
        raise ValueError(f"{error}. {INSTALL_HINT}") from None


def check_typeable(text: str, *, serial: str | None = None) -> None:
    """Raise if :func:`type_text` could not type ``text``, without typing anything.

    Lets a caller that is about to change something first (clear a field, tap into it) find out
    before it has done so. Text that needs the ADBKeyboard app is only checked against the device
    when it has to be, so ordinary text never touches it.

    Raises:
        ValueError: as :func:`type_text` does.
        AdbError: if the device cannot be asked whether the app is installed.
    """
    text = _normalize(text)
    try:
        _as_key_text(text)
    except UntypeableTextError as error:
        _require_keyboard(error, serial)


def type_text(text: str, *, serial: str | None = None) -> None:
    """Type ``text`` into the focused field.

    ``input text`` sends key events, so it types printable ASCII plus the accented Latin letters
    that Android's virtual keyboard can compose (``é ñ ü ÿ`` and 107 others, but not ``ç ß å ø``).
    Anything else (CJK, Cyrillic, emoji) is typed through the ADBKeyboard app when it is installed
    on the device; see :mod:`.keyboard`. That switches the device's keyboard for about a second
    and needs a text field to be focused.

    A newline is sent as the Enter key and a tab as the Tab key, so what happens next depends on
    the field: Enter inserts a line break in a multi-line field but may submit a search box.

    Raises:
        ValueError: if ``text`` has a control character other than newline and tab, or a
            character only the ADBKeyboard app could type and it is not installed. Nothing is
            sent. (Left to the device, a character ``input text`` cannot type makes the whole
            call crash with a ``NullPointerException`` and exit status 255.)
        AdbError: if the ADBKeyboard app is used and does not become ready, usually because no
            text field is focused.
    """
    text = _normalize(text)
    try:
        keyed = _as_key_text(text)
    except UntypeableTextError as error:
        _require_keyboard(error, serial)
        _type_with_keyboard(text, serial)
        return
    _type_keyed(keyed, serial)


def _type_keyed(text: str, serial: str | None) -> None:
    for part in re.split(r"([\n\t])", text):
        if part == "\n":
            press_key(KeyCode.ENTER, serial=serial)
        elif part == "\t":
            press_key(KeyCode.TAB, serial=serial)
        elif part:
            _input_text(part, serial)


def _type_with_keyboard(text: str, serial: str | None) -> None:
    """Type ``text`` through ADBKeyboard, in one session so the keyboard is switched once."""
    with keyboard_session(serial=serial) as send:
        for part in re.split(r"([\n\t])", text):
            if part == "\n":
                press_key(KeyCode.ENTER, serial=serial)
            elif part == "\t":
                press_key(KeyCode.TAB, serial=serial)
            elif part:
                send(part)


# The accents Android's virtual keyboard layout treats as dead keys: sent before a letter they
# compose it (U+0301 then ``e`` is ``é``), sent after one they come out as a separate character.
_DEAD_KEYS = frozenset("\u0300\u0301\u0302\u0303\u0308")  # grave, acute, circumflex, tilde, umlaut


def _as_key_text(text: str) -> str:
    """Rewrite accented letters as dead key + letter, leaving what ``input text`` types as it is.

    Raises:
        UntypeableTextError: naming every character that cannot be typed.
    """
    typeable, untypeable = [], []
    # NFC first, so ``e`` followed by U+0301 and a precomposed ``é`` take the same path.
    for char in unicodedata.normalize("NFC", text):
        base, *accents = unicodedata.normalize("NFD", char)
        if char in "\n\t" or (char.isascii() and char.isprintable()):
            typeable.append(char)
        elif base.isascii() and base.isalpha() and len(accents) == 1 and accents[0] in _DEAD_KEYS:
            typeable.append(accents[0] + base)
        else:
            untypeable.append(char)
    if untypeable:
        raise UntypeableTextError(list(dict.fromkeys(untypeable)))
    return "".join(typeable)


def _input_text(text: str, serial: str | None) -> None:
    """Send text that ``input text`` can type, one call per chunk that is safe to send."""
    # ``input text`` reads the two characters ``%s`` as a space, and that is also the only way it
    # accepts a space. So a literal ``%`` must never sit in front of an ``s`` or a space within one
    # call: split there, and the device sees the ``%`` at the end of one call and the next
    # character at the start of the next.
    for chunk in re.split(r"(?<=%)(?=[s ])", text):
        # Quoting keeps the device shell from acting on characters like & | ; $ and quotes.
        shell(f"input text {shlex.quote(chunk.replace(' ', '%s'))}", serial=serial)
