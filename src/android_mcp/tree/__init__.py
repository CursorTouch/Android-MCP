"""UI tree: reads the screen through :mod:`android_mcp.adb` and finds what can be tapped.

Usage:
    from android_mcp.tree import Tree

    tree = Tree.read()
    for element in tree.interactive_elements():
        print(element.name, element.center)
    node = tree.tap_target(540, 1200)  # what a tap there would reach
"""

from .service import Tree, element_name, is_interactive, takes_taps
from .views import Bounds, Element, Node

__all__ = [
    "Bounds",
    "Element",
    "Node",
    "Tree",
    "element_name",
    "is_interactive",
    "takes_taps",
]
