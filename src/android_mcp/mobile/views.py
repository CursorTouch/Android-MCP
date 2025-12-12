from dataclasses import dataclass
from android_mcp.tree.views import TreeState
from PIL.Image import Image
from typing import Literal

@dataclass
class App:
    name:str
    status:Literal['Maximized','Minimized']

@dataclass
class MobileState:
    tree_state:TreeState
    screenshot:bytes|str|Image|None