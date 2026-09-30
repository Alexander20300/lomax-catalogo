import os
from PIL import Image, ImageDraw

os.makedirs("evidencias/E3", exist_ok=True)
img = Image.new("RGB", (1200, 800))
d = ImageDraw.Draw(img)
for x in range(1200):
    d.line([(x, 0), (x, 800)], fill=(x * 255 // 1200, 120, 255 - x * 255 // 1200))
d.rectangle([100, 100, 1100, 700], outline="white", width=8)
d.text((150, 150), "Producto de prueba 1200x800", fill="white")
img.save("evidencias/E3/prueba_1200x800.jpg", "JPEG", quality=90)

with open("evidencias/E3/invalido.jpg", "w") as f:
    f.write("esto no es una imagen")