"""Tests for input, shell and screencap. Lower layers are replaced to capture the commands."""

import itertools
import shlex

import pytest

import android_mcp.adb as adb
from android_mcp.adb import core, input, keyboard


@pytest.fixture(autouse=True)
def no_keyboard(monkeypatch):
    """The device has no ADBKeyboard app: ``pm list packages`` finds nothing.

    Returns the commands the keyboard module sent, so a test can see whether it was asked.
    """
    asked = []

    def fake_shell(command, *, serial=None, timeout=30):
        asked.append(command)
        return ""

    monkeypatch.setattr(keyboard, "shell", fake_shell)
    return asked


@pytest.fixture
def shell_calls(monkeypatch):
    """Record every ``shell`` call the input functions make as ``(command, serial)``."""
    calls = []

    def fake_shell(command, *, serial=None, timeout=30):
        calls.append((command, serial))
        return ""

    monkeypatch.setattr(input, "shell", fake_shell)
    return calls


def _device_types(command: str) -> str:
    """What the device types for ``input text <arg>``, modelling AOSP's ``Input.sendText``.

    It turns each ``%s`` into a space and leaves every other character, including a lone ``%``,
    as it is.
    """
    words = shlex.split(command)
    assert words[:2] == ["input", "text"] and len(words) == 3, command
    buff = list(words[2])
    escape = False
    i = 0
    while i < len(buff):
        if escape:
            escape = False
            if buff[i] == "s":
                buff[i] = " "
                del buff[i - 1]
                i -= 1
        if buff[i] == "%":
            escape = True
        i += 1
    return "".join(buff)


@pytest.mark.unit
class TestTouch:
    """Tests for tap, long_press, swipe and drag."""

    def test_tap(self, shell_calls):
        """A tap is ``input tap x y``."""
        adb.tap(540, 1200)

        assert shell_calls == [("input tap 540 1200", None)]

    def test_long_press_is_a_zero_distance_swipe(self, shell_calls):
        """A long press holds one point for the given time."""
        adb.long_press(10, 20, duration_ms=1500)

        assert shell_calls == [("input swipe 10 20 10 20 1500", None)]

    def test_swipe(self, shell_calls):
        """A swipe goes between two points over a duration, 300 ms by default."""
        adb.swipe(1, 2, 3, 4)
        adb.swipe(1, 2, 3, 4, duration_ms=900)

        assert shell_calls == [
            ("input swipe 1 2 3 4 300", None),
            ("input swipe 1 2 3 4 900", None),
        ]

    def test_drag(self, shell_calls):
        """A drag is ``input draganddrop``."""
        adb.drag(1, 2, 3, 4)

        assert shell_calls == [("input draganddrop 1 2 3 4 500", None)]

    def test_serial_is_passed_through(self, shell_calls):
        """Every touch function targets the device it is given."""
        adb.tap(1, 1, serial="emulator-5554")
        adb.long_press(1, 1, serial="emulator-5554")
        adb.swipe(1, 1, 2, 2, serial="emulator-5554")
        adb.drag(1, 1, 2, 2, serial="emulator-5554")

        assert {serial for _, serial in shell_calls} == {"emulator-5554"}
        assert len(shell_calls) == 4


@pytest.mark.unit
class TestKeys:
    """Tests for press_key and KeyCode."""

    def test_press_key_sends_the_number(self, shell_calls):
        """A KeyCode member is sent as its Android key code."""
        adb.press_key(adb.KeyCode.BACK)

        assert shell_calls == [("input keyevent 4", None)]

    def test_press_key_accepts_a_raw_code(self, shell_calls):
        """Any other Android key code can be sent as a plain int."""
        adb.press_key(29, serial="emulator-5554")

        assert shell_calls == [("input keyevent 29", "emulator-5554")]

    @pytest.mark.parametrize(
        ("key", "code"),
        [
            (adb.KeyCode.HOME, 3),
            (adb.KeyCode.BACK, 4),
            (adb.KeyCode.ENTER, 66),
            (adb.KeyCode.DELETE, 67),
            (adb.KeyCode.APP_SWITCH, 187),
            (adb.KeyCode.VOLUME_MUTE, 164),
        ],
    )
    def test_key_codes_match_android(self, key, code):
        """Spot-check values against android.view.KeyEvent."""
        assert key == code


@pytest.mark.unit
class TestTypeText:
    """Tests for type_text."""

    def test_plain_text(self, shell_calls):
        """Plain text is passed to ``input text`` as is."""
        adb.type_text("hello")

        assert shell_calls == [("input text hello", None)]

    def test_spaces_become_percent_s(self, shell_calls):
        """``input text`` only accepts a space written as %s."""
        adb.type_text("hello big world")

        assert shell_calls == [("input text hello%sbig%sworld", None)]

    @pytest.mark.parametrize("text", ["a&b", "a|b", "a;b", "$HOME", "a`b`", "(x)", "a>b", "*"])
    def test_shell_metacharacters_are_quoted(self, shell_calls, text):
        """Characters the device shell would act on reach ``input text`` as literal text."""
        adb.type_text(text)

        command, _ = shell_calls[0]
        assert command == f"input text '{text}'"

    def test_single_quote_is_escaped(self, shell_calls):
        """A single quote cannot end the quoting early."""
        adb.type_text("it's")

        assert shell_calls == [("input text 'it'\"'\"'s'", None)]

    def test_newline_is_the_enter_key(self, shell_calls):
        """A newline splits the text around an Enter key press."""
        adb.type_text("a\nb")

        assert shell_calls == [
            ("input text a", None),
            ("input keyevent 66", None),
            ("input text b", None),
        ]

    def test_crlf_is_one_newline(self, shell_calls):
        """Windows line endings press Enter once, not twice."""
        adb.type_text("a\r\nb")

        assert [command for command, _ in shell_calls].count("input keyevent 66") == 1

    def test_tab_is_the_tab_key(self, shell_calls):
        """A tab splits the text around a Tab key press."""
        adb.type_text("a\tb")

        assert shell_calls == [
            ("input text a", None),
            ("input keyevent 61", None),
            ("input text b", None),
        ]

    def test_leading_trailing_and_repeated_breaks(self, shell_calls):
        """Breaks at the edges or back to back press their keys and send no empty text."""
        adb.type_text("\n\ta\n")

        assert [command for command, _ in shell_calls] == [
            "input keyevent 66",
            "input keyevent 61",
            "input text a",
            "input keyevent 66",
        ]

    def test_serial_reaches_every_call(self, shell_calls):
        """Text and key presses in one string all go to the same device."""
        adb.type_text("a\nb", serial="emulator-5554")

        assert {serial for _, serial in shell_calls} == {"emulator-5554"}

    def test_empty_text_sends_nothing(self, shell_calls):
        """There is nothing to type."""
        adb.type_text("")

        assert shell_calls == []

    @pytest.mark.parametrize(
        ("text", "commands"),
        [
            ("a%sb", ["input text a%", "input text sb"]),
            ("%s", ["input text %", "input text s"]),
            ("%%s", ["input text %%", "input text s"]),
            ("100%", ["input text 100%"]),
            ("50% done", ["input text 50%", "input text %sdone"]),
            ("x% y%sz", ["input text x%", "input text %sy%", "input text sz"]),
        ],
    )
    def test_literal_percent_s_is_split_across_calls(self, shell_calls, text, commands):
        """A ``%`` is kept apart from a following ``s`` or space, which would read as ``%s``."""
        adb.type_text(text)

        assert [command for command, _ in shell_calls] == commands

    def test_every_percent_and_space_combination_survives_the_device(self, shell_calls):
        """Run the commands through a model of the device's ``%s`` handling and compare.

        The model follows ``Input.sendText`` in AOSP; the cases above were also typed into a real
        emulator and read back unchanged.
        """
        for length in range(1, 6):
            for chars in itertools.product("%s a", repeat=length):
                text = "".join(chars)
                shell_calls.clear()

                adb.type_text(text)

                assert "".join(_device_types(command) for command, _ in shell_calls) == text

    @pytest.mark.parametrize(
        ("text", "typed"),
        [
            ("é", "\u0301e"),
            ("È", "\u0300E"),
            ("â", "\u0302a"),
            ("ñ", "\u0303n"),
            ("ü", "\u0308u"),
            ("ÿ", "\u0308y"),
            ("Ÿ", "\u0308Y"),
            ("ǹ", "\u0300n"),
            ("ẽ", "\u0303e"),
        ],
    )
    def test_accented_letter_is_sent_as_dead_key_then_letter(self, shell_calls, text, typed):
        """The device composes ``é`` from the accent followed by the letter, not the other way."""
        adb.type_text(text)

        assert shell_calls == [(f"input text '{typed}'", None)]

    def test_accents_mix_with_ascii(self, shell_calls):
        """Accented letters inside ordinary text are rewritten in place."""
        adb.type_text("café naïve")

        assert shell_calls == [("input text 'caf\u0301e%sna\u0308ive'", None)]

    def test_decomposed_input_is_the_same_as_precomposed(self, shell_calls):
        """``e`` followed by U+0301 types the same as ``é``."""
        adb.type_text("cafe\u0301")
        decomposed = list(shell_calls)
        shell_calls.clear()
        adb.type_text("café")

        assert decomposed == shell_calls

    def test_accents_survive_the_percent_s_handling(self, shell_calls):
        """A ``%`` before a space or an accented letter still reaches the device as typed."""
        adb.type_text("50% é, 100%s ü")

        typed = "".join(_device_types(command) for command, _ in shell_calls)
        assert typed == "50% \u0301e, 100%s \u0308u"

    @pytest.mark.parametrize(
        "text",
        [
            "日本",  # CJK
            "emoji 😀",
            "ç",  # cedilla is not a dead key
            "ß",
            "å",  # ring above is not a dead key
            "ø",
            "æ",
            "ǘ",  # two accents on one letter
            "\u0301",  # a lone accent
            "ok\n日本",
        ],
    )
    def test_text_only_the_keyboard_app_can_type_is_refused_without_it(
        self, shell_calls, no_keyboard, text
    ):
        """With no ADBKeyboard installed, the error says what to install; nothing is sent."""
        with pytest.raises(ValueError, match="cannot type") as info:
            adb.type_text(text)

        assert "ADBKeyboard" in str(info.value) and adb.KEYBOARD_URL in str(info.value)
        assert shell_calls == []
        assert no_keyboard == ["pm list packages com.android.adbkeyboard"]

    @pytest.mark.parametrize("text", ["bell\x07", "nul\x00", "lone\rcr", "esc\x1b", "del\x7f"])
    def test_control_characters_are_refused_whatever_is_installed(
        self, shell_calls, no_keyboard, text
    ):
        """Nothing can type a control character, so the device is not even asked."""
        with pytest.raises(ValueError, match="control characters"):
            adb.type_text(text)

        assert shell_calls == [] and no_keyboard == []

    def test_control_characters_are_refused_among_otherwise_unicode_text(self, no_keyboard):
        """A bell hidden in Japanese text still stops it."""
        with pytest.raises(ValueError, match="control characters"):
            adb.type_text("日本\x07語")

        assert no_keyboard == []

    def test_lone_surrogates_are_refused(self, no_keyboard):
        """A lone surrogate cannot be encoded to send, so it is refused up front."""
        with pytest.raises(ValueError, match="control characters"):
            adb.type_text("a\ud800b")

    def test_ordinary_text_never_asks_about_the_keyboard(self, shell_calls, no_keyboard):
        """The extra check costs nothing for text ``input text`` can type."""
        adb.type_text("hello café")

        assert no_keyboard == []

    def test_check_typeable_accepts_ordinary_text_without_asking(self, no_keyboard):
        """Typeable text passes with no device call at all."""
        adb.check_typeable("hello café\nnext\tline")

        assert no_keyboard == []

    def test_check_typeable_refuses_like_type_text(self, no_keyboard):
        """It raises what type_text would, so a caller can check first."""
        with pytest.raises(ValueError, match="ADBKeyboard"):
            adb.check_typeable("日本", serial="emulator-5554")

        assert no_keyboard == ["pm list packages com.android.adbkeyboard"]

    def test_check_typeable_accepts_unicode_when_the_keyboard_is_installed(self, monkeypatch):
        """With the app installed, Unicode text is acceptable."""
        monkeypatch.setattr(keyboard, "shell", lambda *a, **k: "package:com.android.adbkeyboard\n")

        adb.check_typeable("日本")

    def test_error_names_every_untypeable_character_once(self, shell_calls):
        """The message lists each character that is the problem, so it can be fixed."""
        with pytest.raises(ValueError) as info:
            adb.type_text("日本 ça 日")

        message = str(info.value)
        assert "'日'" in message and "'本'" in message and "'ç'" in message
        assert message.count("'日'") == 1
        assert "'a'" not in message


@pytest.mark.unit
class TestClearText:
    """Tests for clear_text."""

    def test_selects_all_then_deletes(self, shell_calls):
        """Ctrl+A then Delete empties a field of any length, wherever the caret is."""
        adb.clear_text(serial="emulator-5554")

        assert shell_calls == [
            ("input keycombination 113 29 2>&1", "emulator-5554"),
            ("input keyevent 67", "emulator-5554"),
        ]

    def test_without_serial(self, shell_calls):
        """No serial means the only attached device."""
        adb.clear_text()

        assert [serial for _, serial in shell_calls] == [None, None]

    def test_old_devices_fall_back_to_repeated_deletes(self, monkeypatch):
        """Before Android 12 ``input`` answers "Unknown command"; clear by deleting both ways.

        It writes that to stderr and exits 0, and ``shell`` returns only stdout, so the answer
        is seen only when the command merges stderr into stdout itself.
        """
        calls = []

        def old_device(command, *, serial=None, timeout=30):
            calls.append(command)
            if "keycombination" in command and command.endswith(" 2>&1"):
                return "Error: Unknown command: keycombination\n"
            return ""

        monkeypatch.setattr(input, "shell", old_device)

        adb.clear_text()

        assert calls[0] == "input keycombination 113 29 2>&1"
        keys = calls[1].removeprefix("input keyevent ").split()
        assert keys == ["67", "112"] * 200
        assert len(calls) == 2

    def test_a_supported_device_never_takes_the_fallback(self, shell_calls):
        """Only one short keycombination and one Delete are sent."""
        adb.clear_text()

        assert len(shell_calls) == 2
        assert all(len(command) < 40 for command, _ in shell_calls)


@pytest.mark.unit
class TestShell:
    """Tests for shell."""

    def test_runs_one_command_through_adb_shell(self, monkeypatch):
        """The command goes to ``adb shell`` as a single argument, with the serial."""
        seen = {}

        def fake_run(*args, **kwargs):
            seen["args"], seen["kwargs"] = args, kwargs
            return "out"

        monkeypatch.setattr(core, "run", fake_run)

        assert adb.shell("ls -l /sdcard", serial="emulator-5554", timeout=5) == "out"
        assert seen["args"] == ("shell", "ls -l /sdcard")
        assert seen["kwargs"] == {"serial": "emulator-5554", "timeout": 5}


@pytest.mark.unit
class TestScreencap:
    """Tests for screencap."""

    def test_uses_exec_out_and_returns_bytes(self, monkeypatch):
        """``exec-out`` keeps the PNG intact; the bytes come back untouched."""
        seen = {}
        png = b"\x89PNG\r\n\x1a\n\x00\xff"

        def fake_run_bytes(*args, **kwargs):
            seen["args"], seen["kwargs"] = args, kwargs
            return png

        monkeypatch.setattr(core, "run_bytes", fake_run_bytes)

        assert adb.screencap(serial="emulator-5554") == png
        assert seen["args"] == ("exec-out", "screencap", "-p")
        assert seen["kwargs"]["serial"] == "emulator-5554"

    def test_drops_multiple_displays_warning(self, monkeypatch):
        """Foldables print a warning line before the PNG; only the PNG comes back."""
        png = b"\x89PNG\r\n\x1a\n\x00\xff"
        warning = b"[Warning] Multiple displays were found, but no display id was specified!\n"
        monkeypatch.setattr(core, "run_bytes", lambda *args, **kwargs: warning + png)

        assert adb.screencap(serial="emulator-5554") == png
