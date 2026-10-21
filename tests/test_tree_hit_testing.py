"""Tests for the Tree class's hit testing: which node a tap at a point reaches.

Android gives a touch to the view drawn on top at that point and, if that view does not handle
taps, to its parent, and so on up. The tree reproduces that from the dump so a caller can check
that the point it is about to tap really lands on the element it means.
"""

import pathlib
from xml.sax.saxutils import quoteattr

import pytest

from android_mcp.tree import Bounds, Element, Node, Tree, takes_taps

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _node(class_name="android.view.View", bounds="[0,0][100,100]", children=(), **attributes):
    """Write one ``<node>``. Keyword names use underscores: ``long_clickable`` is long-clickable."""
    attributes = {"class": class_name, "bounds": bounds} | {
        name.replace("_", "-"): value for name, value in attributes.items()
    }
    rendered = " ".join(f"{name}={quoteattr(str(value))}" for name, value in attributes.items())
    return f"<node {rendered}>{''.join(children)}</node>"


def _tree(*nodes, rotation=0):
    xml = f'<?xml version="1.0"?><hierarchy rotation="{rotation}">{"".join(nodes)}</hierarchy>'
    return Tree.from_xml(xml)


def _id(node):
    """A node's short resource id, which the tests use as its name."""
    return node.short_id if node is not None else None


@pytest.mark.unit
class TestBoundsContains:
    """Tests for Bounds.contains."""

    def test_inside(self):
        """A point strictly inside."""
        assert Bounds(10, 20, 110, 220).contains(50, 100)

    @pytest.mark.parametrize(
        ("x", "y", "inside"),
        [
            (10, 20, True),  # top-left pixel is in
            (109, 219, True),  # the last pixel is in
            (110, 100, False),  # right edge is outside: pixels are numbered from 0
            (50, 220, False),  # bottom edge is outside
            (9, 100, False),
            (50, 19, False),
        ],
    )
    def test_edges(self, x, y, inside):
        """``[10,20][110,220]`` covers pixels 10..109 by 20..219."""
        assert Bounds(10, 20, 110, 220).contains(x, y) is inside

    def test_the_centre_of_a_box_is_inside_it(self):
        """The tap point of an element is always within its own bounds, for odd and even sizes."""
        for box in (
            Bounds(0, 0, 1, 1),
            Bounds(0, 0, 2, 2),
            Bounds(5, 7, 12, 30),
            Bounds(-5, 0, 5, 9),
        ):
            assert box.contains(*box.center), box


@pytest.mark.unit
class TestTreeBasics:
    """Tests for building a Tree and walking it."""

    def test_rotation_comes_from_the_dump(self):
        """The hierarchy's rotation attribute is kept."""
        assert _tree(_node(), rotation=0).rotation == 0
        assert _tree(_node(), rotation=1).rotation == 1

    def test_rotation_defaults_to_upright(self):
        """A dump with no rotation attribute is upright."""
        assert Tree.from_xml("<hierarchy/>").rotation == 0

    def test_an_empty_tree(self):
        """No windows: no nodes, nothing at any point."""
        tree = Tree()

        assert list(tree.nodes()) == []
        assert tree.node_at(5, 5) is None
        assert tree.tap_target(5, 5) is None
        assert tree.interactive_elements() == []

    def test_nodes_are_parents_before_children_in_document_order(self):
        """A pre-order walk, which is also back-to-front drawing order."""
        tree = _tree(
            _node(
                resource_id="a",
                children=[
                    _node(resource_id="a1", children=[_node(resource_id="a1x")]),
                    _node(resource_id="a2"),
                ],
            ),
            _node(resource_id="b"),
        )

        assert [n.short_id for n in tree.nodes()] == ["a", "a1", "a1x", "a2", "b"]

    def test_elements_carry_their_node(self):
        """An element made from a tree can be traced back to its node."""
        tree = _tree(_node(text="OK", clickable="true", resource_id="x:id/ok"))

        (element,) = tree.interactive_elements()

        assert isinstance(element.node, Node)
        assert element.node.resource_id == "x:id/ok"

    def test_the_node_does_not_affect_equality_or_repr(self):
        """Two elements that look the same are equal, with or without a node."""
        bounds = Bounds(0, 0, 10, 10)
        with_node = Element("OK", "Button", "ok", bounds, Node("Button", bounds))

        assert with_node == Element("OK", "Button", "ok", bounds)
        assert "node" not in repr(with_node)


@pytest.mark.unit
class TestTakesTaps:
    """Tests for takes_taps: which nodes handle a tap themselves."""

    @staticmethod
    def _make(**flags):
        return _tree(_node(**flags)).roots[0]

    @pytest.mark.parametrize("flag", ["clickable", "long_clickable", "checkable"])
    def test_these_flags_take_taps(self, flag):
        """A node flagged clickable, long-clickable or checkable handles a tap."""
        assert takes_taps(self._make(**{flag: "true"}))

    @pytest.mark.parametrize(
        "class_name",
        ["android.widget.EditText", "android.widget.Button", "android.widget.Spinner"],
    )
    def test_text_fields_and_buttons_take_taps_even_when_not_flagged(self, class_name):
        """A tap focuses a field or presses a button whatever uiautomator says."""
        assert takes_taps(self._make(class_name=class_name))

    @pytest.mark.parametrize("flag", ["scrollable", "focusable", "selected", "enabled"])
    def test_these_flags_alone_do_not(self, flag):
        """A scrolling list's empty space, or a focusable label, does nothing when tapped."""
        assert not takes_taps(self._make(**{flag: "true"}))

    def test_plain_view_does_not(self):
        """A bare view handles nothing."""
        assert not takes_taps(self._make())


@pytest.mark.unit
class TestNodeAt:
    """Tests for node_at: the node drawn on top at a point."""

    def test_a_point_on_no_node(self):
        """Outside every window."""
        assert _tree(_node(bounds="[0,0][100,100]")).node_at(500, 500) is None

    def test_the_child_is_on_top_of_its_parent(self):
        """Children are drawn after parents."""
        tree = _tree(
            _node(
                resource_id="parent", children=[_node(resource_id="child", bounds="[10,10][50,50]")]
            )
        )

        assert _id(tree.node_at(20, 20)) == "child"
        assert _id(tree.node_at(80, 80)) == "parent"

    def test_a_later_sibling_is_on_top_of_an_earlier_one(self):
        """Where two siblings overlap, the one listed last wins."""
        tree = _tree(
            _node(
                children=[
                    _node(resource_id="under", bounds="[0,0][60,60]"),
                    _node(resource_id="over", bounds="[40,40][100,100]"),
                ]
            )
        )

        assert _id(tree.node_at(50, 50)) == "over"
        assert _id(tree.node_at(10, 10)) == "under"
        assert _id(tree.node_at(90, 90)) == "over"

    def test_a_later_window_is_on_top_of_an_earlier_one(self):
        """A dialog listed after the activity covers it."""
        tree = _tree(
            _node(resource_id="activity", bounds="[0,0][100,100]"),
            _node(resource_id="dialog", bounds="[20,20][80,80]"),
        )

        assert _id(tree.node_at(50, 50)) == "dialog"
        assert _id(tree.node_at(5, 5)) == "activity"

    def test_the_last_in_document_order_wins_even_in_another_branch(self):
        """A deep node in an earlier branch is under a later branch's node."""
        tree = _tree(
            _node(
                children=[
                    _node(
                        resource_id="left",
                        children=[_node(resource_id="left_deep", bounds="[0,0][100,100]")],
                    ),
                    _node(resource_id="right", bounds="[0,0][100,100]"),
                ]
            )
        )

        assert _id(tree.node_at(50, 50)) == "right"

    def test_right_and_bottom_edges_are_outside(self):
        """A node ``[0,0][100,100]`` is not under pixel (100, 50)."""
        tree = _tree(_node(resource_id="box", bounds="[0,0][100,100]"))

        assert _id(tree.node_at(99, 99)) == "box"
        assert tree.node_at(100, 50) is None
        assert tree.node_at(50, 100) is None


@pytest.mark.unit
class TestTapTarget:
    """Tests for tap_target: the node that handles a tap."""

    def test_a_clickable_node_handles_its_own_tap(self):
        """The simplest case."""
        tree = _tree(_node(resource_id="button", clickable="true"))

        assert _id(tree.tap_target(50, 50)) == "button"

    def test_a_label_inside_a_clickable_row_passes_the_tap_up_to_the_row(self):
        """Tapping the text of a list row taps the row."""
        tree = _tree(
            _node(
                resource_id="row",
                clickable="true",
                children=[
                    _node("android.widget.TextView", resource_id="label", bounds="[10,10][90,40]")
                ],
            )
        )

        assert _id(tree.node_at(20, 20)) == "label"
        assert _id(tree.tap_target(20, 20)) == "row"

    def test_a_clickable_child_takes_the_tap_before_its_clickable_parent(self):
        """A button on a clickable card is the one pressed."""
        tree = _tree(
            _node(
                resource_id="card",
                clickable="true",
                children=[_node(resource_id="button", clickable="true", bounds="[10,10][50,50]")],
            )
        )

        assert _id(tree.tap_target(20, 20)) == "button"
        assert _id(tree.tap_target(80, 80)) == "card"

    def test_nothing_clickable_up_the_chain_means_nothing_handles_it(self):
        """A tap on bare layout does nothing."""
        tree = _tree(_node(resource_id="root", children=[_node(resource_id="label")]))

        assert tree.tap_target(50, 50) is None

    def test_a_transparent_overlay_lets_the_tap_through_to_what_is_beneath(self):
        """A later sibling that does not handle taps is seen on top, but the tap reaches the button.

        Android offers a touch to each child from the top down and the first that handles it
        takes it, so a layout drawn over a button does not block the button.
        """
        tree = _tree(
            _node(
                resource_id="screen",
                children=[
                    _node(resource_id="button", clickable="true", bounds="[0,0][100,100]"),
                    _node(resource_id="scrim", bounds="[0,0][100,100]"),
                ],
            )
        )

        assert _id(tree.node_at(50, 50)) == "scrim"
        assert _id(tree.tap_target(50, 50)) == "button"

    def test_a_parent_handles_the_tap_only_when_no_child_does(self):
        """Children get the first chance; the clickable parent gets what they pass up."""
        tree = _tree(
            _node(
                resource_id="card",
                clickable="true",
                children=[_node(resource_id="label", bounds="[0,0][50,50]")],
            )
        )

        assert _id(tree.tap_target(25, 25)) == "card"

    def test_a_clickable_overlay_takes_the_tap_from_what_is_under_it(self):
        """A dialog scrim that dismisses on tap gets the tap, not the button beneath."""
        tree = _tree(
            _node(
                children=[
                    _node(resource_id="button", clickable="true", bounds="[0,0][100,100]"),
                    _node(resource_id="scrim", clickable="true", bounds="[0,0][100,100]"),
                ]
            )
        )

        assert _id(tree.tap_target(50, 50)) == "scrim"

    def test_a_scrolling_container_does_not_take_taps_on_its_empty_space(self):
        """Being scrollable is not being tappable."""
        tree = _tree(_node(resource_id="list", scrollable="true"))

        assert tree.node_at(50, 50) is not None
        assert tree.tap_target(50, 50) is None

    def test_a_text_field_takes_the_tap_without_being_flagged_clickable(self):
        """A tap on an EditText focuses it."""
        tree = _tree(_node("android.widget.EditText", resource_id="field"))

        assert _id(tree.tap_target(50, 50)) == "field"

    def test_a_point_on_no_node(self):
        """Off the screen's windows there is nothing to tap."""
        assert _tree(_node(clickable="true")).tap_target(900, 900) is None


@pytest.mark.unit
class TestOnRealDumps:
    """Hit testing on the dumps captured from an Android 15 emulator."""

    @staticmethod
    def _load(name):
        return Tree.from_xml((FIXTURES / name).read_text(encoding="utf-8"))

    def test_the_contact_form_fields_are_reached_by_their_own_centres(self):
        """Every text field takes a tap at its centre itself."""
        tree = self._load("contacts_form.xml")
        fields = [e for e in tree.interactive_elements() if e.class_name.endswith("EditText")]

        assert len(fields) == 6
        for field in fields:
            assert tree.tap_target(*field.center) is field.node, field.name

    def test_the_launcher_search_bar_icons_are_reached_by_their_own_centres(self):
        """The voice and lens buttons inside the search bar are not hidden by the bar."""
        tree = self._load("launcher.xml")
        by_name = {e.name: e for e in tree.interactive_elements()}

        for name in ("Voice search", "Google Lens", "Google app"):
            element = by_name[name]
            assert tree.tap_target(*element.center) is element.node, name

    def test_the_whole_workspace_container_is_not_a_tap_target(self):
        """The scrolling workspace is listed, but a tap at its centre reaches nothing."""
        tree = self._load("launcher.xml")
        workspace = next(e for e in tree.interactive_elements() if e.resource_id == "workspace")

        assert tree.tap_target(*workspace.center) is not workspace.node
