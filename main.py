from mcp.server.fastmcp import FastMCP,Image
from src.mobile import Mobile
from textwrap import dedent
from argparse import ArgumentParser

parser = ArgumentParser()
parser.add_argument('--emulator',action='store_true',help='Use the emulator')
args = parser.parse_args()

instructions=dedent('''
Android MCP server provides tools to interact directly with the Android device, 
thus enabling to operate the mobile device like an actual USER.''')

mcp=FastMCP(name="Android-MCP",instructions=instructions)

mobile=Mobile(device=None if not args.emulator else 'emulator-5554')
device=mobile.get_device()

@mcp.tool(name='Click-Tool',description='Click on a specific cordinate')
def click_tool(x:int,y:int):
    device.click(x,y)
    return f'Clicked on ({x},{y})'

@mcp.tool('State-Tool',description='Get the state of the device')
def state_tool():
    mobile_state=mobile.get_state()
    return mobile_state.tree_state.to_string()

@mcp.tool(name='Long-Click-Tool',description='Long click on a specific cordinate')
def long_click_tool(x:int,y:int,duration:int):
    device.long_click(x,y,duration=duration)
    return f'Long Clicked on ({x},{y})'

@mcp.tool(name='Swipe-Tool',description='Swipe on a specific cordinate')
def swipe_tool(x1:int,y1:int,x2:int,y2:int):
    device.swipe(x1,y1,x2,y2)
    return f'Swiped from ({x1},{y1}) to ({x2},{y2})'

@mcp.tool(name='Type-Tool',description='Type on a specific cordinate')
def type_tool(text:str,x:int,y:int,clear:bool=False):
    device.set_fastinput_ime(enable=True)
    device.send_keys(text=text,clear=clear)
    return f'Typed "{text}" on ({x},{y})'

@mcp.tool(name='Drag-Tool',description='Drag from location and drop on another location')
def drag_tool(x1:int,y1:int,x2:int,y2:int):
    device.drag(x1,y1,x2,y2)
    return f'Dragged from ({x1},{y1}) and dropped on ({x2},{y2})'

@mcp.tool(name='Press-Tool',description='Press on specific button on the device')
def press_tool(button:str):
    device.press(button)
    return f'Pressed the "{button}" button'

@mcp.tool(name='Notification-Tool',description='Access the notifications seen on the device')
def notification_tool():
    device.open_notification()
    return f'Accessed notification bar'

@mcp.tool(name='Wait-Tool',description='Wait for a specific amount of time')
def wait_tool(duration:int):
    device.sleep(duration)
    return f'Waited for {duration} seconds'

@mcp.tool(name='Shell-Tool',description='Execute shell commands on the device')
def shell_tool(command:str):
    return device.shell(command)

if __name__ == '__main__':
    mcp.run()