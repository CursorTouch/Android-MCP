from android_mcp.mobile.views import MobileState
from android_mcp.tree.service import Tree
import uiautomator2 as u2
from io import BytesIO
from PIL import Image
import subprocess
import base64
import os

class Mobile:
    def __init__(self):
        self.device = None

    @staticmethod
    def list_devices():
        try:
            result = subprocess.run(
                ['adb', 'devices'], capture_output=True, text=True, timeout=10
            )
            devices = []
            for line in result.stdout.strip().splitlines()[1:]:
                parts = line.split('\t')
                if len(parts) == 2:
                    devices.append((parts[0], parts[1]))
            return devices
        except FileNotFoundError:
            raise RuntimeError("adb not found. Ensure ADB is installed and on PATH.")
        except subprocess.TimeoutExpired:
            raise RuntimeError("adb devices timed out.")

    def connect(self,serial:str):
        try:
            self.device = u2.connect(serial)
            self.device.info
        except u2.ConnectError as e:
            self.device = None
            raise ConnectionError(f"Failed to connect to device {serial}: {e}")
        except Exception as e:
            self.device = None
            raise RuntimeError(f"Unexpected error connecting to device {serial}: {e}")

    def disconnect(self):
        self.device = None

    @property
    def is_connected(self):
        return self.device is not None

    def get_device(self):
        return self.device

    def capture_data(self, use_vision: bool = True):
        import threading
        data = {}

        def get_xml():
            try:
                data['xml'] = self.device.dump_hierarchy()
            except Exception as e:
                data['xml_error'] = e

        def get_img():
            try:
                # Use format="pillow" to ensure we get a PIL image immediately
                data['img'] = self.device.screenshot(format="pillow")
            except Exception as e:
                data['img_error'] = e

        threads = [threading.Thread(target=get_xml)]
        if use_vision:
            threads.append(threading.Thread(target=get_img))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if 'xml_error' in data:
            raise data['xml_error']
        if use_vision and 'img_error' in data:
            raise data['img_error']

        return data.get('xml'), data.get('img')

    def get_state(self, use_vision=False, as_bytes: bool = False, as_base64: bool = False, use_annotation: bool = True):
        try:
            xml_data, screenshot_data = self.capture_data(use_vision=use_vision)
            tree = Tree(self)
            tree_state = tree.get_state(xml_data=xml_data)

            if use_vision:
                nodes = tree_state.interactive_elements
                if use_annotation:
                    screenshot = tree.annotated_screenshot(nodes=nodes, scale=1.0, screenshot=screenshot_data)
                else:
                    screenshot = screenshot_data

                if os.getenv("SCREENSHOT_QUANTIZED") in ["1", "yes", "true", True]:
                    screenshot = self.quantized_screenshot(screenshot)

                if as_base64:
                    screenshot = self.as_base64(screenshot)
                elif as_bytes:
                    screenshot = self.screenshot_in_bytes(screenshot)
            else:
                screenshot = None
            return MobileState(tree_state=tree_state, screenshot=screenshot)
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

    def quantized_screenshot(self, screenshot: Image.Image) -> Image.Image:
        if screenshot.mode == 'RGBA':
            screenshot = screenshot.convert('RGB')
        screenshot = screenshot.convert('P', palette=Image.Palette.ADAPTIVE, colors=256)

        io = BytesIO()
        screenshot.save(io, format='PNG', optimize=True)
        return Image.open(io)

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

    def as_base64(self,screenshot:Image.Image)->str:
        try:
            if screenshot is None:
                raise ValueError("Screenshot is None")
            io=BytesIO()
            screenshot.save(io,format='PNG')
            bytes=io.getvalue()
            if len(bytes) == 0:
                raise ValueError("Screenshot conversion resulted in empty bytes.")
            return base64.b64encode(bytes).decode('utf-8')
        except Exception as e:
            raise RuntimeError(f"Failed to convert screenshot to base64: {e}")

    