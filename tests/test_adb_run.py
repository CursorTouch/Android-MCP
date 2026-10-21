"""Tests for running adb commands.

``find_adb`` is pointed at the Python interpreter, so these run a real subprocess with real
stdout, stderr, exit codes and timeouts, and need no device.
"""

import subprocess
import sys

import pytest

import android_mcp.adb as adb
from android_mcp.adb import core


@pytest.fixture
def python_as_adb(monkeypatch):
    """Make ``run("-c", code)`` execute ``python -c code``."""
    monkeypatch.setattr(core, "find_adb", lambda: sys.executable)


@pytest.mark.unit
class TestRun:
    """Tests for run."""

    def test_returns_stdout(self, python_as_adb):
        """The command's standard output comes back as text."""
        assert adb.run("-c", "print('hello')") == "hello\n"

    def test_nonzero_exit_raises_with_stderr(self, python_as_adb):
        """A failing command raises, carrying its exit status and what it said on stderr."""
        code = "import sys; sys.stderr.write('device offline'); sys.exit(3)"

        with pytest.raises(adb.AdbCommandError) as info:
            adb.run("-c", code)

        assert info.value.returncode == 3
        assert info.value.detail == "device offline"
        assert "device offline" in str(info.value)
        assert info.value.command[1:] == ["-c", code]

    def test_timeout_raises(self, python_as_adb):
        """A command that does not finish raises with no exit status."""
        with pytest.raises(adb.AdbCommandError) as info:
            adb.run("-c", "import time; time.sleep(30)", timeout=0.5)

        assert info.value.returncode is None
        assert "timed out" in str(info.value)

    def test_stdin_is_not_inherited(self, python_as_adb):
        """The child gets an empty stdin and so cannot read the host's MCP protocol stream."""
        assert adb.run("-c", "import sys; print(repr(sys.stdin.read()))") == "''\n"

    def test_undecodable_output_is_replaced(self, python_as_adb):
        """Bytes that are not UTF-8 do not raise; they become replacement characters."""
        code = "import sys; sys.stdout.buffer.write(b'a\\xffb')"

        assert adb.run("-c", code) == "a\ufffdb"

    def test_crlf_is_read_as_lf(self, python_as_adb):
        """Windows-style line endings in text output come back as ``\\n``."""
        code = "import sys; sys.stdout.buffer.write(b'a\\r\\nb\\r\\n')"

        assert adb.run("-c", code) == "a\nb\n"

    def test_run_bytes_returns_output_untouched(self, python_as_adb):
        """Binary output keeps every byte, including CRLF pairs and bytes that are not UTF-8."""
        code = "import sys; sys.stdout.buffer.write(b'\\x89PNG\\r\\n\\x1a\\n\\xff\\x00')"

        assert adb.run_bytes("-c", code) == b"\x89PNG\r\n\x1a\n\xff\x00"

    def test_run_bytes_raises_like_run(self, python_as_adb):
        """The bytes variant reports failures the same way."""
        with pytest.raises(adb.AdbCommandError) as info:
            adb.run_bytes("-c", "import sys; sys.stderr.write('gone'); sys.exit(2)")

        assert (info.value.returncode, info.value.detail) == (2, "gone")

    def test_serial_is_passed_as_dash_s(self, monkeypatch):
        """A serial selects the device with ``-s`` ahead of the other arguments."""
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command
            return subprocess.CompletedProcess(command, 0, stdout=b"ok", stderr=b"")

        monkeypatch.setattr(core, "find_adb", lambda: "adb")
        monkeypatch.setattr(core.subprocess, "run", fake_run)

        assert adb.run("shell", "id", serial="emulator-5554") == "ok"
        assert seen["command"] == ["adb", "-s", "emulator-5554", "shell", "id"]

    def test_no_serial_means_no_dash_s(self, monkeypatch):
        """Without a serial the command line has no ``-s``."""
        seen = {}

        def fake_run(command, **kwargs):
            seen["command"] = command
            return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

        monkeypatch.setattr(core, "find_adb", lambda: "adb")
        monkeypatch.setattr(core.subprocess, "run", fake_run)

        adb.run("devices")

        assert seen["command"] == ["adb", "devices"]

    def test_missing_adb_propagates(self, monkeypatch):
        """When adb cannot be found, run raises AdbNotFoundError rather than running anything."""

        def not_found():
            raise adb.AdbNotFoundError("adb not found")

        monkeypatch.setattr(core, "find_adb", not_found)

        with pytest.raises(adb.AdbNotFoundError):
            adb.run("devices")


@pytest.mark.unit
class TestErrors:
    """Tests for the exception hierarchy."""

    def test_every_error_is_an_adb_error(self):
        """Callers can catch AdbError for anything this layer raises."""
        assert issubclass(adb.AdbNotFoundError, adb.AdbError)
        assert issubclass(adb.AdbCommandError, adb.AdbError)
