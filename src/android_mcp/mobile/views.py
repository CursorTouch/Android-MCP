"""What the mobile service returns: the screen's elements and, optionally, a screenshot."""

from dataclasses import dataclass, field

from android_mcp.tree import Element

_HEADERS = ("Label", "Name", "ResourceId", "Class", "Coordinates", "Tap")


def format_elements(elements: list[Element]) -> str:
    """Lay ``elements`` out as the table an agent reads, one row per element.

    The label is the element's index in ``elements``, which is also the number drawn on an
    annotated screenshot. Whitespace in a name is collapsed so that every element is one line.
    The last column says whether a tap at the coordinates reaches the element: ``no`` marks a
    scrolling container, a selected tab, or something covered by another view.
    """
    if not elements:
        return "No interactive elements."
    rows = [
        (
            str(label),
            " ".join(element.name.split()),
            element.resource_id,
            element.class_name,
            "({},{})".format(*element.center),
            "yes" if element.tappable else "no",
        )
        for label, element in enumerate(elements)
    ]
    widths = [max(len(cell) for cell in column) for column in zip(_HEADERS, *rows, strict=True)]
    lines = [_HEADERS, *rows]
    return "\n".join(
        "  ".join(cell.ljust(width) for cell, width in zip(line, widths, strict=True)).rstrip()
        for line in lines
    )


@dataclass(frozen=True)
class MobileState:
    """The state of the device's screen at one moment.

    Attributes:
        elements: The interactive elements, in the order they are labelled.
        screenshot: PNG bytes, when a screenshot was asked for.
        warning: Set when something stopped the state being complete, for the agent to read.
    """

    elements: list[Element] = field(default_factory=list)
    screenshot: bytes | None = None
    warning: str | None = None

    def to_string(self) -> str:
        """The warning, if there is one, followed by the element table."""
        table = format_elements(self.elements)
        return f"{self.warning}\n{table}" if self.warning else table
