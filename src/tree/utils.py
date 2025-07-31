import re

def extract_cordinates(bounds:str):
    match = re.search(r'\[(\d+),(\d+)]\[(\d+),(\d+)]', bounds)
    if match:
        x1, y1, x2, y2 = map(int, match.groups())
        return x1, y1, x2, y2

def get_center_cordinates(cordinates:tuple[int,int,int,int]):
    x_center,y_center = (cordinates[0]+cordinates[2])//2,(cordinates[1]+cordinates[3])//2
    return x_center,y_center