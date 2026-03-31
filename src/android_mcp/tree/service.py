from android_mcp.tree.views import TreeState, ElementNode, CenterCord, BoundingBox
from android_mcp.tree.utils import extract_cordinates,get_center_cordinates
from android_mcp.tree.config import INTERACTIVE_CLASSES
from PIL import Image, ImageFont, ImageDraw
from xml.etree.ElementTree import Element
from xml.etree import ElementTree
from typing import TYPE_CHECKING
import random
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

if TYPE_CHECKING:
    from android_mcp.mobile import Mobile

class Tree:
    def __init__(self,mobile:'Mobile'):
        self.mobile = mobile

    def get_element_tree(self, xml_data=None)->'Element':
        tree_string = xml_data if xml_data else self.mobile.device.dump_hierarchy()
        return ElementTree.fromstring(tree_string)
    
    def get_state(self, xml_data=None)->TreeState:
        interactive_elements=self.get_interactive_elements(xml_data=xml_data)
        return TreeState(interactive_elements=interactive_elements)
    
    def get_interactive_elements(self, xml_data=None)->list:
        interactive_elements=[]
        element_tree = self.get_element_tree(xml_data=xml_data)
        nodes=element_tree.findall('.//node[@enabled="true"]')
        for node in nodes:
            if self.is_interactive(node):
                x1,y1,x2,y2 = extract_cordinates(node)
                name=self.get_element_name(node)
                if not name:
                    continue
                x_center,y_center = get_center_cordinates((x1,y1,x2,y2))
                raw_id=node.get('resource-id','')
                short_id=raw_id.split('/')[-1] if '/' in raw_id else raw_id
                interactive_elements.append(ElementNode(**{
                    'name':name,
                    'class_name':node.get('class'),
                    'coordinates':CenterCord(x=x_center,y=y_center),
                    'bounding_box':BoundingBox(x1=x1,y1=y1,x2=x2,y2=y2),
                    'resource_id':short_id
                }))
        return interactive_elements

    def get_element_name(self, node) -> str:
        name = node.get('content-desc') or node.get('text')
        if not name:
            texts = []
            fallback_texts = []
            
            def collect_text(n):
                # Check if this node is actionable (and not the root node we started with)
                is_actionable = (n is not node) and (
                               n.get('clickable') == "true" or 
                               n.get('long-clickable') == "true" or
                               n.get('checkable') == "true" or
                               n.get('scrollable') == "true")
                
                val = n.get('text') or n.get('content-desc') or n.get('hint')

                if is_actionable:
                    if val:
                        fallback_texts.append(val)
                    return # Stop recursing into actionable nodes
                
                if val:
                    texts.append(val)
                
                for child in n:
                    collect_text(child)
            
            collect_text(node)
            
            # Use primary texts if found, otherwise use fallback texts from actionable children
            final_texts = texts if texts else fallback_texts
            name = " ".join(final_texts).strip()
        return name

    def is_interactive(self, node) -> bool:
        attributes = node.attrib
        return (attributes.get('focusable') == "true" or 
        attributes.get('clickable') == "true" or
        attributes.get('long-clickable') == "true" or
        attributes.get('checkable') == "true" or
        attributes.get('scrollable') == "true" or
        attributes.get('selected') == "true" or
        attributes.get('password') == "true" or
        attributes.get('class') in INTERACTIVE_CLASSES)

    def annotated_screenshot(self, nodes: list[ElementNode],scale:float=0.7, screenshot=None) -> Image.Image:
        if screenshot is None:
            screenshot = self.mobile.get_screenshot(scale=scale)

        draw = ImageDraw.Draw(screenshot)
        font_size = 12
        try:
            font = ImageFont.truetype('arial.ttf', font_size)
        except IOError:
            font = ImageFont.load_default()

        def get_random_color():
            return "#{:06x}".format(random.randint(0, 0xFFFFFF))

        def draw_annotation(label, node: ElementNode):
            bounding_box = node.bounding_box
            color = get_random_color()

            adjusted_box = (
                int(bounding_box.x1 * scale),
                int(bounding_box.y1 * scale),
                int(bounding_box.x2 * scale),
                int(bounding_box.y2 * scale)
            )
            # Draw bounding box
            draw.rectangle(adjusted_box, outline=color, width=2)

            # Label dimensions
            label_width = draw.textlength(str(label), font=font)
            label_height = font_size
            left, top, right, bottom = adjusted_box

            # Label position above bounding box, clamped to image bounds
            label_x1 = max(0, right - label_width)
            label_y1 = max(0, top - label_height - 4)
            label_x2 = label_x1 + label_width
            label_y2 = label_y1 + label_height + 4

            # Draw label background and text
            draw.rectangle([(label_x1, label_y1), (label_x2, label_y2)], fill=color)
            draw.text((label_x1 + 2, label_y1 + 2), str(label), fill=(255, 255, 255), font=font)

        for i, node in enumerate(nodes):
            draw_annotation(i, node)

        return screenshot
