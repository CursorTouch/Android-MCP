from dataclasses import dataclass

@dataclass
class ElementNode:
    name: str
    coordinates: 'CenterCord'

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