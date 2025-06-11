from src.tree.utils import extract_cordinates,get_center_cordinates
from src.tree.views import TreeState, ElementNode, CenterCord
from src.tree.config import INTERACTIVE_CLASSES
from xml.etree.ElementTree import Element
from xml.etree import ElementTree
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.mobile import Mobile

class Tree:
    def __init__(self,mobile:'Mobile'):
        self.mobile = mobile

    def get_element_tree(self)->'Element':
        tree_string = self.mobile.device.dump_hierarchy()
        return ElementTree.fromstring(tree_string)
    
    def get_state(self)->TreeState:
        interactive_elements=self.get_interactive_elements()
        return TreeState(interactive_elements=interactive_elements)
    
    def get_interactive_elements(self)->list:
        interactive_elements=[]
        element_tree = self.get_element_tree()
        nodes=element_tree.findall('.//node[@visible-to-user="true"][@enabled="true"]')
        for node in nodes:
            attributes=node.attrib
            if attributes.get('text') or attributes.get('content-desc') or attributes.get('class') in INTERACTIVE_CLASSES:
                cordinates = extract_cordinates(attributes.get('bounds'))
                name=attributes.get('text') or attributes.get('content-desc')
                x_center,y_center = get_center_cordinates(cordinates)
                interactive_elements.append(ElementNode(name=name,coordinates=CenterCord(x=x_center,y=y_center)))
        return interactive_elements

                

