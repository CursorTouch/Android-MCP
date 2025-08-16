from src.mobile.views import MobileState
from src.tree import Tree
import uiautomator2 as u2
from io import BytesIO
from PIL import Image

class Mobile:
    def __init__(self,device:str=None):
        try:
            self.device = u2.connect(device)
            self.device.info
        except u2.ConnectError as e:
            raise ConnectionError(f"Failed to connect to device {device}: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error connecting to device {device}: {e}")

    def get_device(self):
        return self.device

    def get_state(self,use_vision=False):
        try:
            tree = Tree(self)
            tree_state = tree.get_state()
            if use_vision:
                nodes=tree_state.interactive_elements
                annotated_screenshot=tree.annotated_screenshot(nodes=nodes,scale=1.0)
                screenshot=self.screenshot_in_bytes(annotated_screenshot)
            else:
                screenshot=None
            return MobileState(tree_state=tree_state,screenshot=screenshot)
        except Exception as e:
            raise RuntimeError(f"Failed to get device state: {e}")
    
    def get_screenshot(self,scale:float=0.7)->Image.Image:
        try:
            screenshot=self.device.screenshot()
            if screenshot is None:
                raise ValueError("Screenshot capture returned None.")
            size=(screenshot.width*scale, screenshot.height*scale)
            screenshot.thumbnail(size=size, resample=Image.Resampling.LANCZOS)
            return screenshot
        except Exception as e:
            raise RuntimeError(f"Failed to get screenshot: {e}")
    
    def screenshot_in_bytes(self,screenshot:Image.Image)->bytes:
        try:
            if screenshot is None:
                raise ValueError("Screenshot is None")
            io=BytesIO()
            screenshot.save(io,format='PNG')
            bytes=io.getvalue()
            if len(bytes) == 0:
                raise ValueError("Screenshot conversion resulted in empty bytes.")
            return bytes
        except Exception as e:
            raise RuntimeError(f"Failed to convert screenshot to bytes: {e}")

    