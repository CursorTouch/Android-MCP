"""Turn a ``uiautomator dump`` into the list of elements a caller can tap."""

from xml.etree import ElementTree

import android_mcp.adb as adb

from .config import INTERACTIVE_CLASSES
from .views import Bounds, Element, Node


def parse_hierarchy(xml: str) -> list[Node]:
    """Parse the XML of a ``uiautomator dump``.

    Returns:
        One root :class:`Node` per window on screen, in document order.

    Raises:
        xml.etree.ElementTree.ParseError: if ``xml`` is not well-formed.
        ValueError: if a node has a malformed ``bounds`` attribute.
    """
    return [_parse_node(child) for child in ElementTree.fromstring(xml).findall("node")]


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


def _walk(nodes):
    """Every node under ``nodes``, parents before children, in document order."""
    for node in nodes:
        yield node
        yield from _walk(node.children)


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


def interactive_elements(roots: list[Node]) -> list[Element]:
    """The enabled, tappable, named elements under ``roots``, in document order.

    Disabled nodes are skipped, as are nodes with no area and nodes with no name, since a caller
    could neither tap the first nor tell what the second is.
    """
    elements = []
    for node in _walk(roots):
        if not node.enabled or not is_interactive(node) or node.bounds.is_empty:
            continue
        name = element_name(node)
        if name:
            elements.append(Element(name, node.class_name, node.short_id, node.bounds))
    return elements


def find_nodes(
    roots: list[Node],
    *,
    text: str | None = None,
    resource_id: str | None = None,
    class_name: str | None = None,
    description: str | None = None,
) -> list[Node]:
    """The nodes under ``roots`` that match every criterion given, in document order.

    Matching is exact and covers every node, interactive or not, so a label can be found as well
    as a button. ``resource_id`` may be the full id (``com.example:id/save``) or the short form
    after the slash (``save``), which spares the caller the app's package name. ``description`` is
    the content description. Nodes with no area are left out: they are not on screen.

    Args:
        roots: The windows from :func:`parse_hierarchy`.
        text: The node's text.
        resource_id: The node's resource id, full or short.
        class_name: The node's class, e.g. ``android.widget.Button``.
        description: The node's content description.

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

    full_id = "/" in criteria.get("resource_id", "") or ":" in criteria.get("resource_id", "")

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

    return [node for node in _walk(roots) if not node.bounds.is_empty and matches(node)]


def get_elements(*, serial: str | None = None) -> list[Element]:
    """Read the screen of ``serial`` and return its interactive elements.

    Raises:
        AdbError: if the device cannot produce a dump. See :func:`android_mcp.adb.dump_hierarchy`.
    """
    return interactive_elements(parse_hierarchy(adb.dump_hierarchy(serial=serial)))
