"""Tests for the mobile service. The adb layer is replaced, so no device is needed."""

import io
import pathlib
import threading

import pytest
from PIL import Image

import android_mcp.adb as adb
from android_mcp.adb import keyboard
from android_mcp.mobile import (
    ElementNotFoundError,
    Mobile,
    MobileError,
    MobileState,
    format_elements,
    normalize_wifi_address,
    pick_device,
)
from android_mcp.mobile import service as mobile_service
from android_mcp.tree import Bounds, Element

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
EMULATOR = adb.Device("emulator-5554", adb.DeviceState.DEVICE, "sdk_gphone64")
PHONE = adb.Device("R5CT30ABCDE", adb.DeviceState.DEVICE, "SM_G973F")
WIFI = adb.Device("192.168.1.3:5555", adb.DeviceState.DEVICE, "Pixel_8")


def _device(serial, state):
    return adb.Device(serial, state)


@pytest.fixture(autouse=True)
def no_keyboard(monkeypatch):
    """The device has no ADBKeyboard app: the check for it finds no package."""
    monkeypatch.setattr(keyboard, "shell", lambda command, **kwargs: "")


@pytest.fixture
def attached(monkeypatch):
    """Return a function that sets which devices adb reports.

    mDNS discovery is stubbed to find nothing, so no test reaches a real adb. The calls it gets
    are kept on ``attached.mdns_calls``.
    """
    mdns_calls = []

    def set_devices(*devices):
        monkeypatch.setattr(adb, "list_devices", lambda: list(devices))

    def no_peers():
        mdns_calls.append(1)
        return []

    monkeypatch.setattr(adb, "connect_mdns_peers", no_peers)
    set_devices.mdns_calls = mdns_calls
    return set_devices


@pytest.fixture
def mobile(attached):
    """A Mobile already connected to the emulator."""
    attached(EMULATOR)
    service = Mobile()
    service.connect()
    return service


@pytest.mark.unit
class TestPickDevice:
    """Tests for pick_device."""

    def test_no_devices(self):
        """Nothing attached, nothing picked."""
        assert pick_device([]) is None

    def test_auto_prefers_a_physical_device_over_an_emulator(self):
        """Whoever plugged a phone in did not mean the emulator, whatever order adb lists them."""
        assert pick_device([EMULATOR, PHONE]) is PHONE
        assert pick_device([PHONE, EMULATOR]) is PHONE

    def test_auto_counts_wifi_devices_as_physical(self):
        """A host:port serial is a real device over the network."""
        assert pick_device([EMULATOR, WIFI]) is WIFI

    def test_auto_falls_back_to_an_emulator(self):
        """With no physical device the emulator is used."""
        assert pick_device([EMULATOR]) is EMULATOR

    def test_devices_that_are_not_ready_are_skipped(self):
        """An offline or unauthorized phone cannot be used, so the emulator is."""
        devices = [
            _device("AAA", adb.DeviceState.UNAUTHORIZED),
            _device("BBB", adb.DeviceState.OFFLINE),
            EMULATOR,
        ]

        assert pick_device(devices) is EMULATOR

    def test_only_unready_devices_gives_none(self):
        """Nothing usable."""
        assert pick_device([_device("AAA", adb.DeviceState.OFFLINE)]) is None

    def test_wifi_takes_only_a_network_serial(self):
        """``wifi`` ignores USB devices and emulators."""
        assert pick_device([EMULATOR, PHONE, WIFI], "wifi") is WIFI
        assert pick_device([EMULATOR, PHONE], "wifi") is None

    def test_usb_takes_only_a_physical_device_without_a_colon(self):
        """``usb`` ignores emulators and network devices."""
        assert pick_device([EMULATOR, WIFI, PHONE], "usb") is PHONE
        assert pick_device([EMULATOR, WIFI], "usb") is None


@pytest.mark.unit
class TestConnect:
    """Tests for connect, disconnect and the connection state."""

    def test_starts_disconnected(self):
        """A new service has no device."""
        mobile = Mobile()

        assert mobile.is_connected is False
        assert mobile.serial is None

    def test_connects_to_a_named_device(self, attached):
        """The device asked for is the one used, even when another would be picked."""
        attached(EMULATOR, PHONE)
        mobile = Mobile()

        device = mobile.connect("emulator-5554")

        assert device == EMULATOR
        assert (mobile.serial, mobile.is_connected) == ("emulator-5554", True)

    def test_connects_to_a_picked_device(self, attached):
        """With no serial, the preferred device is chosen."""
        attached(EMULATOR, PHONE)
        mobile = Mobile()

        assert mobile.connect() == PHONE
        assert mobile.serial == "R5CT30ABCDE"

    def test_connection_type_is_passed_to_the_picker(self, attached):
        """``connection`` narrows the automatic choice."""
        attached(PHONE, WIFI)
        mobile = Mobile()

        assert mobile.connect(connection="wifi") == WIFI

    def test_unknown_serial_lists_what_is_attached(self, attached):
        """The error says which devices there are to choose from."""
        attached(EMULATOR, PHONE)

        with pytest.raises(MobileError) as info:
            Mobile().connect("nope")

        message = str(info.value)
        assert "'nope' not found" in message
        assert "emulator-5554 (device)" in message and "R5CT30ABCDE (device)" in message

    def test_unauthorized_device_says_what_to_do(self, attached):
        """The common fix for an unauthorized phone is in the message."""
        attached(_device("AAA", adb.DeviceState.UNAUTHORIZED))

        with pytest.raises(MobileError, match="unauthorized") as info:
            Mobile().connect("AAA")

        assert "USB debugging" in str(info.value)

    def test_offline_device_is_refused(self, attached):
        """A device that is attached but offline cannot be used."""
        attached(_device("AAA", adb.DeviceState.OFFLINE))

        with pytest.raises(MobileError, match="offline"):
            Mobile().connect("AAA")

    def test_nothing_attached(self, attached):
        """With no devices the message says so."""
        attached()

        with pytest.raises(MobileError, match="No ready device. No devices are attached"):
            Mobile().connect()

    def test_only_unready_devices_are_described(self, attached):
        """When nothing is ready, the ones that are not are named with their state."""
        attached(_device("AAA", adb.DeviceState.UNAUTHORIZED))

        with pytest.raises(MobileError, match=r"AAA \(unauthorized\)"):
            Mobile().connect()

    def test_no_device_of_the_requested_type(self, attached):
        """The message names the connection type that found nothing."""
        attached(EMULATOR)

        with pytest.raises(MobileError, match="No ready device over wifi"):
            Mobile().connect(connection="wifi")

    def test_a_failed_connect_keeps_the_existing_connection(self, attached):
        """Asking for a device that is not there does not drop the one already in use."""
        attached(EMULATOR)
        mobile = Mobile()
        mobile.connect()

        with pytest.raises(MobileError):
            mobile.connect("nope")

        assert mobile.serial == "emulator-5554"

    def test_disconnect(self, mobile):
        """After disconnecting there is no device."""
        mobile.disconnect()

        assert mobile.is_connected is False
        assert mobile.serial is None

    def test_adb_failure_reaches_the_caller(self, monkeypatch):
        """If adb itself fails, that error is not hidden."""

        def failing():
            raise adb.AdbNotFoundError("adb not found")

        monkeypatch.setattr(adb, "list_devices", failing)

        with pytest.raises(adb.AdbNotFoundError):
            Mobile().connect()

    def test_list_devices_reports_every_state(self, attached):
        """Listing is not filtered, so the caller can explain a device that is not ready."""
        offline = _device("AAA", adb.DeviceState.OFFLINE)
        attached(EMULATOR, offline)

        assert Mobile.list_devices() == [EMULATOR, offline]


def _screen_png(width=1080, height=2400):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def screen(monkeypatch):
    """Give adb a launcher screen to dump and photograph; record every call made to it."""
    calls = {"dump": [], "screencap": []}
    xml = (FIXTURES / "launcher.xml").read_text(encoding="utf-8")
    png = _screen_png()

    def dump(*, serial=None, timeout=30):
        calls["dump"].append(serial)
        return xml

    def screencap(*, serial=None, timeout=30):
        calls["screencap"].append(serial)
        return png

    monkeypatch.setattr(adb, "dump_hierarchy", dump)
    monkeypatch.setattr(adb, "screencap", screencap)
    calls["png"] = png
    return calls


@pytest.mark.unit
class TestGetState:
    """Tests for get_state."""

    def test_elements_only(self, mobile, screen):
        """Without vision the screen is dumped and no screenshot is taken."""
        state = mobile.get_state()

        assert len(state.elements) == 15
        assert state.elements[0].name == "At a glance Gmail Photos YouTube"
        assert state.screenshot is None
        assert state.warning is None
        assert screen["screencap"] == []

    def test_reads_the_connected_device(self, mobile, screen):
        """Both reads are aimed at the connected serial."""
        mobile.get_state(use_vision=True)

        assert screen["dump"] == ["emulator-5554"]
        assert screen["screencap"] == ["emulator-5554"]

    def test_with_vision_the_screenshot_is_annotated(self, mobile, screen):
        """The image comes back as a PNG of the same size, redrawn with the element boxes."""
        state = mobile.get_state(use_vision=True)

        image = Image.open(io.BytesIO(state.screenshot))
        assert image.size == (1080, 2400)
        assert state.screenshot != screen["png"]
        # Element 0 is the whole workspace: its box starts at the top-left corner.
        assert image.convert("RGB").getpixel((0, 1200)) != (255, 255, 255)

    def test_without_annotation_the_png_is_returned_untouched(self, mobile, screen):
        """``annotate=False`` gives the device's own bytes."""
        state = mobile.get_state(use_vision=True, annotate=False)

        assert state.screenshot == screen["png"]

    def test_quantize_makes_a_palette_image(self, mobile, screen):
        """``quantize`` reduces the screenshot to 256 colours."""
        state = mobile.get_state(use_vision=True, annotate=False, quantize=True)

        assert Image.open(io.BytesIO(state.screenshot)).mode == "P"

    def test_the_dump_and_the_screenshot_are_taken_together(self, mobile, monkeypatch):
        """Each read waits for the other to start, so they only finish if they overlap."""
        barrier = threading.Barrier(2, timeout=5)
        xml = (FIXTURES / "launcher.xml").read_text(encoding="utf-8")
        png = _screen_png()

        def dump(*, serial=None, timeout=30):
            barrier.wait()
            return xml

        def screencap(*, serial=None, timeout=30):
            barrier.wait()
            return png

        monkeypatch.setattr(adb, "dump_hierarchy", dump)
        monkeypatch.setattr(adb, "screencap", screencap)

        state = mobile.get_state(use_vision=True)

        assert len(state.elements) == 15 and state.screenshot

    def test_a_busy_screen_still_gives_a_screenshot(self, mobile, monkeypatch, screen):
        """When the dump fails because the screen never idles, the screenshot is returned alone."""

        def busy(*, serial=None, timeout=30):
            raise adb.ScreenNotIdleError("the screen never went idle")

        monkeypatch.setattr(adb, "dump_hierarchy", busy)

        state = mobile.get_state(use_vision=True, annotate=True)

        assert state.elements == []
        assert state.screenshot == screen["png"]
        assert "never went idle" in state.warning
        assert "screenshot" in state.warning and "coordinates" in state.warning

    def test_a_busy_screen_without_vision_raises(self, mobile, monkeypatch):
        """With no screenshot to fall back on there is nothing to return, so the error is raised."""

        def busy(*, serial=None, timeout=30):
            raise adb.ScreenNotIdleError("the screen never went idle")

        monkeypatch.setattr(adb, "dump_hierarchy", busy)

        with pytest.raises(adb.ScreenNotIdleError):
            mobile.get_state()

    def test_other_dump_failures_are_not_swallowed(self, mobile, monkeypatch, screen):
        """Only the busy-screen case is handled; a screen that is off still raises."""

        def off(*, serial=None, timeout=30):
            raise adb.AdbError("uiautomator dump returned no hierarchy: 'ERROR: null root node'")

        monkeypatch.setattr(adb, "dump_hierarchy", off)

        with pytest.raises(adb.AdbError, match="null root node"):
            mobile.get_state(use_vision=True)

    def test_a_failed_screenshot_raises(self, mobile, monkeypatch, screen):
        """No screenshot means the request failed."""

        def broken(*, serial=None, timeout=30):
            raise adb.AdbCommandError(["adb", "exec-out"], 1, "screencap failed")

        monkeypatch.setattr(adb, "screencap", broken)

        with pytest.raises(adb.AdbCommandError, match="screencap failed"):
            mobile.get_state(use_vision=True)

    def test_requires_a_connection(self, screen):
        """With no device connected nothing is read."""
        with pytest.raises(MobileError, match="No device connected"):
            Mobile().get_state()

        assert screen["dump"] == []


@pytest.mark.unit
class TestMobileState:
    """Tests for MobileState and format_elements."""

    @staticmethod
    def _element(
        name,
        resource_id="",
        class_name="android.widget.Button",
        box=(0, 0, 100, 40),
        tappable=True,
    ):
        return Element(name, class_name, resource_id, Bounds(*box), tappable=tappable)

    def test_no_elements(self):
        """An empty screen is said in words, not as a bare header."""
        assert format_elements([]) == "No interactive elements."

    def test_table_has_a_header_and_one_row_per_element(self):
        """Label is the index, and the tap point is the centre of the box."""
        text = format_elements(
            [
                self._element("OK", "ok_button", box=(100, 200, 300, 400)),
                self._element("Cancel", box=(0, 0, 10, 10)),
            ]
        )

        header, first, second = text.splitlines()
        assert header.split() == ["Label", "Name", "ResourceId", "Class", "Coordinates", "Tap"]
        assert first.split() == [
            "0",
            "OK",
            "ok_button",
            "android.widget.Button",
            "(200,300)",
            "yes",
        ]
        assert second.split() == ["1", "Cancel", "android.widget.Button", "(5,5)", "yes"]

    def test_the_tap_column_says_when_a_tap_would_not_reach_the_element(self):
        """A scrolling container or covered element is marked ``no``, the rest ``yes``."""
        text = format_elements(
            [self._element("List", tappable=False), self._element("Save", tappable=True)]
        )

        _, first, second = text.splitlines()
        assert first.split()[-1] == "no"
        assert second.split()[-1] == "yes"

    def test_columns_line_up(self):
        """Every column starts at the same character on every line."""
        text = format_elements(
            [self._element("A long name here", "id_one"), self._element("B", "x")]
        )

        header, first, second = text.splitlines()
        for column in ("Name", "ResourceId", "Class", "Coordinates"):
            start = header.index(column)
            assert first[start] != " " or first[start - 1] == " "
            assert second[start] != " " or second[start - 1] == " "
        assert first.index("id_one") == second.index("x") == header.index("ResourceId")

    def test_whitespace_in_a_name_is_collapsed_to_one_line(self):
        """A name with a line break does not break the table."""
        text = format_elements([self._element("Line one\n  line   two\t")])

        assert len(text.splitlines()) == 2
        assert "Line one line two" in text

    def test_no_trailing_spaces(self):
        """Lines end where their content does."""
        text = format_elements([self._element("A"), self._element("Longer name")])

        assert all(line == line.rstrip() for line in text.splitlines())

    def test_state_to_string_is_the_table(self):
        """With no warning the string is just the table."""
        state = MobileState(elements=[self._element("OK")])

        assert state.to_string() == format_elements(state.elements)

    def test_a_warning_comes_first(self):
        """The agent reads the warning before the table."""
        state = MobileState(warning="Elements unavailable.")

        assert state.to_string() == "Elements unavailable.\nNo interactive elements."


@pytest.fixture
def sent(monkeypatch):
    """Record every action sent to adb as ``(name, args, serial)``."""
    calls = []

    def recorder(name):
        def record(*args, serial=None, **kwargs):
            calls.append((name, args, serial))

        return record

    for name in ("tap", "long_press", "swipe", "drag", "press_key", "type_text"):
        monkeypatch.setattr(adb, name, recorder(name))
    return calls


@pytest.mark.unit
class TestActions:
    """Tests for the actions: each is the adb function, aimed at the connected device."""

    def test_tap(self, mobile, sent):
        """Tap goes to the connected serial."""
        mobile.tap(10, 20)

        assert sent == [("tap", (10, 20), "emulator-5554")]

    def test_long_press(self, mobile, sent):
        """Long press goes to the connected serial."""
        mobile.long_press(10, 20)

        assert sent == [("long_press", (10, 20), "emulator-5554")]

    def test_swipe(self, mobile, sent):
        """Swipe goes to the connected serial."""
        mobile.swipe(1, 2, 3, 4)

        assert sent == [("swipe", (1, 2, 3, 4), "emulator-5554")]

    def test_drag(self, mobile, sent):
        """Drag goes to the connected serial."""
        mobile.drag(1, 2, 3, 4)

        assert sent == [("drag", (1, 2, 3, 4), "emulator-5554")]

    def test_type_text(self, mobile, sent):
        """Text goes to the connected serial."""
        mobile.type_text("hello")

        assert sent == [("type_text", ("hello",), "emulator-5554")]

    @pytest.mark.parametrize(
        ("button", "key"),
        [
            ("back", adb.KeyCode.BACK),
            ("Home", adb.KeyCode.HOME),
            ("volume up", adb.KeyCode.VOLUME_UP),
            ("recent", adb.KeyCode.APP_SWITCH),
        ],
    )
    def test_press_by_name(self, mobile, sent, button, key):
        """A button name is turned into its key code."""
        mobile.press(button)

        assert sent == [("press_key", (key,), "emulator-5554")]

    def test_press_unknown_button_sends_nothing(self, mobile, sent):
        """A name that is not a key raises before anything reaches the device."""
        with pytest.raises(ValueError, match="unknown key"):
            mobile.press("nope")

        assert sent == []

    def test_actions_follow_the_connection(self, attached, sent):
        """After connecting to another device, actions go there."""
        attached(EMULATOR, PHONE)
        mobile = Mobile()
        mobile.connect("emulator-5554")
        mobile.tap(1, 1)
        mobile.connect("R5CT30ABCDE")
        mobile.tap(2, 2)

        assert [serial for _, _, serial in sent] == ["emulator-5554", "R5CT30ABCDE"]

    @pytest.mark.parametrize(
        "action",
        [
            lambda m: m.tap(1, 1),
            lambda m: m.long_press(1, 1),
            lambda m: m.swipe(1, 1, 2, 2),
            lambda m: m.drag(1, 1, 2, 2),
            lambda m: m.press("back"),
            lambda m: m.type_text("x"),
        ],
        ids=["tap", "long_press", "swipe", "drag", "press", "type_text"],
    )
    def test_every_action_requires_a_connection(self, sent, action):
        """With no device connected nothing is sent."""
        with pytest.raises(MobileError, match="No device connected"):
            action(Mobile())

        assert sent == []


class _Clock:
    """A clock that only moves when something sleeps, so waiting costs no real time."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    """Replace the service's clock and sleep with a fake one."""
    fake = _Clock()
    monkeypatch.setattr(mobile_service, "monotonic", fake.monotonic)
    monkeypatch.setattr(mobile_service, "sleep", fake.sleep)
    return fake


def _xml(*buttons):
    """A hierarchy of buttons, each ``(text, resource_id, bounds)``."""
    nodes = "".join(
        f'<node class="android.widget.Button" text="{text}" resource-id="{resource_id}" '
        f'content-desc="" clickable="true" enabled="true" bounds="{bounds}"/>'
        for text, resource_id, bounds in buttons
    )
    return f'<?xml version="1.0"?><hierarchy rotation="0">{nodes}</hierarchy>'


SAVE = ("Save", "com.app:id/save", "[100,200][300,400]")
CANCEL = ("Cancel", "com.app:id/cancel", "[400,200][600,400]")


@pytest.fixture
def screens(monkeypatch, clock):
    """Return a function that scripts successive dumps; each takes two seconds on the clock.

    Items are XML strings or exceptions to raise. The last item repeats once the script runs out.
    """
    state = {"script": [], "calls": 0}

    def fake_dump(*, serial=None, timeout=30):
        clock.now += 2
        index = min(state["calls"], len(state["script"]) - 1)
        state["calls"] += 1
        item = state["script"][index]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(adb, "dump_hierarchy", fake_dump)

    def script(*items):
        state["script"] = list(items)
        state["calls"] = 0
        return state

    return script


@pytest.mark.unit
class TestWifi:
    """Tests for normalize_wifi_address and connect_wifi."""

    @pytest.mark.parametrize(
        ("given", "address"),
        [
            ("192.168.1.3", "192.168.1.3:5555"),
            ("192.168.1.3:5557", "192.168.1.3:5557"),
            ("  phone.local ", "phone.local:5555"),
            ("", None),
            ("   ", None),
            (None, None),
        ],
    )
    def test_normalize(self, given, address):
        """Port 5555 is added when missing; blank means no address."""
        assert normalize_wifi_address(given) == address

    def test_connects_adb_then_selects_the_device(self, attached, monkeypatch):
        """adb is told to connect, and the device that appears is then the one in use."""
        attached(WIFI)
        connected = []
        monkeypatch.setattr(adb, "connect", lambda address, **kwargs: connected.append(address))
        mobile = Mobile()

        device = mobile.connect_wifi("192.168.1.3")

        assert connected == ["192.168.1.3:5555"]
        assert device == WIFI
        assert mobile.serial == "192.168.1.3:5555"

    def test_blank_host_is_refused_before_adb_is_asked(self, attached, monkeypatch):
        """Nothing is connected for a blank host."""
        monkeypatch.setattr(adb, "connect", lambda *a, **k: pytest.fail("adb was asked to connect"))

        with pytest.raises(MobileError, match="host"):
            Mobile().connect_wifi("  ")

    def test_adb_failure_reaches_the_caller_and_keeps_the_connection(self, attached, monkeypatch):
        """If adb cannot connect, the current device stays selected."""
        attached(EMULATOR)
        mobile = Mobile()
        mobile.connect()

        def refuse(address, **kwargs):
            raise adb.AdbError("cannot connect to 10.0.0.9:5555: refused")

        monkeypatch.setattr(adb, "connect", refuse)

        with pytest.raises(adb.AdbError, match="refused"):
            mobile.connect_wifi("10.0.0.9")

        assert mobile.serial == "emulator-5554"

    def test_connected_but_not_listed_is_an_error(self, attached, monkeypatch):
        """adb said yes but the device is not ready, so it cannot be selected."""
        attached(_device("10.0.0.9:5555", adb.DeviceState.OFFLINE))
        monkeypatch.setattr(adb, "connect", lambda *a, **k: None)

        with pytest.raises(MobileError, match="offline"):
            Mobile().connect_wifi("10.0.0.9")


@pytest.mark.unit
class TestMdnsDiscovery:
    """Tests for the mDNS fallback in list_devices."""

    def test_not_tried_when_devices_are_attached(self, attached):
        """A normal listing never touches mDNS."""
        attached(EMULATOR)

        assert Mobile.list_devices() == [EMULATOR]
        assert attached.mdns_calls == []

    def test_tried_when_nothing_is_attached(self, attached):
        """With no devices, mDNS is asked once."""
        attached()

        assert Mobile.list_devices() == []
        assert attached.mdns_calls == [1]

    def test_the_list_is_read_again_after_peers_connect(self, monkeypatch):
        """A device that wireless debugging just connected shows up in the result."""
        listings = iter([[], [WIFI]])
        monkeypatch.setattr(adb, "list_devices", lambda: next(listings))
        monkeypatch.setattr(adb, "connect_mdns_peers", lambda: ["192.168.1.3:5555"])

        assert Mobile.list_devices() == [WIFI]

    def test_no_second_listing_when_no_peer_connected(self, monkeypatch):
        """If mDNS connected nothing there is no point in listing again."""
        reads = []
        monkeypatch.setattr(adb, "list_devices", lambda: reads.append(1) or [])
        monkeypatch.setattr(adb, "connect_mdns_peers", lambda: [])

        Mobile.list_devices()

        assert reads == [1]


@pytest.fixture
def acted(monkeypatch, clock):
    """Record, in order, everything sent to adb and every sleep, as ``(what, details)``."""
    log = []

    def record(name):
        def call(*args, serial=None, **kwargs):
            log.append((name, args, serial))

        return call

    for name in ("tap", "clear_text", "type_text", "expand_notifications"):
        monkeypatch.setattr(adb, name, record(name))
    monkeypatch.setattr(
        mobile_service, "sleep", lambda seconds: log.append(("sleep", seconds, None))
    )
    return log


@pytest.mark.unit
class TestTypeText:
    """Tests for Mobile.type_text."""

    def test_types_into_the_focused_field(self, mobile, acted):
        """With no coordinates nothing is tapped."""
        mobile.type_text("hello")

        assert acted == [("type_text", ("hello",), "emulator-5554")]

    def test_taps_the_field_first_and_lets_it_settle(self, mobile, acted):
        """The tap comes first, then a short pause for focus, then the text."""
        mobile.type_text("hello", x=540, y=935)

        assert [entry[0] for entry in acted] == ["tap", "sleep", "type_text"]
        assert acted[0] == ("tap", (540, 935), "emulator-5554")

    def test_clear_happens_after_focusing_and_before_typing(self, mobile, acted):
        """tap, settle, clear, type."""
        mobile.type_text("hello", x=1, y=2, clear=True)

        assert [entry[0] for entry in acted] == ["tap", "sleep", "clear_text", "type_text"]

    def test_clear_without_coordinates(self, mobile, acted):
        """Clearing works on whatever has focus."""
        mobile.type_text("hello", clear=True)

        assert [entry[0] for entry in acted] == ["clear_text", "type_text"]

    def test_text_that_cannot_be_typed_changes_nothing(self, mobile, acted):
        """Untypeable text is refused before the field is tapped or emptied."""
        with pytest.raises(ValueError, match="cannot type"):
            mobile.type_text("日本", x=1, y=2, clear=True)

        assert acted == []

    @pytest.mark.parametrize(("x", "y"), [(5, None), (None, 5)])
    def test_one_coordinate_is_refused_and_changes_nothing(self, mobile, acted, x, y):
        """A half-given point is a mistake, not a request to type somewhere."""
        with pytest.raises(ValueError, match="both x and y"):
            mobile.type_text("hello", x=x, y=y, clear=True)

        assert acted == []

    def test_requires_a_connection(self, acted):
        """Nothing is sent without a device."""
        with pytest.raises(MobileError, match="No device connected"):
            Mobile().type_text("hello", x=1, y=2)

        assert acted == []


@pytest.mark.unit
class TestNotificationsAndWait:
    """Tests for open_notifications and wait."""

    def test_open_notifications(self, mobile, acted):
        """The shade is opened on the connected device."""
        mobile.open_notifications()

        assert acted == [("expand_notifications", (), "emulator-5554")]

    def test_open_notifications_requires_a_connection(self, acted):
        """Nothing is sent without a device."""
        with pytest.raises(MobileError, match="No device connected"):
            Mobile().open_notifications()

    def test_wait_sleeps_for_that_long(self, clock):
        """The pause is the requested number of seconds."""
        Mobile().wait(2.5)

        assert clock.sleeps == [2.5]

    def test_wait_needs_no_device(self, clock):
        """Waiting is not tied to a connection."""
        Mobile().wait(0)

        assert clock.sleeps == [0]

    def test_negative_wait_is_refused(self, clock):
        """You cannot wait for minus a second."""
        with pytest.raises(ValueError, match="negative"):
            Mobile().wait(-1)

        assert clock.sleeps == []


@pytest.mark.unit
class TestFindElement:
    """Tests for find_element."""

    def test_finds_by_resource_id(self, mobile, screens):
        """A short id is enough, and the element carries its name and tap point."""
        screens(_xml(SAVE, CANCEL))

        element = mobile.find_element(resource_id="cancel")

        assert (element.name, element.resource_id, element.center) == (
            "Cancel",
            "cancel",
            (500, 300),
        )

    def test_finds_by_text(self, mobile, screens):
        """Text is matched exactly."""
        screens(_xml(SAVE, CANCEL))

        assert mobile.find_element(text="Save").center == (200, 300)
        assert mobile.find_element(text="Sav") is None

    def test_index_picks_among_several_matches(self, mobile, screens):
        """Counting from zero, in screen order."""
        first = ("OK", "a", "[0,0][100,100]")
        second = ("OK", "b", "[0,200][100,300]")
        screens(_xml(first, second))

        assert mobile.find_element(text="OK").resource_id == "a"
        assert mobile.find_element(text="OK", index=1).resource_id == "b"
        assert mobile.find_element(text="OK", index=2) is None

    def test_nothing_matching_is_none(self, mobile, screens):
        """Not found is not an error."""
        screens(_xml(SAVE))

        assert mobile.find_element(text="Nope") is None

    def test_a_node_with_no_text_of_its_own_gets_its_childrens_name(self, mobile, screens):
        """Matching by id on a container names it as the tree does."""
        xml = (
            '<?xml version="1.0"?><hierarchy rotation="0">'
            '<node class="android.view.ViewGroup" text="" resource-id="x:id/row" content-desc="" '
            'enabled="true" bounds="[0,0][100,100]">'
            '<node class="android.widget.TextView" text="Title" content-desc="" '
            'enabled="true" bounds="[0,0][100,50]"/></node></hierarchy>'
        )
        screens(xml)

        assert mobile.find_element(resource_id="row").name == "Title"

    def test_no_criteria_is_refused(self, mobile, screens):
        """Matching everything is never intended."""
        screens(_xml(SAVE))

        with pytest.raises(ValueError, match="at least one"):
            mobile.find_element()

    def test_negative_index_is_refused(self, mobile, screens):
        """There is no match before the first."""
        screens(_xml(SAVE))

        with pytest.raises(ValueError, match="index"):
            mobile.find_element(text="Save", index=-1)

    def test_requires_a_connection(self, screens):
        """The screen cannot be read without a device."""
        screens(_xml(SAVE))

        with pytest.raises(MobileError, match="No device connected"):
            Mobile().find_element(text="Save")


@pytest.mark.unit
class TestWaitForElement:
    """Tests for wait_for_element."""

    def test_found_at_once_reads_once_and_does_not_sleep(self, mobile, screens, clock):
        """An element already on screen costs one read and no waiting."""
        state = screens(_xml(SAVE))

        element = mobile.wait_for_element(text="Save")

        assert element.name == "Save"
        assert state["calls"] == 1
        assert clock.sleeps == []

    def test_waits_until_it_appears(self, mobile, screens, clock):
        """It keeps looking, pausing between looks, and returns when the element shows up."""
        state = screens(_xml(CANCEL), _xml(CANCEL), _xml(CANCEL, SAVE))

        element = mobile.wait_for_element(text="Save", timeout=30)

        assert element.center == (200, 300)
        assert state["calls"] == 3
        assert clock.sleeps == [0.5, 0.5]

    def test_times_out_with_what_was_looked_for(self, mobile, screens, clock):
        """When it never appears, the error names the selector and the time waited."""
        screens(_xml(CANCEL))

        with pytest.raises(ElementNotFoundError) as info:
            mobile.wait_for_element(text="Save", class_name="android.widget.Button", timeout=5)

        message = str(info.value)
        assert "text='Save'" in message and "class_name='android.widget.Button'" in message
        assert "within 5s" in message
        assert "never went idle" not in message
        assert clock.now >= 5

    def test_the_wait_ends_close_to_the_timeout(self, mobile, screens, clock):
        """It does not keep going long after the deadline."""
        screens(_xml(CANCEL))

        with pytest.raises(ElementNotFoundError):
            mobile.wait_for_element(text="Save", timeout=10)

        assert 10 <= clock.now <= 10 + 2 + 0.5  # the deadline plus the read in progress

    def test_reads_at_least_once_even_with_no_time(self, mobile, screens):
        """A zero timeout still looks once, so an element already there is found."""
        state = screens(_xml(SAVE))

        assert mobile.wait_for_element(text="Save", timeout=0).name == "Save"
        assert state["calls"] == 1

    def test_zero_timeout_and_absent_element_fails_after_one_read(self, mobile, screens, clock):
        """No time means one look, then the error."""
        state = screens(_xml(CANCEL))

        with pytest.raises(ElementNotFoundError):
            mobile.wait_for_element(text="Save", timeout=0)

        assert state["calls"] == 1 and clock.sleeps == []

    def test_a_busy_screen_is_kept_trying_and_named_in_the_error(self, mobile, screens):
        """A screen that never idles cannot be read; that is said when it gives up."""
        busy = adb.ScreenNotIdleError("the screen never went idle")
        screens(busy)

        with pytest.raises(ElementNotFoundError, match="never went idle"):
            mobile.wait_for_element(text="Save", timeout=6)

    def test_an_element_found_after_the_screen_settles(self, mobile, screens):
        """Busy for a while, then readable and present."""
        busy = adb.ScreenNotIdleError("the screen never went idle")
        screens(busy, busy, _xml(SAVE))

        assert mobile.wait_for_element(text="Save", timeout=60).name == "Save"

    def test_the_final_error_forgets_an_earlier_busy_spell(self, mobile, screens):
        """Busy first, then readable but without the element: the error is the plain one."""
        busy = adb.ScreenNotIdleError("the screen never went idle")
        screens(busy, _xml(CANCEL))

        with pytest.raises(ElementNotFoundError) as info:
            mobile.wait_for_element(text="Save", timeout=3)

        assert "never went idle" not in str(info.value)

    def test_other_read_failures_are_not_swallowed(self, mobile, screens):
        """A screen that is off is an error now, not something to wait out."""
        screens(adb.AdbError("uiautomator dump returned no hierarchy: 'ERROR: null root node'"))

        with pytest.raises(adb.AdbError, match="null root node"):
            mobile.wait_for_element(text="Save", timeout=30)

    def test_bad_arguments_are_refused_before_the_screen_is_read(self, mobile, screens):
        """No criterion, or a negative timeout, fails at once."""
        state = screens(_xml(SAVE))

        with pytest.raises(ValueError, match="at least one"):
            mobile.wait_for_element()
        with pytest.raises(ValueError, match="timeout"):
            mobile.wait_for_element(text="Save", timeout=-1)

        assert state["calls"] == 0

    def test_requires_a_connection_before_reading(self, screens):
        """No device, no read."""
        state = screens(_xml(SAVE))

        with pytest.raises(MobileError, match="No device connected"):
            Mobile().wait_for_element(text="Save")

        assert state["calls"] == 0

    def test_index_is_passed_through(self, mobile, screens):
        """The nth match is the one waited for."""
        screens(_xml(("OK", "a", "[0,0][10,10]"), ("OK", "b", "[0,20][10,30]")))

        assert mobile.wait_for_element(text="OK", index=1).resource_id == "b"


@pytest.mark.unit
class TestClickElement:
    """Tests for click_element."""

    def test_taps_the_centre_of_the_element_found(self, mobile, screens, acted):
        """The tap goes where the element is now, and the element is returned."""
        screens(_xml(SAVE, CANCEL))

        element = mobile.click_element(resource_id="cancel")

        assert element.name == "Cancel"
        assert acted == [("tap", (500, 300), "emulator-5554")]

    def test_waits_for_the_element_before_tapping(self, mobile, screens, acted):
        """An element that appears after a moment is tapped once it is there."""
        screens(_xml(CANCEL), _xml(CANCEL, SAVE))

        mobile.click_element(text="Save", timeout=10)

        assert [entry for entry in acted if entry[0] == "tap"] == [
            ("tap", (200, 300), "emulator-5554")
        ]

    def test_nothing_is_tapped_when_it_never_appears(self, mobile, screens, acted):
        """A miss is an error, and no tap is sent."""
        screens(_xml(CANCEL))

        with pytest.raises(ElementNotFoundError):
            mobile.click_element(text="Save", timeout=2)

        assert [entry for entry in acted if entry[0] == "tap"] == []

    def test_default_timeout_is_five_seconds(self, mobile, screens, clock, acted):
        """The original tool waited five seconds before giving up."""
        screens(_xml(CANCEL))

        with pytest.raises(ElementNotFoundError, match="within 5s"):
            mobile.click_element(text="Save")
