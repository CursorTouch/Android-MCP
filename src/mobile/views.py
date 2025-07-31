from dataclasses import dataclass
from src.tree.views import TreeState
from typing import Literal

@dataclass
class App:
    name:str
    status:Literal['Maximized','Minimized']

@dataclass
class MobileState:
    tree_state:TreeState
    screenshot:bytes|None