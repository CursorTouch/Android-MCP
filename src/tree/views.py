from dataclasses import dataclass

@dataclass
class ElementNode:
    name: str
    coordinates: 'CenterCord'
    bounding_box: 'BoundingBox'

@dataclass
class BoundingBox:
    x1:int
    y1:int
    x2:int
    y2:int

    def to_string(self):
        return f'[{self.x1},{self.y1}][{self.x2},{self.y2}]'

@dataclass
class TreeState:
    interactive_elements:list[ElementNode]

    def to_string(self):
        return '\n'.join([f'Label: {index} Name: {node.name} Coordinates: {node.coordinates.to_string()}' for index,node in enumerate(self.interactive_elements)])
    
@dataclass
class CenterCord:
    x: int
    y: int

    def to_string(self):
        return f'({self.x},{self.y})'