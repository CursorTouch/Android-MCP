"""The UI tree: one moment of a device's screen, as ``uiautomator dump`` reports it."""

from collections.abc import Iterator, Sequence
from xml.etree import ElementTree

import android_mcp.adb as adb

from .config import INTERACTIVE_CLASSES
from .views import Bounds, Element, Node


def is_interactive(node: Node) -> bool:
    """Whether a person could do something with this node."""
    return (
        node.focusable
        or node.clickable
        or node.long_clickable
        or node.checkable
        or node.scrollable
        or node.selected
        or node.password
        or node.class_name in INTERACTIVE_CLASSES
    )


def _is_actionable(node: Node) -> bool:
    return node.clickable or node.long_clickable or node.checkable or node.scrollable


def takes_taps(node: Node) -> bool:
    """Whether a tap on this node is handled by it, rather than passed on to its parent.

    A node that is clickable, long-clickable or checkable handles taps. So does a text field or
    other interactive widget, which takes a tap to focus even when it is not flagged clickable.
    Scrolling and focusability alone do not: a tap on a scrolling list's empty space does nothing.
    """
    return (
        node.clickable
        or node.long_clickable
        or node.checkable
        or node.class_name in INTERACTIVE_CLASSES
    )


def element_name(node: Node) -> str:
    """The text that identifies ``node`` to a person, or ``""`` when it has none.

    The node's own content description or text wins. Failing that, the text of what is inside it,
    so a clickable row reads as its labels. Text inside a nested actionable node is used only when
    the row has none of its own, because that node is listed as an element in its own right.
    """
    name = node.content_desc or node.text
    if name:
        return name

    texts: list[str] = []
    fallback: list[str] = []

    def collect(current: Node) -> None:
        value = current.text or current.content_desc or current.hint
        if current is not node and _is_actionable(current):
            if value:
                fallback.append(value)
            return
        if value:
            texts.append(value)
        for child in current.children:
            collect(child)

    collect(node)
    return " ".join(texts or fallback).strip()


def _parse_node(element: ElementTree.Element) -> Node:
    def flag(name: str, default: bool = False) -> bool:
        return element.get(name, "true" if default else "false") == "true"

    return Node(
        class_name=element.get("class", ""),
        bounds=Bounds.parse(element.get("bounds", "")),
        package=element.get("package", ""),
        resource_id=element.get("resource-id", ""),
        text=element.get("text", ""),
        content_desc=element.get("content-desc", ""),
        hint=element.get("hint", ""),
        clickable=flag("clickable"),
        long_clickable=flag("long-clickable"),
        checkable=flag("checkable"),
        checked=flag("checked"),
        enabled=flag("enabled", default=True),
        focusable=flag("focusable"),
        focused=flag("focused"),
        scrollable=flag("scrollable"),
        selected=flag("selected"),
        password=flag("password"),
        children=tuple(_parse_node(child) for child in element.findall("node")),
    )


def _walk(
    nodes: Sequence[Node], path: tuple[Node, ...] = ()
) -> Iterator[tuple[Node, tuple[Node, ...]]]:
    """Every node under ``nodes`` with its ancestors, parents before children, in document order."""
    for node in nodes:
        yield node, path
        yield from _walk(node.children, (*path, node))


class Tree:
    """The UI of a device's screen at one moment: its windows, as a tree of nodes.

    A tree is a snapshot. It does not change when the screen does; read the device again for a
    new one. Build one from a device with :meth:`read`, or from dump XML with :meth:`from_xml`.

    Attributes:
        roots: One root :class:`Node` per window, in document order.
        rotation: The screen rotation in quarter turns (0 upright, 1 landscape, 2, 3), as the
            dump reports it. All coordinates are in the rotated screen's own pixels.
    """

    def __init__(self, roots: Sequence[Node] = (), rotation: int = 0) -> None:
        self.roots = tuple(roots)
        self.rotation = rotation

    @classmethod
    def from_xml(cls, xml: str) -> "Tree":
        """Parse the XML of a ``uiautomator dump``.

        Raises:
            xml.etree.ElementTree.ParseError: if ``xml`` is not well-formed.
            ValueError: if a node has a malformed ``bounds`` attribute.
        """
        document = ElementTree.fromstring(xml)
        roots = [_parse_node(child) for child in document.findall("node")]
        return cls(roots, rotation=int(document.get("rotation", "0")))

    @classmethod
    def read(cls, serial: str | None = None) -> "Tree":
        """Read the screen of ``serial`` now.

        Raises:
            AdbError: if the device cannot produce a dump; see ``adb.dump_hierarchy``.
        """
        return cls.from_xml(adb.dump_hierarchy(serial=serial))

    def nodes(self) -> Iterator[Node]:
        """Every node, parents before children, in document order."""
        for node, _ in _walk(self.roots):
            yield node

    def interactive_elements(self) -> list[Element]:
        """The enabled, tappable, named elements, in document order.

        Disabled nodes are skipped, as are nodes with no area and nodes with no name, since a
        caller could neither tap the first nor tell what the second is.
        """
        elements = []
        for node in self.nodes():
            if not node.enabled or not is_interactive(node) or node.bounds.is_empty:
                continue
            name = element_name(node)
            if name:
                elements.append(Element(name, node.class_name, node.short_id, node.bounds, node))
        return elements

    def find(
        self,
        *,
        text: str | None = None,
        resource_id: str | None = None,
        class_name: str | None = None,
        description: str | None = None,
    ) -> list[Node]:
        """The nodes that match every criterion given, in document order.

        Matching is exact and covers every node, interactive or not, so a label can be found as
        well as a button. ``resource_id`` may be the full id (``com.example:id/save``) or the
        short form after the slash (``save``), which spares the caller the app's package name.
        ``description`` is the content description. Nodes with no area are left out: they are not
        on screen.

        Raises:
            ValueError: if no criterion is given. A blank one counts as not given.
        """
        criteria = {
            name: value
            for name, value in (
                ("text", text),
                ("resource_id", resource_id),
                ("class_name", class_name),
                ("description", description),
            )
            if value
        }
        if not criteria:
            raise ValueError("give at least one of text, resource_id, class_name or description")

        wanted_id = criteria.get("resource_id", "")
        full_id = "/" in wanted_id or ":" in wanted_id

        def matches(node: Node) -> bool:
            return (
                ("text" not in criteria or node.text == criteria["text"])
                and ("class_name" not in criteria or node.class_name == criteria["class_name"])
                and ("description" not in criteria or node.content_desc == criteria["description"])
                and (
                    "resource_id" not in criteria
                    or (node.resource_id if full_id else node.short_id) == criteria["resource_id"]
                )
            )

        return [node for node in self.nodes() if not node.bounds.is_empty and matches(node)]

    def node_at(self, x: int, y: int) -> Node | None:
        """The node drawn on top at pixel ``(x, y)``, or ``None`` if the point is on no node.

        This is what is *seen* there, not what a tap reaches: see :meth:`tap_target`. Parents are
        drawn before their children and earlier siblings before later ones, so the last node in
        document order that contains the point is the one on top. (Elevation can reorder views;
        the dump does not report it.)
        """
        found = None
        for node in self.nodes():
            if node.bounds.contains(x, y):
                found = node
        return found

    def tap_target(self, x: int, y: int) -> Node | None:
        """The node that handles a tap at pixel ``(x, y)``, or ``None`` if nothing does.

        This follows how Android dispatches a touch. A view offers it to its children from the top
        down, and the first child that contains the point and handles it takes it. If no child
        does, the view handles it itself when it :func:`takes_taps`. A view that does not handle
        taps, such as a transparent layout drawn over a button, therefore lets the tap fall
        through to what is beneath it; only a view that does handle taps blocks what is under it.
        """

        def dispatch(nodes: Sequence[Node]) -> Node | None:
            for node in reversed(nodes):
                if not node.bounds.contains(x, y):
                    continue
                handler = dispatch(node.children)
                if handler is None and takes_taps(node):
                    handler = node
                if handler is not None:
                    return handler
            return None

        return dispatch(self.roots)
