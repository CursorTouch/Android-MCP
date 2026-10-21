"""Click, ClickBySelector, LongClick, Swipe, Drag, Type and Press: acting on the screen."""

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..session import Session


def _acts(title: str) -> ToolAnnotations:
    return ToolAnnotations(
        title=title,
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=False,
    )


def register(mcp: FastMCP, session: Session) -> None:
    def click(x: int, y: int) -> str:
        with session.operation() as mobile:
            mobile.tap(x, y)
        return f"Clicked on ({x},{y})"

    mcp.tool(
        click,
        name="Click",
        description="Click on a specific coordinate",
        annotations=_acts("Click"),
    )

    def click_by_selector(
        text: str | None = None,
        resourceId: str | None = None,
        className: str | None = None,
        description: str | None = None,
        index: int = 0,
        timeout: float = 5.0,
    ) -> str:
        with session.operation() as mobile:
            element = mobile.click_element(
                text=text,
                resource_id=resourceId,
                class_name=className,
                description=description,
                index=index,
                timeout=timeout,
            )
        x, y = element.center
        message = f"Clicked element {element.name!r} at ({x},{y})"
        if not element.tappable:
            message += (
                ". Note: nothing at that point is marked as taking taps, so it may have had no "
                "effect; take a Snapshot to check."
            )
        return message

    mcp.tool(
        click_by_selector,
        name="ClickBySelector",
        description=(
            "Click on an element by selector (text, resourceId, className, description), all "
            "matched exactly; resourceId may be the full id or the part after the slash. More "
            "reliable than coordinate clicks: it finds the element when it clicks, so it handles "
            "dynamic layouts and elements that have moved. index picks the nth match, counting "
            "from 0. At least one selector must be provided."
        ),
        annotations=_acts("Click By Selector"),
    )

    def long_click(x: int, y: int) -> str:
        with session.operation() as mobile:
            mobile.long_press(x, y)
        return f"Long Clicked on ({x},{y})"

    mcp.tool(
        long_click,
        name="LongClick",
        description="Long click on a specific coordinate",
        annotations=_acts("Long Click"),
    )

    def swipe(x1: int, y1: int, x2: int, y2: int) -> str:
        with session.operation() as mobile:
            mobile.swipe(x1, y1, x2, y2)
        return f"Swiped from ({x1},{y1}) to ({x2},{y2})"

    mcp.tool(
        swipe,
        name="Swipe",
        description="Swipe from one coordinate to another",
        annotations=_acts("Swipe"),
    )

    def type_text(
        text: str, x: int | None = None, y: int | None = None, clear: bool = False
    ) -> str:
        with session.operation() as mobile:
            mobile.type_text(text, x=x, y=y, clear=clear)
        where = f" on ({x},{y})" if x is not None and y is not None else ""
        return f"Typed {text!r}{where}"

    mcp.tool(
        type_text,
        name="Type",
        description=(
            "Type text into a field. Give x and y to tap the field first, otherwise the text goes "
            "into whatever has focus. clear=true empties the field first. A newline presses "
            "Enter and a tab presses Tab. Printable ASCII and accented Latin letters (é ñ ü, not "
            "ç ß å) are typed directly. Any other text (CJK, Cyrillic, Arabic, emoji, ç) needs "
            "the ADBKeyboard app installed on the device and a focused text field; without the "
            "app it is rejected with install instructions."
        ),
        annotations=_acts("Type"),
    )

    def drag(x1: int, y1: int, x2: int, y2: int) -> str:
        with session.operation() as mobile:
            mobile.drag(x1, y1, x2, y2)
        return f"Dragged from ({x1},{y1}) and dropped on ({x2},{y2})"

    mcp.tool(
        drag,
        name="Drag",
        description=(
            "Drag from one coordinate and drop on another, for example to move an icon. "
            "Needs Android 8 or later."
        ),
        annotations=_acts("Drag"),
    )

    def press(button: str) -> str:
        with session.operation() as mobile:
            mobile.press(button)
        return f'Pressed the "{button}" button'

    mcp.tool(
        press,
        name="Press",
        description=(
            "Press a button on the device: back, home, recent, menu, search, enter, delete, "
            "tab, space, power, camera, volume up, volume down, volume mute, or up, down, "
            "left, right, center for the d-pad."
        ),
        annotations=_acts("Press"),
    )
