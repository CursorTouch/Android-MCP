"""Tests for dump_hierarchy. ``run`` is replaced with what ``uiautomator dump`` printed."""

import pytest

import android_mcp.adb as adb
from android_mcp.adb import core

XML = (
    "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
    '<hierarchy rotation="0"><node/></hierarchy>'
)
NOTICE = "UI hierchary dumped to: /dev/tty"  # sic: that is how uiautomator spells it


@pytest.fixture
def printed(monkeypatch):
    """Return a function that sets what the dump command prints and records how it was run."""
    calls = []

    def set_output(text):
        def fake_run(*args, **kwargs):
            calls.append((args, kwargs))
            return text

        monkeypatch.setattr(core, "run", fake_run)
        return calls

    return set_output


@pytest.mark.unit
class TestDumpHierarchy:
    """Tests for dump_hierarchy."""

    def test_returns_the_xml_without_the_trailing_notice(self, printed):
        """uiautomator's "dumped to" line is not part of the document."""
        printed(XML + NOTICE + "\n")

        assert adb.dump_hierarchy() == XML

    def test_dumps_to_stdout_through_exec_out(self, printed):
        """Writing to /dev/tty returns the XML directly and leaves nothing on the device."""
        calls = printed(XML + NOTICE)

        adb.dump_hierarchy(serial="emulator-5554", timeout=5)

        assert calls == [
            (
                ("exec-out", "uiautomator", "dump", "/dev/tty"),
                {"serial": "emulator-5554", "timeout": 5},
            )
        ]

    def test_ignores_anything_printed_before_the_xml(self, printed):
        """A warning ahead of the document does not matter."""
        printed("WARNING: something\n" + XML + NOTICE)

        assert adb.dump_hierarchy() == XML

    def test_a_hierarchy_with_no_windows_still_counts(self, printed):
        """A self-closing root is a valid, empty document."""
        empty = "<?xml version='1.0' ?><hierarchy rotation=\"0\" />"
        printed(empty + NOTICE)

        assert adb.dump_hierarchy() == empty

    @pytest.mark.parametrize(
        "output",
        [
            "ERROR: null root node returned by UiTestAutomationBridge.",
            "ERROR: something new in a later Android release",
            "",
        ],
    )
    def test_an_error_message_raises_with_the_text(self, printed, output):
        """When uiautomator exits 0 but prints no XML, that is a failure, not an empty screen."""
        printed(output)

        with pytest.raises(adb.AdbError, match="no hierarchy") as info:
            adb.dump_hierarchy()

        assert output.strip() in str(info.value)
        assert not isinstance(info.value, adb.ScreenNotIdleError)

    def test_a_screen_that_never_idles_raises_its_own_error(self, printed):
        """uiautomator's "could not get idle state" is a ScreenNotIdleError, and says why."""
        printed("ERROR: could not get idle state.\n")

        with pytest.raises(adb.ScreenNotIdleError, match="never went idle") as info:
            adb.dump_hierarchy()

        assert "video" in str(info.value) and "timer" in str(info.value)

    def test_not_idle_is_still_an_adb_error(self, printed):
        """Callers that catch AdbError for any dump failure still catch it."""
        printed("ERROR: could not get idle state.")

        with pytest.raises(adb.AdbError):
            adb.dump_hierarchy()

    def test_not_idle_is_not_retried(self, printed):
        """A busy screen stays busy, and each attempt costs ten seconds, so the dump runs once."""
        calls = printed("ERROR: could not get idle state.")

        with pytest.raises(adb.ScreenNotIdleError):
            adb.dump_hierarchy()

        assert len(calls) == 1

    def test_idle_notice_inside_real_xml_is_not_an_error(self, printed):
        """A node whose text mentions the phrase does not turn a good dump into a failure."""
        xml = XML.replace("<node/>", '<node text="could not get idle state"/>')
        printed(xml + NOTICE)

        assert adb.dump_hierarchy() == xml

    def test_command_failure_propagates(self, monkeypatch):
        """If the command itself fails, the adb error reaches the caller."""

        def failing_run(*args, **kwargs):
            raise adb.AdbCommandError(["adb", "exec-out"], 1, "device offline")

        monkeypatch.setattr(core, "run", failing_run)

        with pytest.raises(adb.AdbCommandError):
            adb.dump_hierarchy()
