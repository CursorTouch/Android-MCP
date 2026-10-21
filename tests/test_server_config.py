"""Tests for choosing the device from the command line and the environment, and the CLI."""

import pytest
from click.testing import CliRunner

from android_mcp import __main__ as cli
from android_mcp.server import DevicePreference, resolve_preference
from android_mcp.server.config import screenshot_quantized


def _resolve(env=None, **options):
    return resolve_preference(env=env or {}, **options)


@pytest.mark.unit
class TestResolvePreference:
    """Tests for resolve_preference."""

    def test_defaults_to_auto_detect(self):
        """With nothing set, pick among what is attached."""
        assert _resolve() == DevicePreference("auto", None, "auto-detect")

    def test_device_option(self):
        """--device names the serial."""
        assert _resolve(device="R5CT30ABCDE") == DevicePreference("auto", "R5CT30ABCDE", "--device")

    def test_device_option_is_stripped(self):
        """Padding around the serial is dropped."""
        assert _resolve(device="  emulator-5554 ").serial == "emulator-5554"

    def test_device_with_connection(self):
        """--connection narrows how a named device is treated."""
        preference = _resolve(device="192.168.1.3", connection="wifi")

        assert (preference.connection, preference.serial) == ("wifi", "192.168.1.3")

    def test_wifi_option_adds_the_default_port(self):
        """--wifi HOST becomes host:5555."""
        assert _resolve(wifi="192.168.1.3") == DevicePreference(
            "wifi", "192.168.1.3:5555", "--wifi"
        )

    def test_wifi_option_keeps_a_port(self):
        """An explicit port is kept."""
        assert _resolve(wifi="192.168.1.3:5557").serial == "192.168.1.3:5557"

    def test_wifi_flag_without_a_host_uses_the_environment(self):
        """--wifi on its own falls back to ANDROID_MCP_HOST."""
        preference = _resolve(wifi="", env={"ANDROID_MCP_HOST": "10.0.0.9"})

        assert (preference.connection, preference.serial) == ("wifi", "10.0.0.9:5555")

    def test_wifi_flag_without_any_host(self):
        """With no host anywhere the connection is wifi but no device is named."""
        preference = _resolve(wifi="")

        assert (preference.connection, preference.serial) == ("wifi", None)

    def test_usb_option(self):
        """--usb alone means any USB device; with a value, that serial."""
        assert _resolve(usb="") == DevicePreference("usb", None, "--usb")
        assert _resolve(usb="RFCW70CZWKV") == DevicePreference("usb", "RFCW70CZWKV", "--usb")

    def test_wifi_beats_usb_beats_device(self):
        """Among the options the order is wifi, usb, device."""
        assert _resolve(wifi="1.2.3.4", usb="X", device="Y").source == "--wifi"
        assert _resolve(usb="X", device="Y").source == "--usb"

    def test_environment_device(self):
        """ANDROID_MCP_DEVICE names the serial."""
        preference = _resolve(env={"ANDROID_MCP_DEVICE": "emulator-5554"})

        assert preference == DevicePreference("auto", "emulator-5554", "ANDROID_MCP_DEVICE")

    def test_environment_connection_alone(self):
        """ANDROID_MCP_CONNECTION=usb picks by connection type."""
        preference = _resolve(env={"ANDROID_MCP_CONNECTION": "USB"})

        assert (preference.connection, preference.serial) == ("usb", None)

    def test_environment_host_implies_wifi(self):
        """ANDROID_MCP_HOST alone is enough to ask for Wi-Fi."""
        preference = _resolve(env={"ANDROID_MCP_HOST": "10.0.0.9"})

        assert preference == DevicePreference(
            "wifi", "10.0.0.9:5555", "ANDROID_MCP_CONNECTION/ANDROID_MCP_HOST"
        )

    def test_environment_wifi_without_host(self):
        """ANDROID_MCP_CONNECTION=wifi with no host names no device."""
        preference = _resolve(env={"ANDROID_MCP_CONNECTION": "wifi"})

        assert (preference.connection, preference.serial) == ("wifi", None)

    def test_command_line_beats_the_environment(self):
        """An option wins over a variable."""
        env = {"ANDROID_MCP_DEVICE": "from-env", "ANDROID_MCP_HOST": "10.0.0.9"}

        assert _resolve(device="from-cli", env=env).serial == "from-cli"
        assert _resolve(usb="", env=env).connection == "usb"

    def test_connection_option_beats_the_environments_connection(self):
        """--connection wins over ANDROID_MCP_CONNECTION."""
        preference = _resolve(connection="usb", env={"ANDROID_MCP_CONNECTION": "wifi"})

        assert preference.connection == "usb"

    def test_blank_variables_count_as_unset(self):
        """MCP hosts pass blanks for options left empty."""
        env = {
            "ANDROID_MCP_DEVICE": "  ",
            "ANDROID_MCP_CONNECTION": "",
            "ANDROID_MCP_HOST": " ",
        }

        assert _resolve(env=env) == DevicePreference()

    @pytest.mark.parametrize("bad", ["bluetooth", "wi-fi"])
    def test_invalid_connection_from_the_environment(self, bad):
        """The error names the variable and the choices."""
        with pytest.raises(ValueError, match="ANDROID_MCP_CONNECTION") as info:
            _resolve(env={"ANDROID_MCP_CONNECTION": bad})

        assert "auto, usb, wifi" in str(info.value)

    def test_invalid_connection_from_the_option(self):
        """The error names the option."""
        with pytest.raises(ValueError, match="--connection"):
            _resolve(connection="bluetooth")


@pytest.mark.unit
class TestScreenshotQuantized:
    """Tests for screenshot_quantized."""

    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", " on "])
    def test_enabled(self, value):
        """The usual spellings of yes."""
        assert screenshot_quantized({"SCREENSHOT_QUANTIZED": value}) is True

    @pytest.mark.parametrize("value", ["", "0", "false", "no", "maybe"])
    def test_disabled(self, value):
        """Anything else is off."""
        assert screenshot_quantized({"SCREENSHOT_QUANTIZED": value}) is False

    def test_unset(self):
        """Off by default."""
        assert screenshot_quantized({}) is False


@pytest.fixture
def started(monkeypatch):
    """Replace build_server so the CLI can be run without starting a server."""
    seen = {}

    class FakeServer:
        def run(self):
            seen["ran"] = True

    def fake_build(preference):
        seen["preference"] = preference
        return FakeServer()

    monkeypatch.setattr(cli, "build_server", fake_build)
    for name in ("ANDROID_MCP_DEVICE", "ANDROID_MCP_CONNECTION", "ANDROID_MCP_HOST"):
        monkeypatch.delenv(name, raising=False)
    return seen


@pytest.mark.unit
class TestCommandLine:
    """Tests for the android-mcp-beta command."""

    def test_runs_the_server_with_the_default_preference(self, started):
        """No options starts the server on auto-detect."""
        result = CliRunner().invoke(cli.main, [])

        assert result.exit_code == 0
        assert started == {"preference": DevicePreference(), "ran": True}

    def test_passes_options_through(self, started):
        """--device reaches the preference."""
        CliRunner().invoke(cli.main, ["--device", "emulator-5554"])

        assert started["preference"].serial == "emulator-5554"

    def test_wifi_flag_with_a_value(self, started):
        """--wifi HOST."""
        CliRunner().invoke(cli.main, ["--wifi", "192.168.1.3"])

        assert started["preference"] == DevicePreference("wifi", "192.168.1.3:5555", "--wifi")

    def test_wifi_flag_without_a_value(self, started, monkeypatch):
        """--wifi on its own reads ANDROID_MCP_HOST."""
        monkeypatch.setenv("ANDROID_MCP_HOST", "10.0.0.9")

        CliRunner().invoke(cli.main, ["--wifi"])

        assert started["preference"].serial == "10.0.0.9:5555"

    def test_usb_flag_with_and_without_a_value(self, started):
        """--usb and --usb SERIAL."""
        CliRunner().invoke(cli.main, ["--usb"])
        assert started["preference"] == DevicePreference("usb", None, "--usb")

        CliRunner().invoke(cli.main, ["--usb", "RFCW70CZWKV"])
        assert started["preference"].serial == "RFCW70CZWKV"

    def test_transport_is_an_alias_for_connection(self, started):
        """The original server accepted --transport for the same thing."""
        CliRunner().invoke(cli.main, ["--transport", "usb"])

        assert started["preference"].connection == "usb"

    def test_environment_is_read(self, started, monkeypatch):
        """ANDROID_MCP_DEVICE sets the device."""
        monkeypatch.setenv("ANDROID_MCP_DEVICE", "from-env")

        CliRunner().invoke(cli.main, [])

        assert started["preference"] == DevicePreference("auto", "from-env", "ANDROID_MCP_DEVICE")

    def test_invalid_connection_is_a_usage_error(self, started):
        """click rejects a bad choice before anything starts."""
        result = CliRunner().invoke(cli.main, ["--connection", "bluetooth"])

        assert result.exit_code == 2
        assert "bluetooth" in result.output
        assert "ran" not in started

    def test_invalid_environment_connection_is_a_usage_error(self, started, monkeypatch):
        """A bad variable gives a clean message, not a traceback."""
        monkeypatch.setenv("ANDROID_MCP_CONNECTION", "bluetooth")

        result = CliRunner().invoke(cli.main, [])

        assert result.exit_code == 2
        assert "ANDROID_MCP_CONNECTION" in result.output
        assert "ran" not in started

    def test_help_lists_the_options(self):
        """--help documents every option and the environment variables."""
        result = CliRunner().invoke(cli.main, ["--help"])

        assert result.exit_code == 0
        for text in ("--device", "--connection", "--wifi", "--usb", "ANDROID_MCP_DEVICE"):
            assert text in result.output
