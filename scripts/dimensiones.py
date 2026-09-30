import sys
from PIL import Image

for ruta in sys.argv[1:]:
    with Image.open(ruta) as im:
        print(ruta, im.format, im.width, "x", im.height)