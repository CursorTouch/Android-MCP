"""Data types for the UI tree: what ``uiautomator dump`` reports, and what survives filtering."""

import re
from dataclasses import dataclass, field

_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


@dataclass(frozen=True)
class Bounds:
    """A screen rectangle in pixels, as uiautomator writes it: ``[left,top][right,bottom]``."""

    left: int
    top: int
    right: int
    bottom: int

    @classmethod
    def parse(cls, text: str) -> "Bounds":
        """Read uiautomator's ``bounds`` attribute.

        Raises:
            ValueError: if ``text`` is not of the form ``[left,top][right,bottom]``.
        """
        match = _BOUNDS.fullmatch(text.strip())
        if match is None:
            raise ValueError(f"not a bounds string: {text!r}")
        return cls(*map(int, match.groups()))

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def is_empty(self) -> bool:
        """True when nothing can be tapped inside: no width or no height."""
        return self.width <= 0 or self.height <= 0

    @property
    def center(self) -> tuple[int, int]:
        """The ``(x, y)`` pixel to tap to hit this rectangle."""
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2

    def contains(self, x: int, y: int) -> bool:
        """Whether pixel ``(x, y)`` is inside. The right and bottom edges are outside, as pixels
        are numbered from 0: a view ``[0,0][100,100]`` covers pixels 0 to 99."""
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(frozen=True)
class Node:
    """One ``<node>`` of the dump, with its children."""

    class_name: str
    bounds: Bounds
    package: str = ""
    resource_id: str = ""
    text: str = ""
    content_desc: str = ""
    hint: str = ""
    clickable: bool = False
    long_clickable: bool = False
    checkable: bool = False
    checked: bool = False
    enabled: bool = True
    focusable: bool = False
    focused: bool = False
    scrollable: bool = False
    selected: bool = False
    password: bool = False
    children: tuple["Node", ...] = ()

    @property
    def short_id(self) -> str:
        """The resource id without its package: ``workspace`` for ``x.launcher:id/workspace``."""
        return self.resource_id.rpartition("/")[2]


@dataclass(frozen=True)
class Element:
    """An interactive thing on screen that a caller can name and tap.

    Attributes:
        node: The tree node this was made from, when it came from a tree. It is left out of
            comparisons and of the repr, so two elements are equal when they look equal.
        tappable: Whether a tap at the element's centre reaches the element (or a part of it).
            False for a scrolling container, a selected tab, or something covered by another
            view that handles taps: it is listed, but tapping its centre will not act on it.
    """

    name: str
    class_name: str
    resource_id: str
    bounds: Bounds
    node: Node | None = field(default=None, repr=False, compare=False)
    tappable: bool = True

    @property
    def center(self) -> tuple[int, int]:
        return self.bounds.center
