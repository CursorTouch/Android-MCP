from src.mobile.views import MobileState
from uiautomator2 import Device
from src.tree import Tree
import uiautomator2 as u2

class Mobile:
    def __init__(self,device:str=None):
        self.device = u2.connect(device)

    def get_device(self):
        return self.device

    def get_state(self):
        tree = Tree(self)
        tree_state = tree.get_state()
        return MobileState(tree_state=tree_state)
    
    def get_screenshot(self):
        image=self.device.screenshot()

    