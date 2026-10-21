"""UI tree: reads the screen through :mod:`android_mcp.adb` and finds what can be tapped.

Usage:
    import android_mcp.tree as tree

    for element in tree.get_elements():
        print(element.name, element.center)
"""

from .service import (
    element_name,
    find_nodes,
    get_elements,
    interactive_elements,
    is_interactive,
    parse_hierarchy,
)
from .views import Bounds, Element, Node

__all__ = [
    "Bounds",
    "Element",
    "Node",
    "element_name",
    "find_nodes",
    "get_elements",
    "interactive_elements",
    "is_interactive",
    "parse_hierarchy",
]
