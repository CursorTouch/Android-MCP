"""The mobile service: one connected device, read through its screen and driven through input."""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from time import monotonic, sleep
from typing import Literal

import android_mcp.adb as adb
from android_mcp.tree import Element, Tree

from .errors import ElementNotFoundError, MobileError
from .screenshot import render
from .views import MobileState

Connection = Literal["auto", "usb", "wifi"]


def _read_elements(serial: str) -> list[Element]:
    """The interactive elements on the screen of ``serial`` now."""
    return Tree.read(serial).interactive_elements()


def _is_emulator(device: adb.Device) -> bool:
    return device.serial.startswith("emulator-")


def pick_device(
    devices: Sequence[adb.Device], connection: Connection = "auto"
) -> adb.Device | None:
    """Choose which of ``devices`` to use when the caller named none.

    Only devices that are ready (state ``device``) are considered, in the order adb lists them.
    ``connection`` narrows the choice: ``wifi`` takes a ``host:port`` serial, ``usb`` a physical
    device with no colon in its serial. ``auto`` takes the first physical device, since someone
    who plugged a phone in did not mean to drive the emulator, and falls back to an emulator.

    Returns:
        The chosen device, or ``None`` when nothing qualifies.
    """
    ready = [device for device in devices if device.state is adb.DeviceState.DEVICE]
    if connection == "wifi":
        return next((device for device in ready if ":" in device.serial), None)
    if connection == "usb":
        return next(
            (device for device in ready if ":" not in device.serial and not _is_emulator(device)),
            None,
        )
    return next((device for device in ready if not _is_emulator(device)), None) or next(
        iter(ready), None
    )


def _describe(devices: Sequence[adb.Device]) -> str:
    if not devices:
        return "No devices are attached."
    return "Attached: " + ", ".join(f"{device.serial} ({device.state})" for device in devices) + "."


def normalize_wifi_address(host: str | None) -> str | None:
    """Give ``host`` or ``host:port`` as adb wants it, adding the default port 5555.

    Returns:
        The address, or ``None`` when ``host`` is missing or blank.
    """
    if host is None or not host.strip():
        return None
    host = host.strip()
    return host if ":" in host else f"{host}:5555"


def _describe_selector(**selector: str | None) -> str:
    return ", ".join(f"{name}={value!r}" for name, value in selector.items() if value)


class Mobile:
    """The service an MCP server drives: connect to a device, read its screen, act on it."""

    def __init__(self) -> None:
        self._serial: str | None = None

    @staticmethod
    def list_devices() -> list[adb.Device]:
        """Every device adb can see, whatever its state.

        When there are none, devices advertising wireless debugging over mDNS are connected and
        the list is read again, since adb does not connect to them by itself.
        """
        devices = adb.list_devices()
        if not devices and adb.connect_mdns_peers():
            devices = adb.list_devices()
        return devices

    @property
    def serial(self) -> str | None:
        """The connected device's serial, or ``None``."""
        return self._serial

    @property
    def is_connected(self) -> bool:
        return self._serial is not None

    def connect(self, serial: str | None = None, *, connection: Connection = "auto") -> adb.Device:
        """Select the device to work with.

        Args:
            serial: The device to use. Omit to choose one with :func:`pick_device`.
            connection: How to choose when ``serial`` is omitted. Ignored when it is given.

        Returns:
            The device now connected.

        Raises:
            MobileError: if the device named is not attached or not ready, or none qualifies.
            AdbError: if adb itself fails.
        """
        devices = self.list_devices()
        if serial is not None:
            device = next((device for device in devices if device.serial == serial), None)
            if device is None:
                raise MobileError(f"Device {serial!r} not found. {_describe(devices)}")
            if device.state is not adb.DeviceState.DEVICE:
                hint = (
                    " Accept the USB debugging prompt on the device."
                    if device.state is adb.DeviceState.UNAUTHORIZED
                    else ""
                )
                raise MobileError(f"Device {serial!r} is {device.state}, not ready.{hint}")
        else:
            device = pick_device(devices, connection)
            if device is None:
                wanted = "" if connection == "auto" else f" over {connection}"
                raise MobileError(f"No ready device{wanted}. {_describe(devices)}")
        self._serial = device.serial
        return device

    def connect_wifi(self, host: str) -> adb.Device:
        """Connect adb to a device over Wi-Fi, then select it.

        Args:
            host: ``host`` or ``host:port``. Port 5555 is assumed when there is none.

        Raises:
            MobileError: if ``host`` is blank, or the device does not show up as ready.
            AdbError: if adb cannot connect.
        """
        address = normalize_wifi_address(host)
        if address is None:
            raise MobileError("A host or host:port is required to connect over Wi-Fi.")
        adb.connect(address)
        return self.connect(address)

    def disconnect(self) -> None:
        """Forget the connected device. Nothing is changed on the device itself."""
        self._serial = None

    def _require(self) -> str:
        if self._serial is None:
            raise MobileError("No device connected. Call connect() first.")
        return self._serial

    def get_state(
        self, *, use_vision: bool = False, annotate: bool = True, quantize: bool = False
    ) -> MobileState:
        """Read what is on the device's screen.

        The element list and the screenshot are taken at the same time, so they show the same
        moment and cost the slower of the two, not both.

        Args:
            use_vision: Also capture a screenshot.
            annotate: Draw each element's box and label number on the screenshot.
            quantize: Reduce the screenshot to 256 colours to make it smaller.

        Returns:
            The state. When the screen never goes idle (a video or a running timer) the element
            list cannot be read; with ``use_vision`` the state then holds the screenshot alone and
            a ``warning`` saying so.

        Raises:
            MobileError: if no device is connected.
            ScreenNotIdleError: if the screen never goes idle and no screenshot was asked for.
            AdbError: if the device cannot be read.
        """
        serial = self._require()
        if not use_vision:
            return MobileState(elements=_read_elements(serial))

        with ThreadPoolExecutor(max_workers=2) as pool:
            elements_future = pool.submit(_read_elements, serial)
            screenshot_future = pool.submit(adb.screencap, serial=serial)
            png = screenshot_future.result()
            try:
                elements, warning = elements_future.result(), None
            except adb.ScreenNotIdleError as error:
                elements = []
                warning = f"Elements unavailable: {error}. Use the screenshot and tap coordinates."

        screenshot = render(png, elements, annotate_elements=annotate, quantize=quantize)
        return MobileState(elements=elements, screenshot=screenshot, warning=warning)

    def tap(self, x: int, y: int) -> None:
        """Tap the screen at pixel ``(x, y)``."""
        adb.tap(x, y, serial=self._require())

    def long_press(self, x: int, y: int) -> None:
        """Press and hold at pixel ``(x, y)``."""
        adb.long_press(x, y, serial=self._require())

    def swipe(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Swipe from ``(x1, y1)`` to ``(x2, y2)``."""
        adb.swipe(x1, y1, x2, y2, serial=self._require())

    def drag(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Press at ``(x1, y1)``, drag to ``(x2, y2)`` and release."""
        adb.drag(x1, y1, x2, y2, serial=self._require())

    def press(self, button: str) -> None:
        """Press a button by name, such as ``"back"``, ``"home"`` or ``"volume up"``.

        Raises:
            ValueError: if the name is not a known key, listing the ones that are.
            MobileError: if no device is connected.
        """
        key = adb.KeyCode.parse(button)
        adb.press_key(key, serial=self._require())

    def type_text(
        self, text: str, *, x: int | None = None, y: int | None = None, clear: bool = False
    ) -> None:
        """Type ``text`` into a field.

        Args:
            text: What to type. See :func:`android_mcp.adb.type_text` for what can be typed.
            x: With ``y``, tap this point first to focus the field. Omit both to type into
                whatever already has focus.
            y: See ``x``.
            clear: Empty the field before typing.

        Raises:
            ValueError: if ``text`` cannot be typed, or only one of ``x`` and ``y`` is given.
                Nothing is tapped or cleared in that case.
            MobileError: if no device is connected.
        """
        serial = self._require()
        # Everything that can be refused is refused before the screen is touched.
        adb.check_typeable(text, serial=serial)
        if (x is None) != (y is None):
            raise ValueError("Give both x and y to tap a field first, or neither.")
        if x is not None and y is not None:
            adb.tap(x, y, serial=serial)
            sleep(_FOCUS_SETTLE)
        if clear:
            adb.clear_text(serial=serial)
        adb.type_text(text, serial=serial)

    def open_notifications(self) -> None:
        """Pull down the notification shade."""
        adb.expand_notifications(serial=self._require())

    def wait(self, seconds: float) -> None:
        """Pause for ``seconds``, for something on the device to finish.

        Raises:
            ValueError: if ``seconds`` is negative.
        """
        if seconds < 0:
            raise ValueError(f"Cannot wait a negative time: {seconds}")
        sleep(seconds)

    def find_element(
        self,
        *,
        text: str | None = None,
        resource_id: str | None = None,
        class_name: str | None = None,
        description: str | None = None,
        index: int = 0,
    ) -> Element | None:
        """Look for an element on the screen now.

        The criteria are those of :meth:`android_mcp.tree.Tree.find`; every one given must match.

        Args:
            index: Which match to return when several match, counting from 0 in screen order.

        Returns:
            The element, or ``None`` when nothing (or not that many things) matches.

        Raises:
            ValueError: if no criterion is given, or ``index`` is negative.
            MobileError: if no device is connected.
            AdbError: if the screen cannot be read.
        """
        if index < 0:
            raise ValueError(f"index cannot be negative: {index}")
        serial = self._require()
        tree = Tree.read(serial)
        matches = tree.find(
            text=text,
            resource_id=resource_id,
            class_name=class_name,
            description=description,
        )
        if index >= len(matches):
            return None
        return tree.element_for(matches[index])

    def wait_for_element(
        self,
        *,
        text: str | None = None,
        resource_id: str | None = None,
        class_name: str | None = None,
        description: str | None = None,
        index: int = 0,
        timeout: float = 10.0,
    ) -> Element:
        """Wait for an element to appear, looking again every moment until ``timeout``.

        The screen is always read at least once, whatever the timeout. Each read takes a couple of
        seconds on a real device, so the wait can run a little over ``timeout``. A screen that
        never goes idle cannot be read, so it is kept trying like a screen that does not have the
        element yet, and the final error says which it was.

        Raises:
            ElementNotFoundError: if it never appears.
            ValueError: if no criterion is given, or ``index`` or ``timeout`` is negative.
            MobileError: if no device is connected.
            AdbError: for any failure to read the screen other than a busy one.
        """
        if timeout < 0:
            raise ValueError(f"timeout cannot be negative: {timeout}")
        criteria = {
            "text": text,
            "resource_id": resource_id,
            "class_name": class_name,
            "description": description,
        }
        # With no windows to search this only validates the criteria, so a bad call fails now
        # instead of after the first slow read.
        Tree().find(**criteria)
        self._require()

        deadline = monotonic() + timeout
        busy = False
        while True:
            try:
                element = self.find_element(index=index, **criteria)
            except adb.ScreenNotIdleError:
                element, busy = None, True
            else:
                busy = False
            if element is not None:
                return element
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            sleep(min(_POLL_INTERVAL, remaining))

        detail = " The screen never went idle, so it could not be read." if busy else ""
        raise ElementNotFoundError(
            f"No element matching {_describe_selector(**criteria)} within {timeout:g}s.{detail}"
        )

    def click_element(
        self,
        *,
        text: str | None = None,
        resource_id: str | None = None,
        class_name: str | None = None,
        description: str | None = None,
        index: int = 0,
        timeout: float = 5.0,
    ) -> Element:
        """Wait for an element, as :meth:`wait_for_element` does, then tap its centre.

        Finding the element when you act, instead of using coordinates from an earlier snapshot,
        keeps the tap right when the layout has moved since.

        The tap is made even when the tree says nothing at that point takes taps, because a view
        can handle touches through a listener without being flagged clickable. The returned
        element's ``tappable`` says what the tree thought, so the caller can check the result.

        Returns:
            The element that was tapped.

        Raises:
            ElementNotFoundError: if it never appears.
            ValueError: as :meth:`wait_for_element`.
            MobileError: if no device is connected.
        """
        element = self.wait_for_element(
            text=text,
            resource_id=resource_id,
            class_name=class_name,
            description=description,
            index=index,
            timeout=timeout,
        )
        self.tap(*element.center)
        return element


# Time for the keyboard and focus to settle after tapping a field, before text goes in.
_FOCUS_SETTLE = 0.3
# Pause between looks while waiting for an element. A look is itself slow, so this is short.
_POLL_INTERVAL = 0.5
