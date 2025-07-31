from src.mobile.views import MobileState
from src.tree import Tree
import uiautomator2 as u2
from io import BytesIO
from PIL import Image

class Mobile:
    def __init__(self,device:str=None):
        self.device = u2.connect(device)

    def get_device(self):
        return self.device

    def get_state(self,use_vision=False):
        tree = Tree(self)
        tree_state = tree.get_state()
        if use_vision:
            nodes=tree_state.interactive_elements
            annotated_screenshot=tree.annotated_screenshot(nodes=nodes,scale=1.0)
            screenshot=self.screenshot_in_bytes(annotated_screenshot)
        else:
            screenshot=None
        return MobileState(tree_state=tree_state,screenshot=screenshot)
    
    def get_screenshot(self,scale:float=0.7)->Image.Image:
        screenshot=self.device.screenshot()
        size=(screenshot.width*scale, screenshot.height*scale)
        screenshot.thumbnail(size=size, resample=Image.Resampling.LANCZOS)
        return screenshot
    
    def screenshot_in_bytes(self,screenshot:Image.Image)->bytes:
        io=BytesIO()
        screenshot.save(io,format='PNG')
        bytes=io.getvalue()
        return bytes

    