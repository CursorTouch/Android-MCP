from xml.etree import ElementTree
from xml.etree.ElementTree import Element
from uiautomator2 import Device
import uiautomator2 as u2
import re

class Tree:
    def __init__(self, device:Device=None):
        self.device = device
    
    def get_element_tree(self)->Element:
        tree_string = self.device.dump_hierarchy()
        # print(tree_string)
        return ElementTree.fromstring(tree_string)
    
def extract_cordinates(text:str):
    match = re.search(r'\[(\d+),(\d+)]\[(\d+),(\d+)]', text)
    if match:
        x1, y1, x2, y2 = map(int, match.groups())
        return x1, y1, x2, y2

if __name__ == "__main__":
    device = u2.connect("emulator-5554")
    tree = Tree(device)
    element_tree = tree.get_element_tree()
    nodes=element_tree.findall('.//node[@visible-to-user="true"][@enabled="true"]')
    #Interactive Elements Check
    INTERACTIVE_CLASSES = [
        "android.widget.Button",
        "android.widget.ImageButton",
        "android.widget.EditText",
        "android.widget.CheckBox",
        "android.widget.Switch",
        "android.widget.RadioButton",
        "android.widget.Spinner",
        "android.widget.SeekBar"
    ]
    for node in nodes:
        attributes=node.attrib
        # print(attributes)
        if attributes.get('text') or attributes.get('content-desc') or attributes.get('class') in INTERACTIVE_CLASSES:
            cordinates = extract_cordinates(attributes.get('bounds'))
            x_center,y_center = (cordinates[0]+cordinates[2])//2,(cordinates[1]+cordinates[3])//2
            print(attributes.get('text') or attributes.get('content-desc') or 'EMPTY',(x_center,y_center))


        