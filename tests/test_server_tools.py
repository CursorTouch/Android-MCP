"""Tests for the MCP tools, through fastmcp's in-memory client.

The real server runs and the adb layer underneath it is replaced, so the tool names, schemas,
results and errors are what a client sees, with no device.
"""

import asyncio
import io
import pathlib
import threading
import time

import pytest
from fastmcp import Client
from PIL import Image

import android_mcp.adb as adb
from android_mcp.adb import keyboard
from android_mcp.mobile import service as mobile_service
from android_mcp.server import DevicePreference, build_server

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
EMULATOR = adb.Device("emulator-5554", adb.DeviceState.DEVICE, "sdk_gphone64")
PHONE = adb.Device("R5CT30ABCDE", adb.DeviceState.DEVICE, "SM_G973F")
WIFI = adb.Device("192.168.1.3:5555", adb.DeviceState.DEVICE, "Pixel_8")

EXPECTED_TOOLS = {
    "ListDevices",
    "ConnectDevice",
    "Device",
    "Snapshot",
    "Click",
    "ClickBySelector",
    "LongClick",
    "Type",
    "Swipe",
    "Drag",
    "Press",
    "Notification",
    "Wait",
    "WaitForElement",
}


def _png():
    buffer = io.BytesIO()
    Image.new("RGB", (1080, 2400), "white").save(buffer, format="PNG")
    return buffer.getvalue()


class FakeDevice:
    """Stands in for adb: a list of devices, a screen, and a log of what was done to it."""

    def __init__(self):
        self.devices = [EMULATOR]
        self.xml = (FIXTURES / "launcher.xml").read_text(encoding="utf-8")
        self.png = _png()
        self.log = []
        self.sleeps = []
        self.connects = []
        self.tap_delay = 0.0
        self.dump_error = None

    def calls(self, name):
        return [entry[1:] for entry in self.log if entry[0] == name]

    def install(self, monkeypatch):
        def record(name):
            def call(*args, serial=None, **kwargs):
                self.log.append((name, args, serial))

            return call

        def tap(*args, serial=None, **kwargs):
            self.log.append(("tap_start", args, serial))
            time.sleep(self.tap_delay)
            self.log.append(("tap", args, serial))

        def dump(*, serial=None, timeout=30):
            self.log.append(("dump", (), serial))
            if self.dump_error is not None:
                raise self.dump_error
            return self.xml

        def screencap(*, serial=None, timeout=30):
            self.log.append(("screencap", (), serial))
            return self.png

        def connect(address, **kwargs):
            self.connects.append(address)

        monkeypatch.setattr(adb, "list_devices", lambda: list(self.devices))
        monkeypatch.setattr(adb, "connect_mdns_peers", lambda: [])
        monkeypatch.setattr(adb, "connect", connect)
        monkeypatch.setattr(adb, "dump_hierarchy", dump)
        monkeypatch.setattr(adb, "screencap", screencap)
        monkeypatch.setattr(adb, "tap", tap)
        for name in (
            "long_press",
            "swipe",
            "drag",
            "press_key",
            "type_text",
            "clear_text",
            "expand_notifications",
        ):
            monkeypatch.setattr(adb, name, record(name))
        monkeypatch.setattr(mobile_service, "sleep", self.sleeps.append)
        # No ADBKeyboard on this device: the check for it finds no package.
        monkeypatch.setattr(keyboard, "shell", lambda command, **kwargs: "")


@pytest.fixture
def device(monkeypatch):
    """A fake device, installed under the adb layer."""
    fake = FakeDevice()
    fake.install(monkeypatch)
    return fake


@pytest.fixture
def server(device):
    """The real server, with the default preference."""
    return build_server()


async def call(server, name, arguments=None, *, ok=True):
    """Call a tool the way a client does; assert it did or did not fail; return the result."""
    async with Client(server) as client:
        result = await client.call_tool(name, arguments or {}, raise_on_error=False)
    assert result.is_error is (not ok), [getattr(c, "text", c) for c in result.content]
    return result


def text_of(result):
    return result.content[0].text


@pytest.mark.unit
class TestToolList:
    """What a client sees when it lists the tools."""

    async def test_exactly_the_original_tools(self, server):
        """The same fourteen names as the original Android-MCP."""
        async with Client(server) as client:
            tools = await client.list_tools()

        assert {tool.name for tool in tools} == EXPECTED_TOOLS

    async def test_every_tool_has_a_description_and_a_title(self, server):
        """Both are shown to the agent and the person."""
        async with Client(server) as client:
            tools = await client.list_tools()

        for tool in tools:
            assert tool.description, tool.name
            assert tool.annotations.title, tool.name

    async def test_reads_are_marked_read_only_and_actions_destructive(self, server):
        """Clients use these hints to decide what needs confirming."""
        async with Client(server) as client:
            tools = {tool.name: tool for tool in await client.list_tools()}

        for name in ("ListDevices", "Snapshot", "WaitForElement"):
            assert tools[name].annotations.read_only_hint is True, name
        for name in ("Click", "ClickBySelector", "LongClick", "Swipe", "Drag", "Type", "Press"):
            assert tools[name].annotations.read_only_hint is False, name
            assert tools[name].annotations.destructive_hint is True, name

    async def test_type_takes_optional_coordinates(self, server):
        """Only text is required; x, y and clear have defaults."""
        async with Client(server) as client:
            tools = {tool.name: tool for tool in await client.list_tools()}

        schema = tools["Type"].input_schema
        assert schema["required"] == ["text"]
        assert set(schema["properties"]) == {"text", "x", "y", "clear"}

    async def test_selector_tools_keep_the_original_argument_names(self, server):
        """Callers written against the original use resourceId and className."""
        async with Client(server) as client:
            tools = {tool.name: tool for tool in await client.list_tools()}

        for name in ("ClickBySelector", "WaitForElement"):
            properties = set(tools[name].input_schema["properties"])
            assert {"text", "resourceId", "className", "description", "timeout"} <= properties
        assert "index" in tools["ClickBySelector"].input_schema["properties"]

    async def test_instructions_tell_the_agent_where_to_start(self, server):
        """The agent is told to call Snapshot first."""
        async with Client(server) as client:
            instructions = client.instructions

        assert "Snapshot" in instructions


@pytest.mark.unit
class TestDeviceTools:
    """ListDevices, ConnectDevice and Device."""

    async def test_list_devices(self, server, device):
        """One line per device: serial, tab, state."""
        device.devices = [EMULATOR, PHONE, adb.Device("AAA", adb.DeviceState.UNAUTHORIZED)]

        result = await call(server, "ListDevices")

        assert text_of(result).splitlines() == [
            "emulator-5554\tdevice",
            "R5CT30ABCDE\tdevice",
            "AAA\tunauthorized",
        ]

    async def test_list_devices_when_there_are_none(self, server, device):
        """An empty list is said in words."""
        device.devices = []

        assert "No devices found" in text_of(await call(server, "ListDevices"))

    async def test_listing_does_not_connect(self, server, device):
        """Listing must work with nothing attached, and does not select a device."""
        await call(server, "ListDevices")
        await call(server, "Click", {"x": 1, "y": 1})

        # The click connected on its own, which listing alone had not.
        assert device.calls("tap") == [((1, 1), "emulator-5554")]

    async def test_connect_device(self, server, device):
        """A serial selects that device, and later actions go to it."""
        device.devices = [EMULATOR, PHONE]

        result = await call(server, "ConnectDevice", {"serial": "emulator-5554"})
        await call(server, "Click", {"x": 5, "y": 6})

        assert text_of(result) == "Connected to emulator-5554"
        assert device.calls("tap") == [((5, 6), "emulator-5554")]

    async def test_connect_device_over_wifi_runs_adb_connect(self, server, device):
        """A host:port is connected through adb first."""
        device.devices = [WIFI]

        result = await call(server, "ConnectDevice", {"serial": "192.168.1.3:5555"})

        assert device.connects == ["192.168.1.3:5555"]
        assert text_of(result) == "Connected to 192.168.1.3:5555"

    async def test_connect_unknown_device_is_an_error_listing_the_devices(self, server, device):
        """The agent is told what is attached."""
        result = await call(server, "ConnectDevice", {"serial": "nope"}, ok=False)

        assert "'nope' not found" in text_of(result)
        assert "emulator-5554" in text_of(result)

    async def test_device_list(self, server, device):
        """Device(list) is ListDevices."""
        assert "emulator-5554\tdevice" in text_of(await call(server, "Device", {"action": "list"}))

    async def test_device_connect_with_a_serial(self, server, device):
        """Device(connect, serial) selects it."""
        result = await call(server, "Device", {"action": "connect", "serial": "emulator-5554"})

        assert text_of(result) == "Connected to emulator-5554"

    async def test_device_connect_without_a_serial_uses_the_preference(self, device):
        """With no serial the configured device is used."""
        device.devices = [EMULATOR, PHONE]
        server = build_server(DevicePreference("auto", "R5CT30ABCDE", "--device"))

        result = await call(server, "Device", {"action": "connect"})

        assert text_of(result) == "Connected to R5CT30ABCDE"

    async def test_device_disconnect_then_the_next_action_reconnects(self, server, device):
        """Disconnecting forgets the device; the next action picks one again."""
        await call(server, "Click", {"x": 1, "y": 1})
        result = await call(server, "Device", {"action": "disconnect"})
        await call(server, "Click", {"x": 2, "y": 2})

        assert text_of(result) == "Disconnected from device."
        assert device.calls("tap") == [((1, 1), "emulator-5554"), ((2, 2), "emulator-5554")]

    async def test_device_rejects_an_unknown_action(self, server):
        """The schema only allows list, connect and disconnect."""
        async with Client(server) as client:
            with pytest.raises(Exception, match="action"):
                await client.call_tool("Device", {"action": "reboot"})


@pytest.mark.unit
class TestLazyConnection:
    """The device is connected on first use, by the preference."""

    async def test_first_action_connects_to_the_picked_device(self, server, device):
        """A physical device is preferred over an emulator."""
        device.devices = [EMULATOR, PHONE]

        await call(server, "Click", {"x": 1, "y": 2})

        assert device.calls("tap") == [((1, 2), "R5CT30ABCDE")]

    async def test_the_preference_serial_is_used(self, device):
        """--device wins over picking."""
        device.devices = [EMULATOR, PHONE]
        server = build_server(DevicePreference("auto", "emulator-5554", "--device"))

        await call(server, "Click", {"x": 1, "y": 2})

        assert device.calls("tap") == [((1, 2), "emulator-5554")]

    async def test_a_wifi_preference_runs_adb_connect(self, device):
        """--wifi HOST connects adb to the address before using it."""
        device.devices = [WIFI]
        server = build_server(DevicePreference("wifi", "192.168.1.3:5555", "--wifi"))

        await call(server, "Click", {"x": 1, "y": 2})

        assert device.connects == ["192.168.1.3:5555"]
        assert device.calls("tap") == [((1, 2), "192.168.1.3:5555")]

    async def test_no_device_is_an_error_that_says_how_to_choose_one(self, server, device):
        """The agent is told what to do, and nothing is sent."""
        device.devices = []

        result = await call(server, "Click", {"x": 1, "y": 2}, ok=False)

        message = text_of(result)
        assert "No ready device" in message and "--device" in message
        assert device.calls("tap") == []

    async def test_the_server_works_after_a_device_appears(self, server, device):
        """A failed first call does not poison the next one."""
        device.devices = []
        await call(server, "Click", {"x": 1, "y": 2}, ok=False)
        device.devices = [EMULATOR]

        await call(server, "Click", {"x": 1, "y": 2})

        assert device.calls("tap") == [((1, 2), "emulator-5554")]


@pytest.mark.unit
class TestSnapshot:
    """The Snapshot tool."""

    async def test_returns_the_element_table(self, server, device):
        """One text block with a header and a row per element."""
        result = await call(server, "Snapshot")

        assert len(result.content) == 1
        lines = text_of(result).splitlines()
        assert lines[0].split() == ["Label", "Name", "ResourceId", "Class", "Coordinates"]
        assert len(lines) == 16
        assert "Google search" in text_of(result)
        assert device.calls("screencap") == []

    async def test_with_vision_returns_a_png_after_the_table(self, server, device):
        """The screenshot is an image block of type PNG."""
        result = await call(server, "Snapshot", {"use_vision": True})

        assert [type(block).__name__ for block in result.content] == [
            "TextContent",
            "ImageContent",
        ]
        assert result.content[1].mime_type == "image/png"

    async def test_the_image_is_annotated_unless_asked_not_to(self, server, device):
        """use_annotation=false returns the device's own bytes."""
        import base64

        annotated = await call(server, "Snapshot", {"use_vision": True})
        clean = await call(server, "Snapshot", {"use_vision": True, "use_annotation": False})

        assert base64.b64decode(clean.content[1].data) == device.png
        assert base64.b64decode(annotated.content[1].data) != device.png

    async def test_quantized_screenshots_from_the_environment(self, server, device, monkeypatch):
        """SCREENSHOT_QUANTIZED=true gives a palette image."""
        import base64

        monkeypatch.setenv("SCREENSHOT_QUANTIZED", "true")

        result = await call(server, "Snapshot", {"use_vision": True, "use_annotation": False})

        image = Image.open(io.BytesIO(base64.b64decode(result.content[1].data)))
        assert image.mode == "P"

    async def test_a_busy_screen_gives_the_screenshot_and_a_warning(self, server, device):
        """The agent still gets the image, and is told why there are no elements."""
        device.dump_error = adb.ScreenNotIdleError("the screen never went idle")

        result = await call(server, "Snapshot", {"use_vision": True})

        assert "never went idle" in text_of(result)
        assert "No interactive elements." in text_of(result)
        assert result.content[1].type == "image"

    async def test_a_busy_screen_without_vision_is_an_error(self, server, device):
        """There is nothing to return."""
        device.dump_error = adb.ScreenNotIdleError("the screen never went idle")

        result = await call(server, "Snapshot", ok=False)

        assert "never went idle" in text_of(result)

    async def test_a_screen_that_is_off_is_an_error(self, server, device):
        """Other dump failures are reported, not hidden."""
        device.dump_error = adb.AdbError("uiautomator dump returned no hierarchy: 'null root node'")

        result = await call(server, "Snapshot", ok=False)

        assert "null root node" in text_of(result)


@pytest.mark.unit
class TestInputTools:
    """The tools that act on the device."""

    async def test_click(self, server, device):
        """Click taps the coordinates."""
        result = await call(server, "Click", {"x": 10, "y": 20})

        assert text_of(result) == "Clicked on (10,20)"
        assert device.calls("tap") == [((10, 20), "emulator-5554")]

    async def test_long_click(self, server, device):
        """LongClick presses and holds."""
        result = await call(server, "LongClick", {"x": 10, "y": 20})

        assert text_of(result) == "Long Clicked on (10,20)"
        assert device.calls("long_press") == [((10, 20), "emulator-5554")]

    async def test_swipe(self, server, device):
        """Swipe goes between two points."""
        result = await call(server, "Swipe", {"x1": 1, "y1": 2, "x2": 3, "y2": 4})

        assert text_of(result) == "Swiped from (1,2) to (3,4)"
        assert device.calls("swipe") == [((1, 2, 3, 4), "emulator-5554")]

    async def test_drag(self, server, device):
        """Drag picks up and drops."""
        result = await call(server, "Drag", {"x1": 1, "y1": 2, "x2": 3, "y2": 4})

        assert text_of(result) == "Dragged from (1,2) and dropped on (3,4)"
        assert device.calls("drag") == [((1, 2, 3, 4), "emulator-5554")]

    @pytest.mark.parametrize(
        ("button", "key"),
        [
            ("back", adb.KeyCode.BACK),
            ("Home", adb.KeyCode.HOME),
            ("volume up", adb.KeyCode.VOLUME_UP),
            ("recent", adb.KeyCode.APP_SWITCH),
        ],
    )
    async def test_press(self, server, device, button, key):
        """Press takes the names the original did."""
        result = await call(server, "Press", {"button": button})

        assert text_of(result) == f'Pressed the "{button}" button'
        assert device.calls("press_key") == [((key,), "emulator-5554")]

    async def test_press_unknown_button_lists_the_known_ones(self, server, device):
        """The error is for the agent to act on."""
        result = await call(server, "Press", {"button": "nope"}, ok=False)

        assert "unknown key 'nope'" in text_of(result)
        assert "volume_up" in text_of(result)
        assert device.calls("press_key") == []

    async def test_type_into_the_focused_field(self, server, device):
        """With no coordinates the text is typed where focus is."""
        result = await call(server, "Type", {"text": "hello"})

        assert text_of(result) == "Typed 'hello'"
        assert device.calls("type_text") == [(("hello",), "emulator-5554")]
        assert device.calls("tap") == []

    async def test_type_taps_the_field_first_when_given_coordinates(self, server, device):
        """x and y focus the field before typing."""
        result = await call(server, "Type", {"text": "hi", "x": 540, "y": 935})

        assert text_of(result) == "Typed 'hi' on (540,935)"
        assert [entry[0] for entry in device.log if entry[0] in ("tap", "type_text")] == [
            "tap",
            "type_text",
        ]

    async def test_type_with_clear(self, server, device):
        """clear=true empties the field before the text goes in."""
        await call(server, "Type", {"text": "hi", "clear": True})

        names = [entry[0] for entry in device.log if entry[0] in ("clear_text", "type_text")]
        assert names == ["clear_text", "type_text"]

    async def test_type_unsupported_text_is_refused_and_changes_nothing(self, server, device):
        """CJK is rejected before the field is tapped or cleared."""
        result = await call(
            server, "Type", {"text": "日本", "x": 1, "y": 2, "clear": True}, ok=False
        )

        assert "cannot type" in text_of(result)
        assert [e[0] for e in device.log if e[0] in ("tap", "clear_text", "type_text")] == []

    async def test_type_with_only_one_coordinate_is_refused(self, server, device):
        """Half a point is a mistake."""
        result = await call(server, "Type", {"text": "hi", "x": 5}, ok=False)

        assert "both x and y" in text_of(result)

    async def test_notification(self, server, device):
        """Opens the shade."""
        result = await call(server, "Notification")

        assert text_of(result) == "Accessed notification bar"
        assert device.calls("expand_notifications") == [((), "emulator-5554")]

    async def test_wait(self, server, device):
        """Pauses for that many seconds."""
        result = await call(server, "Wait", {"duration": 2})

        assert text_of(result) == "Waited for 2 seconds"
        assert device.sleeps == [2]

    async def test_wait_accepts_fractions_and_rejects_negatives(self, server, device):
        """Half a second is fine; minus one is not."""
        assert text_of(await call(server, "Wait", {"duration": 0.5})) == "Waited for 0.5 seconds"

        result = await call(server, "Wait", {"duration": -1}, ok=False)

        assert "negative" in text_of(result)

    async def test_wait_does_not_need_a_device(self, server, device):
        """Waiting works with nothing attached."""
        device.devices = []

        await call(server, "Wait", {"duration": 1})


@pytest.mark.unit
class TestSelectorTools:
    """ClickBySelector and WaitForElement, on the launcher screen."""

    async def test_click_by_resource_id(self, server, device):
        """The short id is enough; the tap goes to the element's centre."""
        result = await call(server, "ClickBySelector", {"resourceId": "search_container_hotseat"})

        assert text_of(result) == "Clicked element 'Google search' at (540,2207)"
        assert device.calls("tap") == [((540, 2207), "emulator-5554")]

    async def test_click_by_description(self, server, device):
        """Description is the content description."""
        await call(server, "ClickBySelector", {"description": "Voice search"})

        assert device.calls("tap") == [((790, 2207), "emulator-5554")]

    async def test_click_by_text_and_index(self, server, device):
        """Two icons are labelled Gmail; index picks the second."""
        await call(server, "ClickBySelector", {"text": "Gmail", "index": 1})

        assert device.calls("tap") == [((910, 1970), "emulator-5554")]

    async def test_click_by_selector_without_a_selector_is_an_error(self, server, device):
        """At least one selector is required."""
        result = await call(server, "ClickBySelector", {}, ok=False)

        assert "at least one" in text_of(result)
        assert device.calls("tap") == []

    async def test_click_by_selector_not_found(self, server, device):
        """A miss is an error naming what was looked for; nothing is tapped."""
        result = await call(server, "ClickBySelector", {"text": "Nope", "timeout": 0}, ok=False)

        assert "text='Nope'" in text_of(result)
        assert device.calls("tap") == []

    async def test_wait_for_element_reports_where_it_is(self, server, device):
        """The reply carries the class, the tap point and the bounds."""
        result = await call(server, "WaitForElement", {"description": "Google Lens"})

        message = text_of(result)
        assert "Element found" in message
        assert "class=android.widget.ImageButton" in message
        assert "coords=(916,2207)" in message
        assert "bounds=[" in message
        assert device.calls("tap") == []

    async def test_wait_for_element_times_out_with_an_error(self, server, device):
        """Not found within the time is an error."""
        result = await call(server, "WaitForElement", {"text": "Nope", "timeout": 0}, ok=False)

        assert "No element matching" in text_of(result)

    async def test_blank_selectors_from_a_client_count_as_not_given(self, server, device):
        """A client that sends empty strings for unused fields still works."""
        result = await call(
            server,
            "WaitForElement",
            {"text": "", "resourceId": "g_icon", "className": "", "description": ""},
        )

        assert "coords=(164,2207)" in text_of(result)

    async def test_null_selectors_are_accepted(self, server, device):
        """An explicit null for an unused field is valid, as the original also allowed."""
        result = await call(
            server,
            "ClickBySelector",
            {"text": None, "resourceId": "g_icon", "className": None, "description": None},
        )

        assert "Clicked element" in text_of(result)


@pytest.mark.unit
class TestConcurrency:
    """Tool calls share one device and must not overlap."""

    async def test_two_simultaneous_calls_run_one_after_the_other(self, server, device):
        """Each tap finishes before the next starts, even though FastMCP uses threads."""
        device.tap_delay = 0.15

        async with Client(server) as client:
            await asyncio.gather(
                client.call_tool("Click", {"x": 1, "y": 1}),
                client.call_tool("Click", {"x": 2, "y": 2}),
            )

        order = [entry[0] for entry in device.log if entry[0] in ("tap_start", "tap")]
        assert order == ["tap_start", "tap", "tap_start", "tap"]

    async def test_a_failed_call_releases_the_lock(self, server, device):
        """An error inside a call does not block the ones after it."""
        device.devices = []
        await call(server, "Click", {"x": 1, "y": 1}, ok=False)
        device.devices = [EMULATOR]

        finished = threading.Event()

        async def later():
            await call(server, "Click", {"x": 2, "y": 2})
            finished.set()

        await asyncio.wait_for(later(), timeout=5)
        assert finished.is_set()
