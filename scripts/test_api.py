"""Prueba E4: ejecuta todos los endpoints y verifica RDS, DynamoDB y S3 directamente."""
import hashlib
import json
import os
import struct
import sys
import urllib.error
import urllib.request
import uuid

import boto3
import psycopg2

API = os.environ.get("API_URL", "http://api:8000")
ENDPOINT = os.environ["AWS_ENDPOINT_URL"]
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
BUCKET_MINI = os.environ.get("BUCKET_MINIATURAS", "lomax-miniaturas")
TABLA = os.environ.get("TABLA_DYNAMO", "productos_atributos")
IMG_OK = "evidencias/E3/prueba_1200x800.jpg"

s3 = boto3.client("s3", endpoint_url=ENDPOINT, region_name=REGION)
ddb = boto3.client("dynamodb", endpoint_url=ENDPOINT, region_name=REGION)
fallos = 0


def rds(sql, params=()):
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
        dbname=os.environ["DB_NAME"], user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"], connect_timeout=5)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def dynamo(pid):
    r = ddb.get_item(TableName=TABLA, Key={"producto_id": {"S": pid}})
    return r.get("Item")


def http(metodo, ruta, cuerpo_json=None, archivo=None):
    headers, data = {}, None
    if cuerpo_json is not None:
        data = json.dumps(cuerpo_json).encode()
        headers["Content-Type"] = "application/json"
    elif archivo is not None:
        nombre, contenido, tipo = archivo
        b = "----lomax" + uuid.uuid4().hex
        data = (f'--{b}\r\nContent-Disposition: form-data; name="archivo"; '
                f'filename="{nombre}"\r\nContent-Type: {tipo}\r\n\r\n').encode()
        data += contenido + f"\r\n--{b}--\r\n".encode()
        headers["Content-Type"] = f"multipart/form-data; boundary={b}"
    req = urllib.request.Request(API + ruta, data=data, method=metodo, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            st, cab, cuerpo = r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        st, cab, cuerpo = e.code, dict(e.headers), e.read()
    es_img = cab.get("content-type", "").startswith("image/")
    resumen = f"<{len(cuerpo)} bytes de imagen>" if es_img else cuerpo.decode()[:350]
    print(f"  {metodo} {ruta[:70]} -> HTTP {st}  {resumen}")
    return st, cab, cuerpo


def jsn(cuerpo):
    try:
        return json.loads(cuerpo)
    except ValueError:
        return {}


def check(nombre, condicion, detalle=""):
    global fallos
    print(("    [OK]    " if condicion else "    [FALLO] ") + nombre
          + (f"  ({detalle})" if detalle else ""))
    if not condicion:
        fallos += 1


def caso(titulo):
    print(f"\n=== {titulo} ===")


def dims_jpeg(b):
    i = 2
    while i < len(b) - 9:
        if b[i] != 0xFF:
            i += 1
            continue
        m = b[i + 1]
        if m in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        if m == 0xFF:
            i += 1
            continue
        i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    return None


codigo = "E4-" + uuid.uuid4().hex[:8].upper()
valido = {"codigo": codigo, "nombre": "Teclado prueba E4",
          "descripcion": "Producto creado por la prueba E4", "precio": 59.9,
          "categoria_id": 1, "atributos": {"conexion": "USB", "distribucion": "Espanol"}}
imagen_ok = open(IMG_OK, "rb").read()

caso("1. GET /categorias")
st, _, c = http("GET", "/categorias")
check("200 y categorias de RDS", st == 200 and len(jsn(c)) >= 3)
check("coincide con RDS", len(jsn(c)) == rds("SELECT count(*) FROM categoria")[0][0])

caso("2. POST /productos valido (201 PENDIENTE)")
st, _, c = http("POST", "/productos", valido)
pid = jsn(c).get("producto_id", "")
check("201 con producto_id y PENDIENTE", st == 201 and pid and jsn(c).get("estado") == "PENDIENTE")
print(f"    producto_id = {pid}")
fila = rds("SELECT codigo, estado FROM producto WHERE producto_id = %s", (pid,))
check("RDS: existe y esta PENDIENTE", fila == [(codigo, "PENDIENTE")], str(fila))
item = dynamo(pid)
check("DynamoDB: existe con atributos", bool(item) and item["atributos"]["M"]["conexion"]["S"] == "USB")

caso("3. GET /productos/{id} y GET /productos (pendiente no se lista)")
st, _, c = http("GET", f"/productos/{pid}")
check("200 con estado PENDIENTE", st == 200 and jsn(c).get("estado") == "PENDIENTE")
st, _, c = http("GET", "/productos")
check("el pendiente NO aparece en el catalogo", st == 200 and pid not in [p["producto_id"] for p in jsn(c)])

caso("4. Codigo duplicado (409, sin registro extra)")
st, _, c = http("POST", "/productos", valido)
check("409", st == 409)
check("RDS: sigue habiendo 1 solo con ese codigo",
      rds("SELECT count(*) FROM producto WHERE codigo = %s", (codigo,))[0][0] == 1)

caso("5. Entradas invalidas (400, sin registros parciales)")
invalidos = [
    ("precio negativo", {**valido, "codigo": codigo + "-NEG", "precio": -5}),
    ("categoria inexistente", {**valido, "codigo": codigo + "-CAT", "categoria_id": 999}),
    ("falta nombre", {k: v for k, v in {**valido, "codigo": codigo + "-NOM"}.items() if k != "nombre"}),
    ("atributos vacios", {**valido, "codigo": codigo + "-ATR", "atributos": {}}),
    ("codigo vacio", {**valido, "codigo": ""}),
]
for nombre, cuerpo in invalidos:
    print(f"  [{nombre}]")
    st, _, c = http("POST", "/productos", cuerpo)
    check("400", st == 400)
check("RDS: ninguno de los invalidos se guardo",
      rds("SELECT count(*) FROM producto WHERE codigo LIKE %s", (codigo + "-%",))[0][0] == 0)

caso("6. Reprocesar sin imagen original (409)")
st, _, c = http("POST", f"/productos/{pid}/reprocesar")
check("409", st == 409)

caso("7. Imagen: formato no permitido (415)")
st, _, c = http("POST", f"/productos/{pid}/imagen", archivo=("nota.txt", b"hola", "text/plain"))
check("415", st == 415)

caso("8. Imagen: mayor a 5 MB (413)")
grande = b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024 + 10)
st, _, c = http("POST", f"/productos/{pid}/imagen", archivo=("grande.jpg", grande, "image/jpeg"))
check("413", st == 413)

caso("9. Imagen invalida con tipo JPEG (415, queda PENDIENTE)")
st, _, c = http("POST", f"/productos/{pid}/imagen", archivo=("falso.jpg", b"esto no es una imagen", "image/jpeg"))
check("415 con paso lambda", st == 415 and jsn(c).get("detail", {}).get("paso") == "lambda")
check("RDS: sigue PENDIENTE", rds("SELECT estado FROM producto WHERE producto_id = %s", (pid,)) == [("PENDIENTE",)])
check("DynamoDB: estado_procesamiento ERROR", dynamo(pid)["estado_procesamiento"]["S"] == "ERROR")
st, _, c = http("GET", f"/productos/{pid}/imagen")
check("GET imagen: 404", st == 404)

caso("10. Imagen valida completa el MISMO producto (200 PUBLICADO)")
st, _, c = http("POST", f"/productos/{pid}/imagen", archivo=("prueba.jpg", imagen_ok, "image/jpeg"))
check("200 PUBLICADO", st == 200 and jsn(c).get("estado") == "PUBLICADO")
check("RDS: PUBLICADO, un solo producto con ese codigo",
      rds("SELECT estado FROM producto WHERE codigo = %s", (codigo,)) == [("PUBLICADO",)])
item = dynamo(pid)
mkey = item["miniatura_key"].get("S")
check("DynamoDB: estado LISTA y miniatura_key", item["estado_procesamiento"]["S"] == "LISTA" and bool(mkey), str(mkey))
mini_s3 = s3.get_object(Bucket=BUCKET_MINI, Key=mkey)["Body"].read()
check("S3: miniatura existe", len(mini_s3) > 0, f"{len(mini_s3)} bytes")
print(f"    dimensiones de la miniatura en S3: {dims_jpeg(mini_s3)}")
check("miniatura de 300x200 (proporcional)", dims_jpeg(mini_s3) == (300, 200))

caso("11. GET /productos/{id}/imagen (200, mismos bytes que S3)")
st, cab, c = http("GET", f"/productos/{pid}/imagen")
check("200 con Content-Type image/jpeg", st == 200 and cab.get("content-type") == "image/jpeg")
check("SHA-256 del endpoint == SHA-256 de S3", hashlib.sha256(c).hexdigest() == hashlib.sha256(mini_s3).hexdigest(),
      hashlib.sha256(c).hexdigest()[:16])

caso("12. Idempotencia: repetir imagen y reprocesar no duplican objetos")
http("POST", f"/productos/{pid}/imagen", archivo=("prueba.jpg", imagen_ok, "image/jpeg"))
st, _, c = http("POST", f"/productos/{pid}/reprocesar")
check("reprocesar 200 PUBLICADO", st == 200 and jsn(c).get("estado") == "PUBLICADO")
objs = s3.list_objects_v2(Bucket=BUCKET_MINI, Prefix=f"miniaturas/{pid}").get("Contents", [])
check("S3: un solo objeto de miniatura para el producto", len(objs) == 1, str(len(objs)))

caso("13. GET /productos (solo publicados, con atributos y miniatura)")
st, _, c = http("GET", "/productos")
lista = jsn(c)
mio = [p for p in lista if p["producto_id"] == pid]
check("200 e incluye el producto publicado", st == 200 and len(mio) == 1)
check("trae atributos de DynamoDB", bool(mio) and mio[0]["atributos"].get("conexion") == "USB")
check("todos estan PUBLICADO", all(p["estado"] == "PUBLICADO" for p in lista))
check("cantidad == PUBLICADOS en RDS",
      len(lista) == rds("SELECT count(*) FROM producto WHERE estado = 'PUBLICADO'")[0][0], str(len(lista)))

caso("14. GET /productos/{id} detalle y 404")
st, _, c = http("GET", f"/productos/{pid}")
check("200 PUBLICADO y LISTA", st == 200 and jsn(c).get("estado") == "PUBLICADO"
      and jsn(c).get("estado_procesamiento") == "LISTA")
st, _, c = http("GET", f"/productos/{uuid.uuid4()}")
check("inexistente: 404", st == 404)
st, _, c = http("GET", "/productos/abc")
check("id mal formado: 404", st == 404)
st, _, c = http("GET", f"/productos/{uuid.uuid4()}/imagen")
check("imagen de inexistente: 404", st == 404)

print("\nRESULTADO:", "TODAS LAS VERIFICACIONES OK" if not fallos else f"{fallos} FALLO(S)")
sys.exit(1 if fallos else 0)