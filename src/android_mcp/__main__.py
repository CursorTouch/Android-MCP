from fastmcp import FastMCP
from fastmcp.utilities.types import Image
from mcp.types import ToolAnnotations
from contextlib import asynccontextmanager
from argparse import ArgumentParser
from android_mcp.mobile.service import Mobile
from textwrap import dedent
import asyncio
import sys

parser = ArgumentParser()
parser.add_argument('--device',type=str,help='Device serial number (default: auto-detect)')
args, _ = parser.parse_known_args()

instructions=dedent('''
Android MCP server provides tools to interact directly with the Android device, 
thus enabling to operate the mobile device like an actual USER.''')

@asynccontextmanager
async def lifespan(app: FastMCP):
    """Runs initialization code before the server starts and cleanup code after it shuts down."""
    yield

mcp=FastMCP(name="Android-MCP",instructions=instructions)

mobile=Mobile()

_auto_connect_attempted = False

not_connected_msg="No device connected. Use the ListDevices tool to see available devices, then ConnectDevice to connect."

def require_device():
    global _auto_connect_attempted
    if not mobile.is_connected and not _auto_connect_attempted:
        _auto_connect_attempted = True
        target = args.device
        if not target:
            try:
                devices = Mobile.list_devices()
                online = [(s, st) for s, st in devices if st == 'device']
                if len(online) == 1:
                    target = online[0][0]
            except Exception:
                pass
        
        if target:
            try:
                mobile.connect(target)
            except Exception as e:
                print(f"Warning: could not connect to {target}: {e}", file=sys.stderr)
                
    if not mobile.is_connected:
        raise RuntimeError(not_connected_msg)
    return mobile.get_device()

def _resolve_resource_id(device, resource_id: str) -> str:
    """Auto-expand short resourceId (e.g. 'btn_login') to full form (e.g. 'com.example.app:id/btn_login') using the current foreground app package."""
    if not resource_id or '/' in resource_id or ':' in resource_id:
        return resource_id
    try:
        pkg = device.app_current().get('package', '')
    except Exception:
        pkg = ''
    if pkg:
        return f'{pkg}:id/{resource_id}'
    return resource_id

@mcp.tool(name='ListDevices',description='List available ADB devices',annotations=ToolAnnotations(title="List Devices",readOnlyHint=True))
def list_devices_tool():
    devices=Mobile.list_devices()
    if not devices:
        return "No devices found. Ensure a device is connected and ADB is running."
    lines=[f"{serial}\t{state}" for serial,state in devices]
    return "\n".join(lines)

@mcp.tool(name='ConnectDevice',description='Connect to an ADB device by serial number',annotations=ToolAnnotations(title="Connect Device"))
def connect_device_tool(serial:str):
    mobile.connect(serial)
    return f'Connected to {serial}'

@mcp.tool(name='Click',description='Click on a specific cordinate',annotations=ToolAnnotations(title="Click",destructiveHint=True))
def click_tool(x:int,y:int):
    device=require_device()
    device.click(x,y)
    return f'Clicked on ({x},{y})'

@mcp.tool(name='ClickBySelector',description='Click on an element by selector (text, resourceId, className, description). More reliable than coordinate clicks — handles dynamic layouts and element reflow. At least one selector must be provided.',annotations=ToolAnnotations(title="Click By Selector",destructiveHint=True))
def click_by_selector_tool(text:str=None,resourceId:str=None,className:str=None,description:str=None,index:int=0,timeout:float=5.0):
    device=require_device()
    kwargs={}
    if text: kwargs['text']=text
    if resourceId: kwargs['resourceId']=_resolve_resource_id(device, resourceId)
    if className: kwargs['className']=className
    if description: kwargs['description']=description
    if not kwargs:
        return 'Error: at least one selector (text, resourceId, className, description) must be provided'
    if index: kwargs['index']=index
    el=device(**kwargs)
    if not el.wait(timeout=timeout):
        return f'Element not found with selectors {kwargs} within {timeout}s'
    el.click()
    return f'Clicked element matching {kwargs}'

@mcp.tool(name='Snapshot',description='Get the state of the device. Optionally includes visual screenshot when use_vision=True. The use_annotation parameter (default True) can be set to False to get a clean screenshot without bounding boxes.',annotations=ToolAnnotations(title="Snapshot",readOnlyHint=True))
def state_tool(use_vision:bool=False,use_annotation:bool=True):
    require_device()
    mobile_state=mobile.get_state(use_vision=use_vision, use_annotation=use_annotation, as_bytes=True)
    return [mobile_state.tree_state.to_string()]+([Image(data=mobile_state.screenshot,format='PNG')] if use_vision else [])

@mcp.tool(name='LongClick',description='Long click on a specific cordinate',annotations=ToolAnnotations(title="Long Click",destructiveHint=True))
def long_click_tool(x:int,y:int):
    device=require_device()
    device.long_click(x,y)
    return f'Long Clicked on ({x},{y})'

@mcp.tool(name='Swipe',description='Swipe on a specific cordinate',annotations=ToolAnnotations(title="Swipe",destructiveHint=True))
def swipe_tool(x1:int,y1:int,x2:int,y2:int):
    device=require_device()
    device.swipe(x1,y1,x2,y2)
    return f'Swiped from ({x1},{y1}) to ({x2},{y2})'

@mcp.tool(name='Type',description='Type on a specific cordinate',annotations=ToolAnnotations(title="Type",destructiveHint=True))
def type_tool(text:str,x:int,y:int,clear:bool=False):
    device=require_device()
    device.set_fastinput_ime(enable=True)
    device.send_keys(text=text,clear=clear)
    return f'Typed "{text}" on ({x},{y})'

@mcp.tool(name='Drag',description='Drag from location and drop on another location',annotations=ToolAnnotations(title="Drag",destructiveHint=True))
def drag_tool(x1:int,y1:int,x2:int,y2:int):
    device=require_device()
    device.drag(x1,y1,x2,y2)
    return f'Dragged from ({x1},{y1}) and dropped on ({x2},{y2})'

@mcp.tool(name='Press',description='Press on specific button on the device',annotations=ToolAnnotations(title="Press",destructiveHint=True))
def press_tool(button:str):
    device=require_device()
    device.press(button)
    return f'Pressed the "{button}" button'

@mcp.tool(name='Notification',description='Access the notifications seen on the device',annotations=ToolAnnotations(title="Notification",destructiveHint=True,idempotentHint=True))
def notification_tool():
    device=require_device()
    device.open_notification()
    return 'Accessed notification bar'

@mcp.tool(name='Wait',description='Wait for a specific amount of time',annotations=ToolAnnotations(title="Wait",destructiveHint=True,idempotentHint=True))
def wait_tool(duration:int):
    device=require_device()
    device.sleep(duration)
    return f'Waited for {duration} seconds'

@mcp.tool(name='WaitForElement',description='Wait for an element to appear on screen. Use this instead of Wait when content is loading dynamically. Returns element info when found or error on timeout.',annotations=ToolAnnotations(title="Wait For Element",readOnlyHint=True))
def wait_for_element_tool(text:str=None,resourceId:str=None,className:str=None,description:str=None,timeout:float=10.0):
    device=require_device()
    kwargs={}
    if text: kwargs['text']=text
    if resourceId: kwargs['resourceId']=_resolve_resource_id(device, resourceId)
    if className: kwargs['className']=className
    if description: kwargs['description']=description
    if not kwargs:
        return 'Error: at least one selector (text, resourceId, className, description) must be provided'
    el=device(**kwargs)
    if el.wait(timeout=timeout):
        info=el.info
        bounds=info.get('bounds',{})
        cx=(bounds.get('left',0)+bounds.get('right',0))//2
        cy=(bounds.get('top',0)+bounds.get('bottom',0))//2
        return f'Element found: text="{info.get("text","")}" class={info.get("className","")} coords=({cx},{cy}) bounds=[{bounds.get("left",0)},{bounds.get("top",0)}][{bounds.get("right",0)},{bounds.get("bottom",0)}]'
    return f'Element not found with selectors {kwargs} within {timeout}s'

def main():
    mcp.run()

if __name__ == '__main__':
    main()