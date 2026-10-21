"""Tests for connecting over the network and the notification shade. ``run`` is replaced."""

import pytest

import android_mcp.adb as adb
from android_mcp.adb import core


@pytest.fixture
def adb_says(monkeypatch):
    """Return a function that sets what adb prints per command; records every call."""
    calls = []
    outputs = {}

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        result = outputs.get(args[:2], outputs.get(args[:1], ""))
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(core, "run", fake_run)

    def say(command, output):
        outputs[tuple(command)] = output

    say.calls = calls
    return say


@pytest.mark.unit
class TestConnect:
    """Tests for connect."""

    @pytest.mark.parametrize(
        "output",
        [
            "connected to 192.168.1.3:5555",
            "already connected to 192.168.1.3:5555\n",
            "Connected to 192.168.1.3:5555",
        ],
    )
    def test_success_messages(self, adb_says, output):
        """adb says it connected, or already had."""
        adb_says(["connect"], output)

        adb.connect("192.168.1.3:5555")

    @pytest.mark.parametrize(
        "output",
        [
            "cannot connect to 127.0.0.1:1: No connection could be made (10061)",
            "cannot resolve host 'nope' and port 5555: No such host is known. (11001)",
            "failed to connect to '10.0.0.9:5555': Connection timed out",
            "",
        ],
    )
    def test_failure_messages_raise_even_though_adb_exits_zero(self, adb_says, output):
        """adb prints a failure on stdout and exits 0, so the text decides."""
        adb_says(["connect"], output)

        with pytest.raises(adb.AdbError) as info:
            adb.connect("10.0.0.9")

        assert output.strip() in str(info.value) or not output

    def test_asks_adb_to_connect_to_that_address(self, adb_says):
        """The address is passed through as given, with the timeout."""
        adb_says(["connect"], "connected to 10.0.0.9:5555")

        adb.connect("10.0.0.9:5555", timeout=3)

        assert adb_says.calls == [(("connect", "10.0.0.9:5555"), {"timeout": 3})]

    def test_command_failure_propagates(self, monkeypatch):
        """If the adb command itself fails, that error reaches the caller."""

        def failing(*args, **kwargs):
            raise adb.AdbCommandError(["adb", "connect"], None, "no result after 15s")

        monkeypatch.setattr(core, "run", failing)

        with pytest.raises(adb.AdbCommandError):
            adb.connect("10.0.0.9")


MDNS = (
    "List of discovered mdns services\n"
    "adb-R5CT30ABCDE-xYz1Qa\t_adb-tls-connect._tcp.\t192.168.1.20:41233\n"
    "adb-R5CT30ABCDE-xYz1Qa\t_adb-tls-pairing._tcp.\t192.168.1.20:37001\n"
    "adb-RF8M12345-AbC9Zz\t_adb-tls-connect._tcp.\t192.168.1.21:39211\n"
)


@pytest.mark.unit
class TestConnectMdnsPeers:
    """Tests for connect_mdns_peers."""

    def test_connects_to_each_advertised_device_but_not_pairing_services(self, adb_says):
        """Only ``_adb-tls-connect`` entries are connected, not ``_adb-tls-pairing``."""
        adb_says(["mdns", "services"], MDNS)
        adb_says(["connect"], "connected to somewhere")

        connected = adb.connect_mdns_peers()

        assert connected == ["192.168.1.20:41233", "192.168.1.21:39211"]
        addresses = [args[1] for args, _ in adb_says.calls if args[0] == "connect"]
        assert addresses == ["192.168.1.20:41233", "192.168.1.21:39211"]

    def test_nothing_advertised(self, adb_says):
        """Only the header means nothing to connect."""
        adb_says(["mdns", "services"], "List of discovered mdns services\n")

        assert adb.connect_mdns_peers() == []

    def test_a_peer_that_refuses_is_skipped(self, adb_says):
        """A failed connect does not stop the others, and is not reported as connected."""
        adb_says(["mdns", "services"], MDNS)
        adb_says(["connect"], "failed to connect to 'x'")

        assert adb.connect_mdns_peers() == []
        assert sum(1 for args, _ in adb_says.calls if args[0] == "connect") == 2

    def test_mdns_being_unavailable_is_not_an_error(self, monkeypatch):
        """An adb without mDNS support gives an empty result, not an exception."""

        def no_mdns(*args, **kwargs):
            raise adb.AdbCommandError(["adb", "mdns", "services"], 1, "unknown command")

        monkeypatch.setattr(core, "run", no_mdns)

        assert adb.connect_mdns_peers() == []

    def test_lines_that_are_not_services_are_ignored(self, adb_says):
        """Blank lines and short lines do not break parsing."""
        adb_says(["mdns", "services"], "\n\nsomething odd\n  \n")

        assert adb.connect_mdns_peers() == []


@pytest.mark.unit
class TestExpandNotifications:
    """Tests for expand_notifications."""

    def test_runs_the_statusbar_command_on_the_device(self, monkeypatch):
        """The shade is opened with ``cmd statusbar expand-notifications``."""
        seen = []
        monkeypatch.setattr(
            core,
            "shell",
            lambda command, *, serial=None, timeout=30: seen.append((command, serial)),
        )

        adb.expand_notifications(serial="emulator-5554")

        assert seen == [("cmd statusbar expand-notifications", "emulator-5554")]
