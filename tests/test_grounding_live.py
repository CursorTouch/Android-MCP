"""Grounding on a real device: does acting on what Snapshot reports do what it says?

Run with an emulator or phone attached:

    ANDROID_MCP_LIVE=1 uv run pytest -m live -v

Three layers, each stricter than the last:

1. Geometry. Every element's tap point is on screen and inside its own bounds, the screenshot is the
   size of the window the coordinates are in, and nothing the tree lists would send a tap
   somewhere else (see ``grounding.py``).
2. Hit testing against reality. The tree says which node a tap at a point reaches; here that is
   compared with what really happens when the point is tapped.
3. Behaviour. Taps on text fields focus those fields, taps on settings rows open the page the row
   names, and a tap on a switch flips it.

The tests leave the device as they found it: the home screen, upright, switches restored.
"""

import io
import subprocess
import time

import grounding
import pytest
from PIL import Image

import android_mcp.adb as adb
from android_mcp.tree import Tree

pytestmark = pytest.mark.live

SETTLE = 1.6


def _wait(seconds=SETTLE):
    time.sleep(seconds)


@pytest.fixture(scope="module")
def serial():
    """The attached device, which must be ready."""
    ready = [d for d in adb.list_devices() if d.state is adb.DeviceState.DEVICE]
    if not ready:
        pytest.fail("no ready device attached")
    return ready[0].serial


@pytest.fixture(autouse=True)
def home_screen_afterwards(serial):
    """Start and end on the home screen with the test apps closed."""
    yield
    for package in ("com.google.android.contacts", "com.google.android.deskclock"):
        adb.shell(f"am force-stop {package}", serial=serial)
    adb.press_key(adb.KeyCode.HOME, serial=serial)
    _wait(0.8)


def _open(serial, command, wait=3.0):
    adb.press_key(adb.KeyCode.HOME, serial=serial)
    _wait(0.8)
    adb.shell(command, serial=serial)
    _wait(wait)


SCREENS = {
    "launcher": "input keyevent 3",
    "settings": "am start -a android.settings.SETTINGS",
    "wifi settings": "am start -a android.settings.WIFI_SETTINGS",
    "display settings": "am start -a android.settings.DISPLAY_SETTINGS",
    "contact form": "am start -a android.intent.action.INSERT -t vnd.android.cursor.dir/contact",
    "alarm": "am start -a android.intent.action.SHOW_ALARMS",
}


class TestGeometry:
    """Layer 1: the numbers are sane on every screen."""

    @pytest.mark.parametrize("screen", SCREENS)
    def test_no_element_points_somewhere_it_cannot_be_tapped(self, serial, screen):
        """Tap points are on screen and in bounds, and a tap there reaches the element."""
        _open(serial, SCREENS[screen])

        tree = Tree.read(serial)
        items = grounding.findings(tree)

        assert len(tree.interactive_elements()) > 3, "the screen did not load"
        assert grounding.hard(items) == [], "\n" + "\n".join(map(str, grounding.hard(items)))

    @pytest.mark.parametrize("screen", SCREENS)
    def test_the_screenshot_is_in_the_same_coordinates_as_the_tree(self, serial, screen):
        """The window lies inside the screenshot, so a box at (x, y) is where a tap lands.

        Upright an app's window fills the display. Turned on its side it can be smaller (the
        navigation bar takes a strip), so what is checked is containment, not equal size.
        """
        _open(serial, SCREENS[screen])

        tree = Tree.read(serial)
        screenshot = Image.open(io.BytesIO(adb.screencap(serial=serial)))
        window = grounding.screen_of(tree)

        assert 0 <= window.left and window.right <= screenshot.width
        assert 0 <= window.top and window.bottom <= screenshot.height
        if tree.rotation == 0:
            assert screenshot.size == (window.width, window.height)

    def test_every_element_is_inside_the_screen(self, serial):
        """Nothing the tree lists is wholly off screen."""
        _open(serial, SCREENS["settings"])

        tree = Tree.read(serial)
        window = grounding.screen_of(tree)

        for element in tree.interactive_elements():
            b = element.bounds
            assert (
                b.right > 0 and b.bottom > 0 and b.left < window.width and b.top < window.height
            ), element


class TestHitTestingAgainstReality:
    """Layer 2: the tree's idea of what a tap reaches matches what the device does."""

    def test_every_text_field_can_be_focused_by_tapping_its_reported_point(self, serial):
        """For each field on the contact form: read the screen, tap the field's point, check focus.

        If a tap does not take, the layout has moved (see the next test), so the screen is read
        again and the tap repeated. A field that has scrolled out of view is not listed, so it is
        skipped: only what the tree reports can be held to its report.
        """
        _open(serial, SCREENS["contact form"], wait=4)
        names = [
            e.name
            for e in Tree.read(serial).interactive_elements()
            if e.class_name.endswith("EditText")
        ]
        assert len(names) >= 5

        tested = 0
        for name in names:
            for _ in range(2):
                field = next(
                    (
                        e
                        for e in Tree.read(serial).interactive_elements()
                        if e.name == name and e.class_name.endswith("EditText")
                    ),
                    None,
                )
                if field is None:
                    break  # scrolled out of view: nothing is claimed about it now
                adb.tap(*field.center, serial=serial)
                _wait(1.2)
                focused = [
                    n
                    for n in Tree.read(serial).nodes()
                    if n.focused and n.class_name.endswith("EditText")
                ]
                assert len(focused) <= 1
                if focused:
                    assert focused[0].bounds == field.bounds, (
                        f"tapped {name!r} at {field.center} but focus went to "
                        f"{focused[0].hint or focused[0].text!r}"
                    )
                    tested += 1
                    break
            else:
                pytest.fail(
                    f"tapping {name!r} focused nothing, even after reading the screen again"
                )

        assert tested >= 4, f"only {tested} of {len(names)} fields could be checked"

    def test_a_tap_can_move_the_layout_so_reported_points_go_stale(self, serial):
        """Tap Phone, then Email at its reported point: the form scrolls instead of focusing Email.

        With a field focused the soft keyboard's area is reserved, and tapping a field below it
        scrolls the form first. The first tap at the old point therefore does not focus Email,
        Email's point has moved, and a tap at the freshly read point does. A Snapshot is a moment,
        not a promise: read again after any action that can change the screen.
        """
        _open(serial, SCREENS["contact form"], wait=4)

        def read():
            fields = {
                e.name: e
                for e in Tree.read(serial).interactive_elements()
                if e.class_name.endswith("EditText")
            }
            focused = [
                n.hint or n.text
                for n in Tree.read(serial).nodes()
                if n.focused and n.class_name.endswith("EditText")
            ]
            return fields, focused

        fields, _ = read()
        adb.tap(*fields["Phone"].center, serial=serial)
        _wait(2.5)
        fields, focused = read()
        assert focused == ["Phone"]
        stale_point = fields["Email"].center

        adb.tap(*stale_point, serial=serial)
        _wait(1.5)
        fields, focused = read()

        assert fields["Email"].center != stale_point, "the form did not scroll; the test is stale"
        assert focused == [], f"the first tap focused {focused}"

        adb.tap(*fields["Email"].center, serial=serial)
        _wait(1.5)
        assert read()[1] == ["Email"]

    def test_a_tap_at_a_point_the_tree_says_reaches_nothing_changes_nothing(self, serial):
        """The launcher's empty wallpaper area: no node takes a tap there, and nothing opens."""
        _open(serial, SCREENS["launcher"])
        tree = Tree.read(serial)
        point = (540, 1000)  # empty space between the smartspace and the app icons
        assert tree.tap_target(*point) is None

        before = adb.shell("dumpsys window | grep mCurrentFocus", serial=serial)
        adb.tap(*point, serial=serial)
        _wait(1.2)

        assert adb.shell("dumpsys window | grep mCurrentFocus", serial=serial) == before

    def test_the_selected_tab_is_listed_but_a_tap_on_it_reaches_nothing(self, serial):
        """The tree is honest that an already-selected tab does not take taps."""
        _open(serial, SCREENS["alarm"])
        tree = Tree.read(serial)

        selected = next(e for e in tree.interactive_elements() if e.resource_id == "tab_menu_alarm")
        others = [e for e in tree.interactive_elements() if e.resource_id == "tab_menu_clock"]

        assert tree.tap_target(*selected.center) is None
        assert tree.tap_target(*others[0].center) is others[0].node


class TestBehaviour:
    """Layer 3: acting on a labelled element does what its name says."""

    def test_tapping_a_settings_row_opens_the_page_it_names(self, serial):
        """Each row's title is a heading on the page it opens."""
        _open(serial, SCREENS["settings"])
        rows = [
            e
            for e in Tree.read(serial).interactive_elements()
            if e.class_name.endswith("LinearLayout") and e.node.clickable
        ]
        assert len(rows) >= 5

        checked = 0
        for row in rows[:6]:
            title = _row_title(row)
            adb.tap(*row.center, serial=serial)
            _wait(2.5)
            destination = Tree.read(serial)

            assert _has_title(destination, title), (
                f"tapped {row.name!r} at {row.center} but the page has no {title!r} title; "
                f"it has {_labels(destination)}"
            )
            checked += 1
            adb.press_key(adb.KeyCode.BACK, serial=serial)
            _wait(1.5)
        assert checked >= 5

    def test_tapping_a_switch_flips_it(self, serial):
        """The alarm switch changes state when its reported point is tapped, and is put back."""
        _open(serial, SCREENS["alarm"], wait=3.5)
        switch = next(
            e for e in Tree.read(serial).interactive_elements() if e.class_name.endswith("Switch")
        )
        original = switch.node.checked

        try:
            adb.tap(*switch.center, serial=serial)
            _wait(1.2)
            after = _find_at(Tree.read(serial), switch.bounds)

            assert after.checked is (not original)
        finally:
            now = _find_at(Tree.read(serial), switch.bounds)
            if now is not None and now.checked is not original:
                adb.tap(*switch.center, serial=serial)
                _wait(1.0)

        assert _find_at(Tree.read(serial), switch.bounds).checked is original

    def test_each_bottom_tab_goes_to_its_page(self, serial):
        """The Clock app's tabs open the page of the same name."""
        _open(serial, SCREENS["alarm"], wait=3.5)
        tabs = {
            e.name: e
            for e in Tree.read(serial).interactive_elements()
            if e.resource_id.startswith("tab_menu_") and e.resource_id != "tab_menu_alarm"
        }
        assert {"Clock", "Timer"} <= set(tabs)

        for name in ("Clock", "Timer"):
            adb.tap(*tabs[name].center, serial=serial)
            _wait(2.0)
            tree = Tree.read(serial)
            selected = next(
                n for n in tree.nodes() if n.resource_id.endswith("tab_menu_" + name.lower())
            )

            assert selected.selected or selected.focused or not selected.clickable, name


class TestRotation:
    """The same guarantees after the screen is turned on its side."""

    def test_landscape_coordinates_still_ground(self, serial, emulator_rotation):
        """Rotated, the dump, the screenshot and the taps still agree with each other.

        The app's window need not fill the display: in landscape it starts 128 px in from the left
        (the navigation bar's side). What must hold is that its coordinates are display pixels, so
        the window lies inside the screenshot and a tap at an element's point opens that element.
        """
        _open(serial, SCREENS["settings"], wait=3.5)
        emulator_rotation.quarter_turn()  # the launcher is portrait-locked: turn with an app open
        _wait(1.5)
        assert _rotation(serial) != 0, "the emulator did not rotate"

        tree = Tree.read(serial)
        window = grounding.screen_of(tree)
        screenshot = Image.open(io.BytesIO(adb.screencap(serial=serial)))
        items = grounding.findings(tree)

        assert tree.rotation != 0
        assert screenshot.width > screenshot.height, "the display is not landscape"
        assert 0 <= window.left and window.right <= screenshot.width
        assert 0 <= window.top and window.bottom <= screenshot.height
        assert grounding.hard(items) == [], "\n" + "\n".join(map(str, grounding.hard(items)))

        row = next(
            e
            for e in tree.interactive_elements()
            if e.node.clickable and e.class_name.endswith("LinearLayout")
        )
        title = _row_title(row)
        adb.tap(*row.center, serial=serial)
        _wait(2.5)
        assert _has_title(Tree.read(serial), title), f"landscape tap on {row.name!r} missed"


class _EmulatorRotation:
    """Turns an emulator a quarter turn at a time and remembers how far it has gone."""

    def __init__(self, serial):
        self.serial = serial
        self.turns = 0

    def quarter_turn(self):
        subprocess.run(
            [adb.find_adb(), "-s", self.serial, "emu", "rotate"], capture_output=True, check=True
        )
        self.turns += 1
        _wait(2.5)


@pytest.fixture
def emulator_rotation(serial):
    """Let a test rotate an emulator, and turn it back to where it was afterwards.

    ``settings put system user_rotation`` does not rotate the emulator; the console's ``rotate``
    does, a quarter turn per call, once auto-rotate is on. The emulator keeps its sensor reading
    when the foreground app does not rotate (the launcher), so the way back is to undo exactly
    the turns made. Skipped on a real device.
    """
    if not serial.startswith("emulator-"):
        pytest.skip("rotation is driven through the emulator console")
    auto = adb.shell("settings get system accelerometer_rotation", serial=serial).strip()
    adb.shell("settings put system accelerometer_rotation 1", serial=serial)
    rotation = _EmulatorRotation(serial)
    try:
        yield rotation
    finally:
        for _ in range((4 - rotation.turns) % 4):
            rotation.quarter_turn()
        adb.shell("am force-stop com.android.settings", serial=serial)
        adb.shell(
            f"settings put system accelerometer_rotation {0 if auto == 'null' else auto}",
            serial=serial,
        )
        _wait(1.0)


def _has_title(tree, title):
    """Whether the page has ``title`` as text, or as a content description (a toolbar's title)."""
    return any(n.text == title or n.content_desc == title for n in tree.nodes())


def _labels(tree, limit=6):
    """The first few texts and descriptions on a page, for a failure message."""
    return [n.text or n.content_desc for n in tree.nodes() if n.text or n.content_desc][:limit]


def _row_title(element):
    """The first line of a Settings row: its title, before the summary."""
    texts = [n.text for n in _walk(element.node) if n.text]
    return texts[0] if texts else element.name


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


def _find_at(tree, bounds):
    """The node with exactly these bounds that is a switch."""
    return next((n for n in tree.nodes() if n.bounds == bounds), None)


def _rotation(serial):
    """The display's rotation in quarter turns, from ``dumpsys window``."""
    line = adb.shell("dumpsys window displays | grep -m1 mCurrentRotation", serial=serial)
    return {"ROTATION_0": 0, "ROTATION_90": 1, "ROTATION_180": 2, "ROTATION_270": 3}.get(
        line.strip().partition("=")[2], 0
    )
