"""Grounding checks: does the point Snapshot reports for an element really reach that element?

An agent reads the element table and taps the coordinates in it. Grounding is the property that
this acts on the element the agent meant. These checks look for the ways it can fail, using only
what the dump says, so they run on saved dumps as well as on a device.

Kinds of finding, from worst to mildest:

``off_screen``
    The tap point is outside the screen, so the tap lands on nothing.
``outside_own_bounds``
    The tap point is not inside the element's own rectangle (a bug in the geometry).
``tap_goes_elsewhere``
    The element handles taps, but a tap at its point is taken by a different node: one drawn over
    it that handles taps, or a sibling. The agent would act on the wrong thing.
``tap_misses``
    The element handles taps, but a tap at its point reaches no node that does.
``not_a_tap_target``
    The element is listed because it can scroll or take focus, not because a tap does anything
    (a scrolling container, a focusable label). Tapping its centre is not what it is for.
``shared_point``
    Two listed elements have the same tap point, so a tap there can only act on one of them.
"""

from dataclasses import dataclass

from android_mcp.tree import Bounds, Element, Node, Tree, takes_taps

HARD = ("off_screen", "outside_own_bounds", "tap_goes_elsewhere", "tap_misses")
SOFT = ("not_a_tap_target", "shared_point")


@dataclass(frozen=True)
class Finding:
    """One way an element's tap point can mislead."""

    kind: str
    element: Element
    detail: str = ""

    def __str__(self) -> str:
        x, y = self.element.center
        return f"{self.kind:20} {self.element.name[:42]!r:46} ({x},{y})  {self.detail}"


def describe(node: Node | None) -> str:
    """A node in a few words: its short id, or its class, plus how it is flagged."""
    if node is None:
        return "nothing"
    flags = [
        name
        for name in ("clickable", "long_clickable", "checkable", "scrollable", "focusable")
        if getattr(node, name)
    ]
    name = node.short_id or node.class_name.rpartition(".")[2]
    return f"{name}[{','.join(flags) or '-'}]"


def relation(tree: Tree, element_node: Node, other: Node) -> str:
    """How ``other`` stands to ``element_node``: its descendant, its ancestor, or unrelated."""

    def contains(parent: Node, child: Node) -> bool:
        return any(c is child or contains(c, child) for c in parent.children)

    if contains(element_node, other):
        return "descendant"
    if contains(other, element_node):
        return "ancestor"
    return "unrelated"


def screen_of(tree: Tree) -> Bounds | None:
    """The screen's rectangle: the bounds of the first window."""
    return tree.roots[0].bounds if tree.roots else None


def findings(tree: Tree) -> list[Finding]:
    """Everything about this tree's elements that could mislead an agent tapping them."""
    screen = screen_of(tree)
    elements = tree.interactive_elements()
    found: list[Finding] = []

    for element in elements:
        node = element.node
        x, y = element.center
        if screen is not None and not screen.contains(x, y):
            found.append(Finding("off_screen", element, f"screen is {screen}"))
        if not element.bounds.contains(x, y):
            found.append(Finding("outside_own_bounds", element, str(element.bounds)))

        if not takes_taps(node):
            found.append(
                Finding("not_a_tap_target", element, f"listed as {describe(node)}, not tappable")
            )
            continue

        target = tree.tap_target(x, y)
        if target is node:
            continue
        if target is None:
            found.append(Finding("tap_misses", element, "no node at the point handles the tap"))
            continue
        how = relation(tree, node, target)
        if how == "descendant":
            continue  # a part of the element (its own button, say) takes the tap: still grounded
        found.append(
            Finding("tap_goes_elsewhere", element, f"{describe(target)} ({how}) takes it instead")
        )

    by_point: dict[tuple[int, int], list[Element]] = {}
    for element in elements:
        by_point.setdefault(element.center, []).append(element)
    for point, sharing in by_point.items():
        if len(sharing) > 1:
            names = ", ".join(repr(e.name[:24]) for e in sharing)
            for element in sharing:
                found.append(Finding("shared_point", element, f"{len(sharing)} elements: {names}"))
    return found


def hard(items: list[Finding]) -> list[Finding]:
    """The findings that mean a tap will not do what the table promises."""
    return [item for item in items if item.kind in HARD]


def summary(items: list[Finding], total: int) -> str:
    """A count per kind, for a report."""
    counts = {kind: sum(1 for i in items if i.kind == kind) for kind in (*HARD, *SOFT)}
    parts = ", ".join(f"{kind}={n}" for kind, n in counts.items() if n)
    return f"{total} elements; " + (parts or "no findings")
