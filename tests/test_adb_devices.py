"""Tests for listing devices. ``run`` is replaced with canned ``adb devices -l`` output."""

import pytest

import android_mcp.adb as adb
from android_mcp.adb import core

EMULATOR = (
    "emulator-5554          device product:sdk_gphone64_x86_64 model:sdk_gphone64_x86_64 "
    "device:emu64xa transport_id:1"
)
PHONE = (
    "R5CT30ABCDE            device usb:1-2 product:beyond1 model:SM_G973F "
    "device:beyond1 transport_id:2"
)


def _output(*lines: str) -> str:
    return "\n".join(["List of devices attached", *lines, ""])


@pytest.fixture
def adb_output(monkeypatch):
    """Return a function that sets what ``adb devices -l`` prints and records how it was called."""
    calls = []

    def set_output(text: str):
        def fake_run(*args, **kwargs):
            calls.append((args, kwargs))
            return text

        monkeypatch.setattr(core, "run", fake_run)
        return calls

    return set_output


@pytest.mark.unit
class TestListDevices:
    """Tests for list_devices."""

    def test_parses_serial_state_and_model(self, adb_output):
        """Each line becomes a Device with its serial, state and model."""
        adb_output(_output(EMULATOR, PHONE))

        assert adb.list_devices() == [
            adb.Device("emulator-5554", adb.DeviceState.DEVICE, "sdk_gphone64_x86_64"),
            adb.Device("R5CT30ABCDE", adb.DeviceState.DEVICE, "SM_G973F"),
        ]

    def test_asks_adb_for_the_long_listing(self, adb_output):
        """The model is only in ``adb devices -l``, so that is what gets run."""
        calls = adb_output(_output())

        adb.list_devices()

        assert calls == [(("devices", "-l"), {})]

    def test_no_devices(self, adb_output):
        """A header with nothing under it is an empty list."""
        adb_output(_output())

        assert adb.list_devices() == []

    def test_daemon_notices_are_skipped(self, adb_output):
        """The notices adb prints while starting its server are not devices."""
        adb_output(
            "* daemon not running; starting now at tcp:5037\n"
            "* daemon started successfully\n" + _output(EMULATOR)
        )

        assert [device.serial for device in adb.list_devices()] == ["emulator-5554"]

    def test_model_is_none_when_not_reported(self, adb_output):
        """Plain ``adb devices`` style lines have no model."""
        adb_output(_output("emulator-5554\tdevice"))

        assert adb.list_devices() == [adb.Device("emulator-5554", adb.DeviceState.DEVICE, None)]

    def test_wifi_serial(self, adb_output):
        """A ``host:port`` serial is kept whole."""
        adb_output(_output("192.168.1.3:5555     device product:x model:Pixel_8 device:y"))

        assert adb.list_devices()[0].serial == "192.168.1.3:5555"

    def test_states_other_than_ready_are_listed(self, adb_output):
        """Devices that are not ready are returned, with their state, so callers can explain why."""
        adb_output(_output("AAA unauthorized usb:1-1", "BBB offline"))

        assert [device.state for device in adb.list_devices()] == [
            adb.DeviceState.UNAUTHORIZED,
            adb.DeviceState.OFFLINE,
        ]

    def test_failure_propagates(self, monkeypatch):
        """If ``adb devices`` fails, the error reaches the caller."""

        def failing_run(*args, **kwargs):
            raise adb.AdbCommandError(["adb", "devices", "-l"], 1, "boom")

        monkeypatch.setattr(core, "run", failing_run)

        with pytest.raises(adb.AdbCommandError):
            adb.list_devices()


@pytest.mark.unit
class TestDeviceState:
    """Tests for DeviceState."""

    @pytest.mark.parametrize("text", ["device", "offline", "unauthorized", "recovery"])
    def test_known_states(self, text):
        """The words adb prints map to members of the same name."""
        assert adb.DeviceState(text).value == text

    @pytest.mark.parametrize("text", ["no", "something-new", ""])
    def test_unrecognised_state_is_unknown(self, text):
        """A state this code has not heard of, such as ``no permissions (...)``, is UNKNOWN."""
        assert adb.DeviceState(text) is adb.DeviceState.UNKNOWN
