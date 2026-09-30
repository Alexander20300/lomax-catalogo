"""Carga 20 productos por la API (repetible). Usa fotos\\CODIGO.jpg|png si existen."""
import io
import json
import os
import urllib.error
import urllib.request
import uuid

from PIL import Image, ImageDraw, ImageFont

BASE = os.environ.get("API_BASE", "http://proxy/api")
MAPA = "scripts/ids_productos.json"

PRODUCTOS = [
    # Teclados: conexion + distribucion
    ("LMX-TEC-01", "Teclado Mecanico K1", "Teclado mecanico switch rojo", 45.90, "Teclados", {"conexion": "USB", "distribucion": "Espanol"}),
    ("LMX-TEC-02", "Teclado Inalambrico K2", "Teclado compacto inalambrico", 32.50, "Teclados", {"conexion": "Bluetooth", "distribucion": "Espanol"}),
    ("LMX-TEC-03", "Teclado Gamer RGB K3", "Teclado retroiluminado para juegos", 59.00, "Teclados", {"conexion": "USB", "distribucion": "Ingles"}),
    ("LMX-TEC-04", "Teclado Oficina K4", "Teclado de membrana silencioso", 18.90, "Teclados", {"conexion": "USB", "distribucion": "Espanol"}),
    ("LMX-TEC-05", "Teclado Mecanico 60% K5", "Formato compacto 60 por ciento", 69.90, "Teclados", {"conexion": "USB-C", "distribucion": "Ingles"}),
    ("LMX-TEC-06", "Teclado Slim K6", "Teclado delgado recargable", 41.00, "Teclados", {"conexion": "Bluetooth", "distribucion": "Espanol"}),
    ("LMX-TEC-07", "Teclado Numerico K7", "Teclado numerico externo", 12.50, "Teclados", {"conexion": "USB", "distribucion": "Numerico"}),
    # Pantallas: pulgadas + resolucion
    ("LMX-PAN-01", "Monitor 21.5 pulgadas", "Monitor Full HD para oficina", 129.00, "Pantallas", {"pulgadas": 21.5, "resolucion": "1920x1080"}),
    ("LMX-PAN-02", "Monitor 24 pulgadas IPS", "Panel IPS con bordes delgados", 179.00, "Pantallas", {"pulgadas": 24, "resolucion": "1920x1080"}),
    ("LMX-PAN-03", "Monitor 27 pulgadas QHD", "Resolucion QHD para diseno", 259.00, "Pantallas", {"pulgadas": 27, "resolucion": "2560x1440"}),
    ("LMX-PAN-04", "Monitor 32 pulgadas 4K", "Panel 4K para edicion", 399.00, "Pantallas", {"pulgadas": 32, "resolucion": "3840x2160"}),
    ("LMX-PAN-05", "Monitor Gamer 24 pulgadas", "144 Hz para juegos", 219.00, "Pantallas", {"pulgadas": 24, "resolucion": "1920x1080"}),
    ("LMX-PAN-06", "Monitor Curvo 34 pulgadas", "Ultrapanoramico curvo", 449.00, "Pantallas", {"pulgadas": 34, "resolucion": "3440x1440"}),
    ("LMX-PAN-07", "Monitor Portatil 15.6 pulgadas", "Monitor portatil USB-C", 149.00, "Pantallas", {"pulgadas": 15.6, "resolucion": "1920x1080"}),
    # Mouses: conexion + dpi
    ("LMX-MOU-01", "Mouse Optico M1", "Mouse optico de 3 botones", 6.90, "Mouses", {"conexion": "USB", "dpi": 1000}),
    ("LMX-MOU-02", "Mouse Inalambrico M2", "Mouse inalambrico 2.4 GHz", 11.90, "Mouses", {"conexion": "Inalambrico", "dpi": 1600}),
    ("LMX-MOU-03", "Mouse Gamer M3", "Sensor de alta precision", 24.90, "Mouses", {"conexion": "USB", "dpi": 6400}),
    ("LMX-MOU-04", "Mouse Bluetooth M4", "Mouse silencioso Bluetooth", 15.50, "Mouses", {"conexion": "Bluetooth", "dpi": 1600}),
    ("LMX-MOU-05", "Mouse Ergonomico M5", "Diseno vertical ergonomico", 29.90, "Mouses", {"conexion": "Inalambrico", "dpi": 1600}),
    ("LMX-MOU-06", "Mouse Ligero M6", "Mouse ultraligero para juegos", 34.90, "Mouses", {"conexion": "USB", "dpi": 12000}),
]
COLOR = {"Teclados": (11, 61, 145), "Pantallas": (5, 122, 85), "Mouses": (180, 83, 9)}


def http(metodo, ruta, cuerpo_json=None, archivo=None):
    headers, data = {}, None
    if cuerpo_json is not None:
        data = json.dumps(cuerpo_json).encode()
        headers["Content-Type"] = "application/json"
    elif archivo:
        nombre, contenido, tipo = archivo
        b = "----lomax" + uuid.uuid4().hex
        data = (f'--{b}\r\nContent-Disposition: form-data; name="archivo"; '
                f'filename="{nombre}"\r\nContent-Type: {tipo}\r\n\r\n').encode()
        data += contenido + f"\r\n--{b}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={b}"
    req = urllib.request.Request(BASE + ruta, data=data, method=metodo, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def foto(codigo, nombre, categoria):
    for ext, tipo in (("jpg", "image/jpeg"), ("jpeg", "image/jpeg"), ("png", "image/png")):
        ruta = f"fotos/{codigo}.{ext}"
        if os.path.exists(ruta):
            return f"{codigo}.{ext}", open(ruta, "rb").read(), tipo
    img = Image.new("RGB", (800, 600), COLOR[categoria])
    d = ImageDraw.Draw(img)
    d.rectangle([30, 30, 770, 570], outline="white", width=6)
    try:
        f1, f2 = ImageFont.load_default(size=44), ImageFont.load_default(size=30)
    except TypeError:
        f1 = f2 = ImageFont.load_default()
    d.text((60, 220), nombre, fill="white", font=f1)
    d.text((60, 300), codigo + " - " + categoria, fill="white", font=f2)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return f"{codigo}.jpg", buf.getvalue(), "image/jpeg"


mapa = json.load(open(MAPA)) if os.path.exists(MAPA) else {}
_, c = http("GET", "/categorias")
cat_id = {x["nombre"]: x["id"] for x in json.loads(c)}
ok = 0
for codigo, nombre, desc, precio, cat, attrs in PRODUCTOS:
    pid = mapa.get(codigo)
    if not pid:
        st, c = http("POST", "/productos", {"codigo": codigo, "nombre": nombre, "descripcion": desc,
                     "precio": precio, "categoria_id": cat_id[cat], "atributos": attrs})
        if st != 201:
            print(f"[ERROR] {codigo}: HTTP {st} {c.decode()[:200]}")
            continue
        pid = json.loads(c)["producto_id"]
        mapa[codigo] = pid
        json.dump(mapa, open(MAPA, "w"), indent=2)
    st, c = http("GET", f"/productos/{pid}")
    if st == 200 and json.loads(c)["estado"] == "PUBLICADO":
        print(f"[YA PUBLICADO] {codigo}")
        ok += 1
        continue
    st, c = http("POST", f"/productos/{pid}/imagen", archivo=foto(codigo, nombre, cat))
    print(f"[{'OK' if st == 200 else 'ERROR'}] {codigo}: HTTP {st} {c.decode()[:120]}")
    ok += st == 200
print(f"\nPublicados por este script: {ok} de {len(PRODUCTOS)}")