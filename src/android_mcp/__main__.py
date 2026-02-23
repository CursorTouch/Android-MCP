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
args = parser.parse_args()

instructions=dedent('''
Android MCP server provides tools to interact directly with the Android device, 
thus enabling to operate the mobile device like an actual USER.''')

@asynccontextmanager
async def lifespan(app: FastMCP):
    """Runs initialization code before the server starts and cleanup code after it shuts down."""
    await asyncio.sleep(1) # Simulate startup latency
    yield

mcp=FastMCP(name="Android-MCP",instructions=instructions)

mobile=Mobile()

# Auto-connect: use --device if provided, otherwise auto-detect a single device
target=args.device
if not target:
    try:
        devices=Mobile.list_devices()
        online=[(s,st) for s,st in devices if st == 'device']
        if len(online) == 1:
            target=online[0][0]
    except Exception:
        pass

if target:
    try:
        mobile.connect(target)
    except Exception as e:
        print(f"Warning: could not connect to {target}: {e}",file=sys.stderr)

not_connected_msg="No device connected. Use the ListDevices tool to see available devices, then ConnectDevice to connect."

def require_device():
    if not mobile.is_connected:
        raise RuntimeError(not_connected_msg)
    return mobile.get_device()

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

@mcp.tool(name='Snapshot',description='Get the state of the device. Optionally includes visual screenshot when use_vision=True.',annotations=ToolAnnotations(title="Snapshot",readOnlyHint=True))
def state_tool(use_vision:bool=False):
    require_device()
    mobile_state=mobile.get_state(use_vision=use_vision,as_bytes=True)
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

def main():
    mcp.run()

if __name__ == '__main__':
    main()