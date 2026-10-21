"""Tests for typing through the ADBKeyboard app, against a simulated device.

``FakeAndroid`` answers the shell commands the module sends (``pm``, ``ime``, ``settings``,
``dumpsys input_method``, ``am broadcast``) and keeps the state they change, so the tests check
what the device would be left with, not just which commands ran. The clock is fake, so polling
costs no real time.
"""

import base64
import re
import shlex

import pytest

import android_mcp.adb as adb
from android_mcp.adb import input, keyboard

LATIN = "com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME"
OURS = keyboard.KEYBOARD_IME


class FakeAndroid:
    """A device with an input-method manager, answering shell commands."""

    def __init__(self):
        self.installed = True
        self.listed_after_polls = 0  # polls of `ime list -a` before the app is listed
        self.enabled = [LATIN]
        self.current = LATIN
        self.focused_field = True
        self.ready_after_polls = 3  # dumpsys polls after `ime set` before the app is bound
        self.dump_format = "known"  # "known" or "unknown"
        self.fail = {}  # command prefix -> detail: raise AdbCommandError(detail)
        self.broadcast_output = "Broadcast completed: result=0"
        self.log = []
        self.broadcasts = []
        self.clock = 0.0
        self.sleeps = []
        self._list_polls = 0
        self._ready_polls = 0

    # -- the clock the module sees --------------------------------------------------------
    def monotonic(self):
        return self.clock

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.clock += seconds

    # -- shell ------------------------------------------------------------------------------
    def shell(self, command, *, serial=None, timeout=30):
        self.log.append(command)
        for prefix, detail in self.fail.items():
            if command.startswith(prefix):
                raise adb.AdbCommandError(["adb", "shell", command], 1, detail)
        if command.startswith("pm list packages"):
            return f"package:{keyboard.KEYBOARD_PACKAGE}\n" if self.installed else ""
        if command == "settings get secure default_input_method":
            return (self.current or "null") + "\n"
        if command == "ime list -s":
            return "\n".join(self.enabled) + "\n"
        if command == "ime list -s -a":
            self._list_polls += 1
            ids = [LATIN]
            if self.installed and self._list_polls > self.listed_after_polls:
                ids.append(OURS)
            return "\n".join(ids) + "\n"
        if command.startswith("ime enable "):
            self.enabled.append(command.removeprefix("ime enable "))
            return "now enabled\n"
        if command.startswith("ime disable "):
            self.enabled.remove(command.removeprefix("ime disable "))
            return "now disabled\n"
        if command.startswith("ime set "):
            self.current = command.removeprefix("ime set ")
            self._ready_polls = 0
            return "selected\n"
        if command == "ime reset":
            self.current = LATIN
            self._ready_polls = 0
            return "reset\n"
        if command == "dumpsys input_method":
            return self._dump()
        if command.startswith("am broadcast "):
            match = re.fullmatch(r"am broadcast -a ADB_INPUT_B64 --es msg (.+)", command)
            assert match, command
            self.broadcasts.append(base64.b64decode(shlex.split(match.group(1))[0]).decode())
            return self.broadcast_output + "\n"
        raise AssertionError(f"unexpected command: {command}")

    def _dump(self):
        if self.dump_format == "unknown":
            return "Some new dump layout\n  nothing we know\n"
        self._ready_polls += 1
        bound = self._ready_polls > self.ready_after_polls
        connection = "RemoteInputConnection{idHash=#1}" if bound and self.focused_field else "null"
        return (
            f"  mCurId={self.current} mHaveConnection=true mBoundToMethod={str(bound).lower()} "
            f"mVisibleBound={str(bound).lower()}\n"
            f"  mStartedInputConnection={connection}\n"
        )

    # -- helpers for assertions ---------------------------------------------------------------
    def changes(self):
        """The commands that changed the device's keyboard settings, in order."""
        return [
            c
            for c in self.log
            if c.startswith(("ime enable", "ime set", "ime disable", "ime reset"))
        ]


@pytest.fixture
def android(monkeypatch):
    """A simulated device under the keyboard module and the input module."""
    fake = FakeAndroid()
    monkeypatch.setattr(keyboard, "shell", fake.shell)
    monkeypatch.setattr(keyboard, "monotonic", fake.monotonic)
    monkeypatch.setattr(keyboard, "sleep", fake.sleep)
    monkeypatch.setattr(input, "shell", fake.shell)
    return fake


@pytest.mark.unit
class TestIsKeyboardInstalled:
    """Tests for is_keyboard_installed."""

    def test_installed(self, android):
        """The package is listed."""
        assert adb.is_keyboard_installed() is True

    def test_not_installed(self, android):
        """Nothing is listed."""
        android.installed = False

        assert adb.is_keyboard_installed() is False

    def test_a_package_that_merely_starts_with_the_name_does_not_count(self, android, monkeypatch):
        """``pm list packages`` matches substrings; only the exact package is the app."""
        monkeypatch.setattr(
            keyboard, "shell", lambda *a, **k: "package:com.android.adbkeyboard.other\n"
        )

        assert adb.is_keyboard_installed() is False


@pytest.mark.unit
class TestSession:
    """Tests for keyboard_session: switching to the app and back."""

    def test_switches_types_and_restores(self, android):
        """The app is enabled, selected, waited for, used, and then everything is put back."""
        with adb.keyboard_session() as send:
            assert android.current == OURS
            send("日本語")

        assert android.broadcasts == ["日本語"]
        assert android.current == LATIN
        assert android.enabled == [LATIN]
        assert android.changes() == [
            f"ime enable {OURS}",
            f"ime set {OURS}",
            f"ime set {LATIN}",
            f"ime disable {OURS}",
        ]

    def test_waits_for_the_app_to_be_ready_before_sending(self, android):
        """The dump is polled until the app is bound with an input connection."""
        android.ready_after_polls = 4

        with adb.keyboard_session() as send:
            polls_before_send = android.log.count("dumpsys input_method")
            send("x")

        assert polls_before_send == 5  # four "not yet", then ready
        assert len(android.broadcasts) == 1

    def test_an_app_that_is_already_enabled_is_not_enabled_or_disabled_again(self, android):
        """The user's own setup is left as it was found."""
        android.enabled = [LATIN, OURS]

        with adb.keyboard_session() as send:
            send("x")

        assert android.enabled == [LATIN, OURS]
        assert android.changes() == [f"ime set {OURS}", f"ime set {LATIN}"]
        assert "ime list -s -a" not in android.log

    def test_a_newly_installed_app_is_waited_for_until_android_lists_it(self, android):
        """Android lists a new input method a moment late; enabling too early would fail."""
        android.listed_after_polls = 3

        with adb.keyboard_session() as send:
            send("x")

        assert android.log.count("ime list -s -a") == 4
        assert android.broadcasts == ["x"]

    def test_an_app_that_never_gets_listed_is_an_error_and_changes_nothing(self, android):
        """Installed but invisible to the input-method manager: say so, touch nothing."""
        android.listed_after_polls = 10_000

        with pytest.raises(adb.AdbError, match="does not list it as an input method"):
            with adb.keyboard_session():
                pytest.fail("the body must not run")

        assert android.changes() == []
        assert android.current == LATIN

    def test_the_original_keyboard_is_restored_exactly(self, android):
        """Whatever was selected before comes back."""
        other = "com.example.keyboard/.Ime"
        android.enabled = [LATIN, other]
        android.current = other

        with adb.keyboard_session() as send:
            send("x")

        assert android.current == other

    def test_with_no_keyboard_selected_the_default_is_reset(self, android):
        """A device with no default input method is returned to its default, not to ``null``."""
        android.current = None

        with adb.keyboard_session() as send:
            send("x")

        assert "ime reset" in android.log
        assert "ime set None" not in android.log

    def test_not_installed_is_an_error_with_install_instructions_and_changes_nothing(self, android):
        """The message says where to get the app; the device is not touched."""
        android.installed = False

        with pytest.raises(adb.AdbError, match="not installed") as info:
            with adb.keyboard_session():
                pytest.fail("the body must not run")

        assert adb.KEYBOARD_URL in str(info.value)
        assert android.changes() == []

    def test_not_ready_in_time_says_to_focus_a_field_and_restores(self, android):
        """With no focused field the app never gets an input connection."""
        android.focused_field = False

        with pytest.raises(adb.AdbError, match="Is a text field focused") as info:
            with adb.keyboard_session(ready_timeout=2):
                pytest.fail("the body must not run")

        assert "not ready after 2s" in str(info.value)
        assert android.broadcasts == []
        assert android.current == LATIN and android.enabled == [LATIN]
        assert android.clock >= 2

    def test_a_different_keyboard_being_current_is_not_ready(self, android, monkeypatch):
        """Bound and connected, but to another keyboard: that is not our app."""

        def dump(*args, **kwargs):
            return (
                f"  mCurId={LATIN} mHaveConnection=true mBoundToMethod=true\n"
                "  mStartedInputConnection=RemoteInputConnection{idHash=#1}\n"
            )

        original = android.shell

        def shell(command, **kwargs):
            return dump() if command == "dumpsys input_method" else original(command, **kwargs)

        monkeypatch.setattr(keyboard, "shell", shell)

        with pytest.raises(adb.AdbError, match="not ready"):
            with adb.keyboard_session(ready_timeout=1):
                pass

    def test_an_unknown_dump_format_falls_back_to_a_fixed_wait(self, android):
        """If Android's dump has none of the fields, wait a moment and go ahead."""
        android.dump_format = "unknown"

        with adb.keyboard_session() as send:
            send("x")

        assert android.broadcasts == ["x"]
        assert keyboard._BLIND_WAIT in android.sleeps

    def test_a_failure_inside_the_session_still_restores(self, android):
        """An exception in the body propagates, after the keyboard is put back."""
        with pytest.raises(RuntimeError, match="boom"):
            with adb.keyboard_session():
                raise RuntimeError("boom")

        assert android.current == LATIN and android.enabled == [LATIN]

    def test_an_interrupt_still_restores(self, android):
        """Even Ctrl+C leaves the device's keyboard as it was."""
        with pytest.raises(KeyboardInterrupt):
            with adb.keyboard_session():
                raise KeyboardInterrupt

        assert android.current == LATIN and android.enabled == [LATIN]

    def test_a_broadcast_that_was_not_delivered_is_an_error_and_restores(self, android):
        """If ``am`` does not report the broadcast completed, say so."""
        android.broadcast_output = "Error: Activity manager is not running"

        with pytest.raises(adb.AdbError, match="not delivered"):
            with adb.keyboard_session() as send:
                send("x")

        assert android.current == LATIN

    def test_failing_to_restore_after_success_is_an_error_with_the_fix(self, android):
        """Typing worked but the user's keyboard is stuck: say exactly how to fix it."""
        android.fail[f"ime set {LATIN}"] = "permission denied"

        with pytest.raises(adb.AdbError, match="original keyboard back") as info:
            with adb.keyboard_session() as send:
                send("x")

        assert f"adb shell ime set {LATIN}" in str(info.value)

    def test_failing_to_restore_after_another_error_keeps_the_first_error(self, android):
        """The original failure is what propagates; the restore problem is attached as a note."""
        android.fail[f"ime set {LATIN}"] = "permission denied"

        with pytest.raises(RuntimeError, match="boom") as info:
            with adb.keyboard_session():
                raise RuntimeError("boom")

        assert any("original keyboard back" in note for note in info.value.__notes__)

    def test_a_session_types_several_pieces_with_one_switch(self, android):
        """The keyboard is switched once however many times the function is called."""
        with adb.keyboard_session() as send:
            send("日本")
            send("語")

        assert android.broadcasts == ["日本", "語"]
        assert android.changes().count(f"ime set {OURS}") == 1


@pytest.mark.unit
class TestSending:
    """What the broadcasts carry."""

    @pytest.mark.parametrize(
        "text",
        [
            "日本語",
            "Привет, мир",
            "😀 emoji 👩‍👩‍👧",
            "العربية",
            "mixed ascii and 日本",
            "quotes ' \" ` $HOME & ; | < >",
            "a\\b",
            "%s and %%",
        ],
    )
    def test_text_arrives_unchanged(self, android, text):
        """Base64 carries any text through the device shell untouched."""
        with adb.keyboard_session() as send:
            send(text)

        assert "".join(android.broadcasts) == text

    def test_the_broadcast_is_the_documented_action_with_a_quoted_message(self, android):
        """``ADB_INPUT_B64`` with the text base64-encoded as ``msg``."""
        with adb.keyboard_session() as send:
            send("日本")

        command = next(c for c in android.log if c.startswith("am broadcast"))
        expected = base64.b64encode("日本".encode()).decode()
        assert command == f"am broadcast -a ADB_INPUT_B64 --es msg {expected}"

    def test_long_text_is_split_into_several_broadcasts(self, android):
        """500 characters per broadcast keeps every command short."""
        text = "あ" * 1200

        with adb.keyboard_session() as send:
            send(text)

        assert [len(part) for part in android.broadcasts] == [500, 500, 200]
        assert "".join(android.broadcasts) == text

    def test_a_character_is_never_split_across_broadcasts(self, android):
        """Emoji are outside the BMP; slicing by code point keeps each in one piece."""
        text = "😀" * 1001

        with adb.keyboard_session() as send:
            send(text)

        assert all(part == "😀" * len(part) for part in android.broadcasts)
        assert "".join(android.broadcasts) == text

    def test_empty_text_sends_nothing(self, android):
        """There is nothing to broadcast."""
        with adb.keyboard_session() as send:
            send("")

        assert android.broadcasts == []


@pytest.fixture
def keys(monkeypatch, android):
    """Record the key presses ``type_text`` makes while the keyboard is in use."""
    pressed = []
    monkeypatch.setattr(
        input, "press_key", lambda key, *, serial=None: pressed.append((android.current, key))
    )
    return pressed


@pytest.mark.unit
class TestTypeTextThroughTheKeyboard:
    """type_text uses the app for what ``input text`` cannot type."""

    def test_unicode_text_goes_through_the_keyboard(self, android, keys):
        """CJK is broadcast, with the keyboard switched for it and back after."""
        adb.type_text("日本語")

        assert android.broadcasts == ["日本語"]
        assert android.current == LATIN

    def test_ordinary_text_does_not_switch_the_keyboard(self, android, monkeypatch):
        """Text ``input text`` can type never touches the keyboard settings."""
        sent = []
        monkeypatch.setattr(input, "_input_text", lambda text, serial: sent.append(text))

        adb.type_text("hello café")

        assert sent and android.changes() == [] and android.broadcasts == []

    def test_mixed_text_goes_through_the_keyboard_whole(self, android, keys):
        """One untypeable character moves the whole string, so it stays in one piece."""
        adb.type_text("hello 日本")

        assert android.broadcasts == ["hello 日本"]

    def test_newlines_and_tabs_are_still_key_presses(self, android, keys):
        """Enter and Tab are keys, and the text between them is broadcast."""
        adb.type_text("日本\n語\tです")

        assert android.broadcasts == ["日本", "語", "です"]
        assert [key for _, key in keys] == [adb.KeyCode.ENTER, adb.KeyCode.TAB]

    def test_keys_are_pressed_while_the_app_is_the_keyboard(self, android, keys):
        """The key presses happen inside the session, so the order of text and keys is kept."""
        adb.type_text("日\n本")

        assert [current for current, _ in keys] == [OURS]

    def test_without_the_app_the_error_says_how_to_get_it(self, android, keys):
        """No app, no typing, and the message names the project and the file."""
        android.installed = False

        with pytest.raises(ValueError, match="cannot type") as info:
            adb.type_text("日本語")

        message = str(info.value)
        assert "ADBKeyboard" in message and "keyboardservice-debug.apk" in message
        assert android.changes() == [] and android.broadcasts == []

    def test_no_focused_field_is_reported_and_the_keyboard_restored(self, android, keys):
        """The app cannot commit text with nowhere to put it."""
        android.focused_field = False

        with pytest.raises(adb.AdbError, match="Is a text field focused"):
            adb.type_text("日本語")

        assert android.current == LATIN and android.broadcasts == []

    def test_control_characters_are_refused_before_anything_changes(self, android, keys):
        """A bell in Japanese text never reaches the device."""
        with pytest.raises(ValueError, match="control characters"):
            adb.type_text("日本\x07")

        assert android.log == []
