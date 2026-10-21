"""Tests for the UI tree: parsing a uiautomator dump and finding the interactive elements."""

import pathlib
from xml.etree.ElementTree import ParseError
from xml.sax.saxutils import quoteattr

import pytest

import android_mcp.tree as tree
from android_mcp.tree import Bounds, Node
from android_mcp.tree.config import INTERACTIVE_CLASSES

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _roots(xml):
    """The root nodes of the tree dumped in ``xml``."""
    return list(tree.Tree.from_xml(xml).roots)


def _elements_of(roots):
    return tree.Tree(roots).interactive_elements()


def _find_nodes(roots, **criteria):
    return tree.Tree(roots).find(**criteria)


def _node(class_name="android.view.View", bounds="[0,0][100,100]", children=(), **attributes):
    """Write one ``<node>``. Keyword names use underscores: ``content_desc`` is content-desc."""
    attributes = {"class": class_name, "bounds": bounds} | {
        name.replace("_", "-"): value for name, value in attributes.items()
    }
    rendered = " ".join(f"{name}={quoteattr(str(value))}" for name, value in attributes.items())
    return f"<node {rendered}>{''.join(children)}</node>"


def _hierarchy(*nodes):
    return "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">" + (
        "".join(nodes) + "</hierarchy>"
    )


def _elements(*nodes):
    return _elements_of(_roots(_hierarchy(*nodes)))


def _named(*nodes):
    return [element.name for element in _elements(*nodes)]


@pytest.mark.unit
class TestBounds:
    """Tests for Bounds."""

    def test_parse(self):
        """The ``[left,top][right,bottom]`` form is read into four numbers."""
        assert Bounds.parse("[10,20][110,220]") == Bounds(10, 20, 110, 220)

    def test_parse_allows_negative_coordinates(self):
        """A view partly off screen has negative coordinates."""
        assert Bounds.parse("[-30,0][50,100]") == Bounds(-30, 0, 50, 100)

    @pytest.mark.parametrize("text", ["", "[0,0]", "[a,b][c,d]", "0,0,1,1", "[0,0][1,1] extra"])
    def test_parse_rejects_anything_else(self, text):
        """A string that is not a bounds pair raises, naming it."""
        with pytest.raises(ValueError, match="not a bounds string"):
            Bounds.parse(text)

    def test_size_and_center(self):
        """Width, height and the pixel to tap."""
        bounds = Bounds(10, 20, 111, 221)

        assert (bounds.width, bounds.height) == (101, 201)
        assert bounds.center == (60, 120)

    @pytest.mark.parametrize(
        ("bounds", "empty"),
        [
            (Bounds(0, 0, 100, 100), False),
            (Bounds(0, 0, 0, 0), True),
            (Bounds(5, 5, 5, 50), True),  # no width
            (Bounds(5, 5, 50, 5), True),  # no height
            (Bounds(50, 50, 5, 5), True),  # inverted
        ],
    )
    def test_is_empty(self, bounds, empty):
        """Nothing can be tapped inside a rectangle without width or height."""
        assert bounds.is_empty is empty


@pytest.mark.unit
class TestParseHierarchy:
    """Tests for Tree.from_xml."""

    def test_reads_attributes(self):
        """Text, ids, class, package, bounds and every flag come through."""
        xml = _hierarchy(
            _node(
                "android.widget.Button",
                "[1,2][3,4]",
                package="com.example",
                resource_id="com.example:id/ok",
                text="OK",
                content_desc="Confirm",
                hint="hint text",
                clickable="true",
                long_clickable="true",
                checkable="true",
                checked="true",
                enabled="false",
                focusable="true",
                focused="true",
                scrollable="true",
                selected="true",
                password="true",
            )
        )

        (node,) = _roots(xml)

        assert node == Node(
            class_name="android.widget.Button",
            bounds=Bounds(1, 2, 3, 4),
            package="com.example",
            resource_id="com.example:id/ok",
            text="OK",
            content_desc="Confirm",
            hint="hint text",
            clickable=True,
            long_clickable=True,
            checkable=True,
            checked=True,
            enabled=False,
            focusable=True,
            focused=True,
            scrollable=True,
            selected=True,
            password=True,
        )

    def test_missing_attributes_take_defaults(self):
        """A bare node is enabled and nothing else."""
        (node,) = _roots(_hierarchy(_node()))

        assert node.enabled is True
        assert not any(
            [node.clickable, node.long_clickable, node.checkable, node.checked, node.focusable]
        )
        assert (node.text, node.content_desc, node.hint, node.resource_id) == ("", "", "", "")

    def test_one_root_per_window(self):
        """Several windows on screen give several roots, in order."""
        roots = _roots(_hierarchy(_node(text="a"), _node(text="b")))

        assert [root.text for root in roots] == ["a", "b"]

    def test_children_nest_in_document_order(self):
        """Children hang off their parent, in the order the dump lists them."""
        xml = _hierarchy(
            _node(
                text="root",
                children=[_node(text="a", children=[_node(text="a1")]), _node(text="b")],
            )
        )

        (root,) = _roots(xml)

        assert [child.text for child in root.children] == ["a", "b"]
        assert [child.text for child in root.children[0].children] == ["a1"]

    def test_empty_hierarchy(self):
        """A screen with no windows has no roots."""
        assert _roots(_hierarchy()) == []

    def test_attribute_text_is_unescaped(self):
        """XML entities in text and descriptions are decoded."""
        (node,) = _roots(_hierarchy(_node(text="Fish & Chips <3", content_desc='"q"')))

        assert (node.text, node.content_desc) == ("Fish & Chips <3", '"q"')

    @pytest.mark.parametrize(
        ("resource_id", "short"),
        [
            ("com.google.android.apps.nexuslauncher:id/workspace", "workspace"),
            ("android:id/title", "title"),
            ("plain", "plain"),
            ("", ""),
        ],
    )
    def test_short_id(self, resource_id, short):
        """The package prefix is dropped from a resource id."""
        (node,) = _roots(_hierarchy(_node(resource_id=resource_id)))

        assert node.short_id == short

    def test_malformed_xml_raises(self):
        """Text that is not XML raises the parser's error."""
        with pytest.raises(ParseError):
            _roots("<hierarchy><node")

    def test_bad_bounds_raises(self):
        """A node whose bounds cannot be read raises instead of being guessed at."""
        with pytest.raises(ValueError, match="not a bounds string"):
            _roots(_hierarchy(_node(bounds="nope")))


@pytest.mark.unit
class TestIsInteractive:
    """Tests for is_interactive."""

    @staticmethod
    def _make(**flags):
        return _roots(_hierarchy(_node(**flags)))[0]

    @pytest.mark.parametrize(
        "flag",
        [
            "focusable",
            "clickable",
            "long_clickable",
            "checkable",
            "scrollable",
            "selected",
            "password",
        ],
    )
    def test_each_flag_makes_a_node_interactive(self, flag):
        """Any one of these flags is enough."""
        assert tree.is_interactive(self._make(**{flag: "true"}))

    @pytest.mark.parametrize("class_name", sorted(INTERACTIVE_CLASSES))
    def test_interactive_classes(self, class_name):
        """Widgets such as buttons and text fields count even with no flags set."""
        assert tree.is_interactive(self._make(class_name=class_name))

    def test_plain_view_is_not_interactive(self):
        """A view that is not flagged and not a control is just layout."""
        assert not tree.is_interactive(self._make(class_name="android.widget.TextView", text="hi"))

    def test_checked_alone_is_not_enough(self):
        """``checked`` says what state a control is in, not that there is one."""
        assert not tree.is_interactive(self._make(checked="true"))


@pytest.mark.unit
class TestElementName:
    """Tests for element_name."""

    @staticmethod
    def _name(*nodes):
        return tree.element_name(_roots(_hierarchy(*nodes))[0])

    def test_content_description_wins_over_text(self):
        """A content description is what accessibility reads out, so it comes first."""
        assert self._name(_node(text="Text", content_desc="Description")) == "Description"

    def test_text(self):
        """With no description, the text is the name."""
        assert self._name(_node(text="Text")) == "Text"

    def test_own_text_wins_over_children(self):
        """Children are only read when the node has nothing of its own."""
        assert self._name(_node(text="Row", children=[_node(text="Child")])) == "Row"

    def test_joins_the_text_of_children(self):
        """A row with no text of its own reads as its labels, in order."""
        row = _node(children=[_node(text="Title"), _node(children=[_node(text="Subtitle")])])

        assert self._name(row) == "Title Subtitle"

    def test_hint_is_used_last(self):
        """An empty field is named by its hint."""
        assert self._name(_node(hint="Search")) == "Search"

    def test_text_beats_content_desc_beats_hint_among_children(self):
        """Each child contributes one value: text, else description, else hint."""
        row = _node(
            children=[
                _node(text="t", content_desc="d", hint="h"),
                _node(content_desc="d2", hint="h2"),
                _node(hint="h3"),
            ]
        )

        assert self._name(row) == "t d2 h3"

    def test_actionable_child_is_skipped_when_there_is_other_text(self):
        """A button inside a row is listed itself, so its label is not repeated in the row's."""
        row = _node(children=[_node(text="Label"), _node(text="Delete", clickable="true")])

        assert self._name(row) == "Label"

    def test_actionable_child_is_the_fallback(self):
        """A row with no other text takes the labels of the controls inside it."""
        row = _node(
            children=[_node(text="Yes", clickable="true"), _node(text="No", checkable="true")]
        )

        assert self._name(row) == "Yes No"

    def test_does_not_look_inside_an_actionable_child(self):
        """What is nested in a control belongs to that control."""
        row = _node(children=[_node(clickable="true", children=[_node(text="Inner")])])

        assert self._name(row) == ""

    def test_nothing_to_read(self):
        """A node with no text anywhere has no name."""
        assert self._name(_node(children=[_node()])) == ""

    def test_result_is_stripped(self):
        """Padding from the text of children does not leak out."""
        assert self._name(_node(children=[_node(text="  Hi  ")])) == "Hi"


@pytest.mark.unit
class TestInteractiveElements:
    """Tests for interactive_elements."""

    def test_builds_an_element(self):
        """Name, class, short id and tap point of a button."""
        (element,) = _elements(
            _node(
                "android.widget.Button",
                "[100,200][300,400]",
                resource_id="com.x:id/save",
                text="Save",
                clickable="true",
            )
        )

        assert (element.name, element.class_name, element.resource_id) == (
            "Save",
            "android.widget.Button",
            "save",
        )
        assert element.bounds == Bounds(100, 200, 300, 400)
        assert element.center == (200, 300)

    def test_skips_layout_that_nobody_can_use(self):
        """A named view with no flags and no control class is not interactive."""
        assert _named(_node("android.widget.TextView", text="Just text")) == []

    def test_skips_disabled_nodes(self):
        """A disabled control is not offered."""
        assert _named(_node(text="Off", clickable="true", enabled="false")) == []

    def test_a_disabled_parent_does_not_hide_an_enabled_child(self):
        """Only the node's own enabled flag counts."""
        parent = _node(enabled="false", children=[_node(text="Inside", clickable="true")])

        assert _named(parent) == ["Inside"]

    def test_skips_nodes_with_no_name(self):
        """A clickable view with no text cannot be told apart, so it is left out."""
        assert _named(_node(clickable="true")) == []

    @pytest.mark.parametrize("bounds", ["[0,0][0,0]", "[10,10][10,50]", "[10,10][50,10]"])
    def test_skips_nodes_with_no_area(self, bounds):
        """A node that has no width or height cannot be tapped."""
        assert _named(_node(bounds=bounds, text="Ghost", clickable="true")) == []

    def test_parents_come_before_children_in_document_order(self):
        """The list follows the dump: a parent, then its subtree, then its sibling."""
        xml = [
            _node(
                text="A",
                clickable="true",
                children=[_node(text="A1", clickable="true"), _node(text="A2", clickable="true")],
            ),
            _node(text="B", clickable="true"),
        ]

        assert _named(*xml) == ["A", "A1", "A2", "B"]

    def test_covers_every_window(self):
        """Elements from all roots are returned."""
        assert _named(_node(text="One", clickable="true"), _node(text="Two", clickable="true")) == [
            "One",
            "Two",
        ]

    def test_nested_interactive_nodes_are_each_listed(self):
        """A clickable row and the clickable button inside it are both elements."""
        row = _node(clickable="true", children=[_node(text="Open", clickable="true")])

        assert _named(row) == ["Open", "Open"]


@pytest.mark.unit
class TestFindNodes:
    """Tests for Tree.find."""

    @staticmethod
    def _find(*nodes, **criteria):
        return _find_nodes(_roots(_hierarchy(*nodes)), **criteria)

    def test_no_criteria_is_an_error(self):
        """Matching everything is never what a caller meant."""
        with pytest.raises(ValueError, match="at least one"):
            self._find(_node())

    @pytest.mark.parametrize("blank", ["", None])
    def test_blank_criteria_count_as_not_given(self, blank):
        """A blank selector, as a client may send for an unset field, is ignored."""
        with pytest.raises(ValueError, match="at least one"):
            self._find(_node(), text=blank, description=blank)

        found = self._find(_node(text="Hi"), text="Hi", resource_id=blank)
        assert [n.text for n in found] == ["Hi"]

    def test_text_is_an_exact_match(self):
        """Part of a text is not a match."""
        nodes = [_node(text="Save"), _node(text="Save as"), _node(text="save")]

        assert [n.text for n in self._find(*nodes, text="Save")] == ["Save"]

    def test_description_matches_the_content_description(self):
        """Not the text."""
        nodes = [_node(content_desc="Close", text="x"), _node(text="Close")]

        found = self._find(*nodes, description="Close")

        assert [(n.content_desc, n.text) for n in found] == [("Close", "x")]

    def test_class_name(self):
        """The full class name is compared."""
        nodes = [_node("android.widget.Button"), _node("android.widget.ImageButton")]

        found = self._find(*nodes, class_name="android.widget.Button")

        assert [n.class_name for n in found] == ["android.widget.Button"]

    def test_short_resource_id_matches_any_package(self):
        """``save`` finds ``com.a:id/save`` and ``com.b:id/save``, but not ``com.a:id/save_all``."""
        nodes = [
            _node(resource_id="com.a:id/save"),
            _node(resource_id="com.b:id/save"),
            _node(resource_id="com.a:id/save_all"),
        ]

        found = self._find(*nodes, resource_id="save")

        assert [n.resource_id for n in found] == ["com.a:id/save", "com.b:id/save"]

    @pytest.mark.parametrize("given", ["com.a:id/save", "com.a:save", "a/save"])
    def test_full_resource_id_must_match_in_full(self, given):
        """A value with a package part is compared against the whole id."""
        nodes = [_node(resource_id="com.a:id/save"), _node(resource_id="com.b:id/save")]

        found = self._find(*nodes, resource_id=given)

        assert [n.resource_id for n in found] == (
            ["com.a:id/save"] if given == "com.a:id/save" else []
        )

    def test_every_criterion_must_match(self):
        """Criteria are combined with AND."""
        nodes = [
            _node("android.widget.Button", text="OK"),
            _node("android.widget.TextView", text="OK"),
            _node("android.widget.Button", text="Cancel"),
        ]

        found = self._find(*nodes, text="OK", class_name="android.widget.Button")

        assert [(n.class_name, n.text) for n in found] == [("android.widget.Button", "OK")]

    def test_finds_nodes_that_are_not_interactive(self):
        """A plain label can be found, unlike in the interactive-element list."""
        found = self._find(_node("android.widget.TextView", text="Just text"), text="Just text")

        assert len(found) == 1

    def test_finds_nested_nodes_in_document_order(self):
        """Parents are listed before their children, and siblings in order."""
        xml = _node(
            text="Row",
            children=[_node(text="Row", resource_id="a"), _node(text="Row", resource_id="b")],
        )

        found = self._find(xml, text="Row")

        assert [n.short_id for n in found] == ["", "a", "b"]

    def test_skips_nodes_with_no_area(self):
        """A node with no width or height is not on screen."""
        nodes = [_node(text="Ghost", bounds="[5,5][5,50]"), _node(text="Ghost")]

        assert len(self._find(*nodes, text="Ghost")) == 1

    def test_finds_disabled_nodes(self):
        """The caller asked for it by name; whether it can be tapped is theirs to judge."""
        assert len(self._find(_node(text="Off", enabled="false"), text="Off")) == 1

    def test_nothing_matches(self):
        """No match is an empty list, not an error."""
        assert self._find(_node(text="a"), text="b") == []

    def test_covers_every_window(self):
        """Matches from all roots are returned."""
        found = self._find(_node(text="x"), _node(text="x"), text="x")

        assert len(found) == 2

    def test_on_a_real_dump(self):
        """Selectors find what the launcher dump contains."""
        xml = (FIXTURES / "launcher.xml").read_text(encoding="utf-8")
        roots = _roots(xml)

        by_id = _find_nodes(roots, resource_id="search_container_hotseat")
        by_desc = _find_nodes(roots, description="Voice search")
        by_text = _find_nodes(roots, text="Gmail", class_name="android.widget.TextView")

        assert [n.bounds.center for n in by_id] == [(540, 2207)]
        assert [n.bounds.center for n in by_desc] == [(790, 2207)]
        # Two icons are labelled "Gmail": the one on the workspace and the predicted app below.
        assert [n.bounds.center for n in by_text] == [(416, 1619), (910, 1970)]


LAUNCHER = [
    ("At a glance Gmail Photos YouTube", "android.widget.ScrollView", "workspace", 540, 1200),
    ("At a glance", "androidx.viewpager.widget.ViewPager", "smartspace_card_pager", 540, 359),
    ("Tue, Oct 20", "android.view.ViewGroup", "base_template_card_with_date", 540, 359),
    ("Tue, Oct 20", "android.widget.TextView", "date", 215, 353),
    ("Gmail", "android.widget.TextView", "", 416, 1619),
    ("Photos", "android.widget.TextView", "", 663, 1619),
    ("YouTube", "android.widget.TextView", "", 910, 1619),
    ("Phone", "android.widget.TextView", "", 169, 1970),
    ("Messages", "android.widget.TextView", "", 416, 1970),
    ("Chrome", "android.widget.TextView", "", 663, 1970),
    ("Predicted app: Gmail", "android.widget.TextView", "", 910, 1970),
    ("Google search", "android.widget.FrameLayout", "search_container_hotseat", 540, 2207),
    ("Google app", "android.widget.ImageView", "g_icon", 164, 2207),
    ("Voice search", "android.widget.ImageView", "mic_icon", 790, 2207),
    ("Google Lens", "android.widget.ImageButton", "lens_icon", 916, 2207),
]

CONTACTS_FORM = [
    ("Cancel", "android.widget.ImageButton", "", 73, 211),
    ("Save", "android.widget.Button", "toolbar_button", 838, 211),
    ("More options", "android.widget.ImageView", "action_bar_overflow_menu", 1017, 211),
    (
        "Add contact photo Add picture First name Last name Company Phone Mobile Show dropdown "
        "menu Email Home Show dropdown menu Significant date Show date picker",
        "android.widget.ScrollView",
        "contact_editor_scroller",
        540,
        1316,
    ),
    ("Add contact photo", "android.widget.FrameLayout", "photo_update_clickable", 539, 506),
    ("Add picture", "android.widget.Button", "button_change_photo", 539, 727),
    ("First name", "android.widget.EditText", "", 535, 935),
    ("Last name", "android.widget.EditText", "", 535, 1125),
    ("Show more name fields", "android.widget.FrameLayout", "expansion_view_container", 1006, 916),
    ("Company", "android.widget.EditText", "", 535, 1336),
    ("Phone", "android.widget.EditText", "", 535, 1547),
    ("Mobile Phone", "android.widget.Spinner", "", 361, 1737),
    ("Show dropdown menu", "android.widget.ImageButton", "text_input_end_icon", 523, 1737),
    ("Email", "android.widget.EditText", "", 535, 1953),
    ("Home Email", "android.widget.Spinner", "", 347, 2143),
    ("Show dropdown menu", "android.widget.ImageButton", "text_input_end_icon", 494, 2143),
    ("Significant date", "android.widget.EditText", "", 535, 2309),
    ("Show date picker", "android.widget.ImageButton", "text_input_end_icon", 870, 2316),
]


def _summary(elements):
    return [(e.name, e.class_name, e.resource_id, *e.center) for e in elements]


@pytest.mark.unit
class TestRealDumps:
    """Tests against dumps captured from an Android 15 emulator.

    The expected lists are what the original Android-MCP's tree code returned for the same XML.
    """

    @pytest.mark.parametrize(
        ("fixture", "expected"),
        [("launcher.xml", LAUNCHER), ("contacts_form.xml", CONTACTS_FORM)],
    )
    def test_matches_the_original(self, fixture, expected):
        """The same elements come out, with the same names, ids and tap points."""
        xml = (FIXTURES / fixture).read_text(encoding="utf-8")

        elements = _elements_of(_roots(xml))

        assert _summary(elements) == expected

    def test_every_element_can_be_tapped(self):
        """Each tap point lies inside its element's bounds, on a 1080x2400 screen."""
        xml = (FIXTURES / "contacts_form.xml").read_text(encoding="utf-8")

        for element in _elements_of(_roots(xml)):
            x, y = element.center
            assert element.bounds.left <= x <= element.bounds.right
            assert element.bounds.top <= y <= element.bounds.bottom
            assert 0 <= x < 1080 and 0 <= y < 2400


@pytest.mark.unit
class TestGetElements:
    """Tests for Tree.read."""

    def test_reads_the_device_and_returns_its_elements(self, monkeypatch):
        """The dump comes from the adb layer, for the device asked about."""
        seen = {}

        def fake_dump(*, serial=None):
            seen["serial"] = serial
            return (FIXTURES / "launcher.xml").read_text(encoding="utf-8")

        monkeypatch.setattr(tree.service.adb, "dump_hierarchy", fake_dump)

        elements = tree.Tree.read("emulator-5554").interactive_elements()

        assert seen["serial"] == "emulator-5554"
        assert _summary(elements) == LAUNCHER
