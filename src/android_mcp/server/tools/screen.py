"""Snapshot, Wait, WaitForElement and Notification: reading the screen."""

import os

from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from mcp.types import ToolAnnotations

from ..config import screenshot_quantized
from ..session import Session

_READS = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)
_ACTS = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
)


def _annotations(base: ToolAnnotations, title: str, **overrides: bool) -> ToolAnnotations:
    return ToolAnnotations(title=title, **{**base.model_dump(exclude={"title"}), **overrides})


def register(mcp: FastMCP, session: Session) -> None:
    def snapshot(use_vision: bool = False, use_annotation: bool = True) -> str | list:
        with session.operation() as mobile:
            state = mobile.get_state(
                use_vision=use_vision,
                annotate=use_annotation,
                quantize=screenshot_quantized(os.environ),
            )
        table = state.to_string()
        if state.screenshot is None:
            # A list of one string would be sent as JSON text, so plain text goes back as a string.
            return table
        return [table, Image(data=state.screenshot, format="png")]

    mcp.tool(
        snapshot,
        name="Snapshot",
        description=(
            "Get the state of the device: the interactive elements, each with a label and the "
            "coordinates to tap. Optionally includes a visual screenshot when use_vision=True. "
            "The use_annotation parameter (default True) can be set to False to get a clean "
            "screenshot without bounding boxes. If the screen never goes idle (a video or a "
            "running timer) the element list is unavailable and, with use_vision, only the "
            "screenshot is returned."
        ),
        annotations=_annotations(_READS, "Snapshot"),
        # The result is text, or text and an image. FastMCP cannot build a schema for that mix.
        output_schema=None,
    )

    def wait(duration: float) -> str:
        with session.operation(connect=False) as mobile:
            mobile.wait(duration)
        return f"Waited for {duration:g} seconds"

    mcp.tool(
        wait,
        name="Wait",
        description="Wait for a specific amount of time, in seconds",
        annotations=_annotations(_ACTS, "Wait", idempotent_hint=True),
    )

    def wait_for_element(
        text: str | None = None,
        resourceId: str | None = None,
        className: str | None = None,
        description: str | None = None,
        timeout: float = 10.0,
    ) -> str:
        with session.operation() as mobile:
            element = mobile.wait_for_element(
                text=text,
                resource_id=resourceId,
                class_name=className,
                description=description,
                timeout=timeout,
            )
        box = element.bounds
        x, y = element.center
        return (
            f"Element found: text={element.name!r} class={element.class_name} "
            f"coords=({x},{y}) bounds=[{box.left},{box.top}][{box.right},{box.bottom}]"
        )

    mcp.tool(
        wait_for_element,
        name="WaitForElement",
        description=(
            "Wait for an element to appear on screen. Use this instead of Wait when content is "
            "loading dynamically. Select it by text, resourceId (full, or the part after the "
            "slash), className or description, all matched exactly; at least one is required. "
            "Returns the element's coordinates when found, or an error on timeout."
        ),
        annotations=_annotations(_READS, "Wait For Element"),
    )

    def notification() -> str:
        with session.operation() as mobile:
            mobile.open_notifications()
        return "Accessed notification bar"

    mcp.tool(
        notification,
        name="Notification",
        description="Access the notifications seen on the device",
        annotations=_annotations(_ACTS, "Notification", idempotent_hint=True),
    )
