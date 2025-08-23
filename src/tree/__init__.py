from src.tree.views import TreeState, ElementNode, CenterCord, BoundingBox
from src.tree.utils import extract_cordinates,get_center_cordinates
from src.tree.config import INTERACTIVE_CLASSES
from PIL import Image, ImageFont, ImageDraw
from xml.etree.ElementTree import Element
from xml.etree import ElementTree
from typing import TYPE_CHECKING
import random

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

        try:
            element_tree = self.get_element_tree()
            nodes=element_tree.findall('.//node[@visible-to-user="true"][@enabled="true"]')
            
        except Exception as e:
            print(f"Error getting element tree: {e}")
            return interactive_elements

        for node in nodes:
            try:
                attributes=node.attrib

                if not self.is_interactive_element(attributes) or not attributes.get('bounds'):
                    continue

                x1,y1,x2,y2 = extract_cordinates(attributes.get('bounds'))
                name=attributes.get('text') or attributes.get('content-desc')
                x_center,y_center = get_center_cordinates((x1,y1,x2,y2))
                interactive_elements.append(ElementNode(**{
                    'name':name,
                    'coordinates':CenterCord(x=x_center,y=y_center),
                    'bounding_box':BoundingBox(x1=x1,y1=y1,x2=x2,y2=y2)
                }))

            except (ValueError, TypeError, AttributeError) as e:
                print(f"Error processing element: {e}, skipping element")
                continue

            except Exception as e:
                print(f"Unexpected error processing element: {e}, skipping element")
                continue
        return interactive_elements
    

    def is_interactive_element(self, attributes: dict) -> bool:

        element_class = attributes.get('class', '')
        
        if element_class in INTERACTIVE_CLASSES:
            return True

        elif attributes.get('clickable') == 'true':
            return True

        elif attributes.get('focusable') == 'true':
            element_class = attributes.get('class', '')
            if any(input_class in element_class for input_class in [
                'EditText', 'AutoCompleteTextView', 'MultiAutoCompleteTextView'
            ]):
                return True
        
        elif attributes.get('scrollable') == 'true':
            bounds = attributes.get('bounds')

            if bounds:
                coords = extract_cordinates(bounds)
                if coords:
                    x1, y1, x2, y2 = coords
                    width, height = x2 - x1, y2 - y1
                    if width > 100 and height > 100:
                        return True
        
        elif element_class == "android.widget.TextView":
            text = attributes.get('text', '').strip()
            
            button_keywords = [
                'login', 'submit', 'send', 'save', 'delete', 'edit', 'cancel', 'ok', 'yes', 'no',
                'continue', 'next', 'previous', 'back', 'home', 'menu', 'settings', 'help',
                'sign in', 'sign up', 'log in', 'log out', 'register', 'create', 'update',
                'confirm', 'proceed', 'finish', 'done', 'apply', 'reset', 'clear'
            ]
            
            if text and any(keyword in text.lower() for keyword in button_keywords):
                return True
        
        if element_class == "android.widget.ImageView":
            content_desc = attributes.get('content-desc', '').strip()
            if content_desc:
                interactive_descriptions = [
                    'button', 'menu', 'icon', 'avatar', 'profile', 'settings', 'back', 'close',
                    'search', 'filter', 'sort', 'refresh', 'reload', 'share', 'favorite',
                    'bookmark', 'like', 'download', 'upload', 'play', 'pause', 'stop'
                ]
                if any(desc in content_desc.lower() for desc in interactive_descriptions):
                    return True
        
        if element_class in [
            "android.widget.ListView", 
            "androidx.recyclerview.widget.RecyclerView",
        ]:
            return True
        
        return False

    
    def annotated_screenshot(self, nodes: list[ElementNode],scale:float=0.7) -> Image.Image:
        screenshot = self.mobile.get_screenshot(scale=scale)
        # Add padding
        padding = 10
        width = screenshot.width + (2 * padding)
        height = screenshot.height + (2 * padding)
        padded_screenshot = Image.new("RGB", (width, height), color=(255, 255, 255))
        padded_screenshot.paste(screenshot, (padding, padding))

        draw = ImageDraw.Draw(padded_screenshot)
        font_size = 12
        try:
            font = ImageFont.truetype('arial.ttf', font_size)
        except IOError:
            font = ImageFont.load_default()

        def get_random_color():
            return "#{:06x}".format(random.randint(0, 0xFFFFFF))

        def draw_annotation(label, node: ElementNode):
            left,top,right,bottom = node.bounding_box
            color = get_random_color()

            # Scale and pad the bounding box also clip the bounding box
            adjusted_box = (
                int(left * scale) + padding,
                int(top * scale) + padding,
                int(right * scale) + padding,
                int(bottom * scale) + padding
            )
            # Draw bounding box
            draw.rectangle(adjusted_box, outline=color, width=2)

            # Label dimensions
            label_width = draw.textlength(str(label), font=font)
            label_height = font_size
            left, top, right, bottom = adjusted_box

            # Label position above bounding box
            label_x1 = right - label_width
            label_y1 = top - label_height - 4
            label_x2 = label_x1 + label_width
            label_y2 = label_y1 + label_height + 4

            # Draw label background and text
            draw.rectangle([(label_x1, label_y1), (label_x2, label_y2)], fill=color)
            draw.text((label_x1 + 2, label_y1 + 2), str(label), fill=(255, 255, 255), font=font)
        
        # Draw annotations sequentially for better performance and thread safety
        for i, node in enumerate(nodes):
            draw_annotation(i, node)

        return padded_screenshot
