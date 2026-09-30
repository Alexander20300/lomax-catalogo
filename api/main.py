import json
import os
import socket
import uuid
from contextlib import contextmanager
from decimal import Decimal

import boto3
import psycopg2
import psycopg2.errors
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from psycopg2.extras import RealDictCursor

ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://floci:4566")
REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
DB = dict(
    host=os.environ.get("DB_HOST", "floci"),
    port=int(os.environ.get("DB_PORT", "7001")),
    dbname=os.environ.get("DB_NAME", "lomax"),
    user=os.environ.get("DB_USER", "admin"),
    password=os.environ.get("DB_PASSWORD", "lomax12345"),
    connect_timeout=5,
)
BUCKET_ORIG = os.environ.get("BUCKET_ORIGINALES", "lomax-originales")
BUCKET_MINI = os.environ.get("BUCKET_MINIATURAS", "lomax-miniaturas")
TABLA = os.environ.get("TABLA_DYNAMO", "productos_atributos")
LAMBDA = os.environ.get("LAMBDA_NAME", "procesar-miniatura")
MAX_BYTES = 5 * 1024 * 1024
TIPOS = {"image/jpeg": "jpg", "image/png": "png"}
INSTANCIA = os.environ.get("HOSTNAME") or socket.gethostname()

cfg = Config(connect_timeout=5, read_timeout=30, retries={"max_attempts": 1})
cfg_lambda = Config(connect_timeout=5, read_timeout=120, retries={"max_attempts": 1})
s3 = boto3.client("s3", endpoint_url=ENDPOINT, region_name=REGION, config=cfg)
ddb = boto3.client("dynamodb", endpoint_url=ENDPOINT, region_name=REGION, config=cfg)
lam = boto3.client("lambda", endpoint_url=ENDPOINT, region_name=REGION, config=cfg_lambda)
ser, des = TypeSerializer(), TypeDeserializer()

app = FastAPI(title="Lomax Catalogo API")


@app.middleware("http")
async def cabecera_instancia(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Instancia"] = INSTANCIA
    return resp


@app.exception_handler(RequestValidationError)
async def solicitud_invalida(request, exc):
    return JSONResponse(status_code=400, content={
        "detail": {"paso": "validacion", "mensaje": "Solicitud invalida"}})


@app.exception_handler(psycopg2.OperationalError)
async def rds_caido(request, exc):
    return JSONResponse(status_code=503, content={
        "detail": {"paso": "rds", "mensaje": "RDS no disponible"}})


def error(status, paso, mensaje):
    raise HTTPException(status_code=status, detail={"paso": paso, "mensaje": mensaje})


def aws(paso, fn, **kw):
    try:
        return fn(**kw)
    except (BotoCoreError, ClientError) as e:
        error(502, paso, f"Fallo en {paso}: {e}")


@contextmanager
def conexion():
    try:
        conn = psycopg2.connect(**DB)
    except psycopg2.OperationalError:
        error(503, "rds", "No se pudo conectar a RDS")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_id(valor):
    try:
        return str(uuid.UUID(valor))
    except ValueError:
        error(404, "api", "Producto no encontrado")


def texto(body, campo, maximo):
    v = body.get(campo)
    if not isinstance(v, str) or not v.strip():
        error(400, "validacion", f"'{campo}' es obligatorio")
    v = v.strip()
    if len(v) > maximo:
        error(400, "validacion", f"'{campo}' supera {maximo} caracteres")
    return v


def limpiar(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dict):
        return {k: limpiar(x) for k, x in v.items()}
    if isinstance(v, list):
        return [limpiar(x) for x in v]
    return v


def item_a_dict(item):
    return {k: limpiar(des.deserialize(v)) for k, v in item.items()}


def leer_dynamo(pid):
    r = aws("dynamodb", ddb.get_item, TableName=TABLA, Key={"producto_id": {"S": pid}})
    return item_a_dict(r["Item"]) if r.get("Item") else None


COLS = ("p.producto_id, p.codigo, p.nombre, p.descripcion, p.precio, "
        "p.categoria_id, c.nombre AS categoria, p.fecha, p.estado")
FROM = "FROM producto p JOIN categoria c ON c.id = p.categoria_id"


def fila(r):
    return {"producto_id": str(r["producto_id"]), "codigo": r["codigo"],
            "nombre": r["nombre"], "descripcion": r["descripcion"],
            "precio": float(r["precio"]), "categoria_id": r["categoria_id"],
            "categoria": r["categoria"], "fecha": r["fecha"].isoformat(),
            "estado": r["estado"]}


def existe_producto(pid):
    with conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM producto WHERE producto_id = %s", (pid,))
        if not cur.fetchone():
            error(404, "rds", "Producto no encontrado")


def cambiar_estado(pid, estado):
    with conexion() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE producto SET estado = %s WHERE producto_id = %s", (estado, pid))


def procesar(pid, key):
    """Invoca Lambda (sincrono), verifica miniatura y atributos, y publica."""
    payload = json.dumps({"producto_id": pid, "bucket": BUCKET_ORIG, "key": key})
    r = aws("lambda", lam.invoke, FunctionName=LAMBDA,
            InvocationType="RequestResponse", Payload=payload.encode())
    cuerpo = r["Payload"].read()
    if r.get("FunctionError"):
        error(502, "lambda", "La funcion Lambda fallo: " + cuerpo.decode()[:300])
    try:
        res = json.loads(cuerpo)
    except ValueError:
        error(502, "lambda", "Respuesta invalida de Lambda")
    if res.get("estado") != "LISTA":
        cambiar_estado(pid, "PENDIENTE")
        error(415, "lambda", "Imagen invalida o no procesable: " + str(res.get("detalle", "")))

    item = leer_dynamo(pid)
    if (not item or item.get("estado_procesamiento") != "LISTA"
            or not item.get("miniatura_key") or not item.get("atributos")):
        error(503, "dynamodb", "No se pudo confirmar atributos y miniatura")
    try:
        s3.head_object(Bucket=BUCKET_MINI, Key=item["miniatura_key"])
    except (BotoCoreError, ClientError):
        error(503, "s3", "La miniatura no existe en S3")

    cambiar_estado(pid, "PUBLICADO")
    return {"producto_id": pid, "estado": "PUBLICADO", "miniatura_key": item["miniatura_key"]}


@app.get("/health")
def health():
    return {"ok": True, "instancia": INSTANCIA}


@app.get("/categorias")
def categorias():
    with conexion() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT id, nombre FROM categoria ORDER BY id")
        return [dict(r) for r in cur.fetchall()]


@app.post("/productos", status_code=201)
def crear_producto(body: dict = Body(...)):
    codigo = texto(body, "codigo", 50)
    nombre = texto(body, "nombre", 150)
    descripcion = texto(body, "descripcion", 2000)
    precio = body.get("precio")
    if (isinstance(precio, bool) or not isinstance(precio, (int, float))
            or precio < 0 or precio > 99999999.99):
        error(400, "validacion", "'precio' debe ser un numero no negativo")
    categoria_id = body.get("categoria_id")
    if isinstance(categoria_id, bool) or not isinstance(categoria_id, int):
        error(400, "validacion", "'categoria_id' debe ser un entero")
    atributos = body.get("atributos")
    if not isinstance(atributos, dict) or not atributos:
        error(400, "validacion", "'atributos' debe ser un objeto con al menos un atributo")

    with conexion() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM categoria WHERE id = %s", (categoria_id,))
        if not cur.fetchone():
            error(400, "validacion", "La categoria no existe")
        try:
            cur.execute(
                "INSERT INTO producto (codigo, nombre, descripcion, precio, categoria_id) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING producto_id",
                (codigo, nombre, descripcion, Decimal(str(precio)), categoria_id))
        except psycopg2.errors.UniqueViolation:
            error(409, "rds", "Ya existe un producto con ese codigo")
        pid = str(cur.fetchone()[0])
        item = {
            "producto_id": {"S": pid},
            "atributos": ser.serialize(json.loads(json.dumps(atributos), parse_float=Decimal)),
            "imagen_original_key": {"NULL": True},
            "miniatura_key": {"NULL": True},
            "estado_procesamiento": {"S": "PENDIENTE"},
        }
        # Si DynamoDB falla, se lanza excepcion y RDS hace rollback (sin registros parciales)
        aws("dynamodb", ddb.put_item, TableName=TABLA, Item=item)
    return {"producto_id": pid, "estado": "PENDIENTE"}


@app.post("/productos/{producto_id}/imagen")
def subir_imagen(producto_id: str, archivo: UploadFile = File(...)):
    pid = parse_id(producto_id)
    existe_producto(pid)
    ext = TIPOS.get(archivo.content_type)
    if not ext:
        error(415, "validacion", "Solo se permite JPEG o PNG")
    datos = archivo.file.read(MAX_BYTES + 1)
    if len(datos) > MAX_BYTES:
        error(413, "validacion", "El archivo supera 5 MB")
    if not datos:
        error(400, "validacion", "El archivo esta vacio")

    key = f"originales/{pid}.{ext}"
    otra = f"originales/{pid}.{'png' if ext == 'jpg' else 'jpg'}"
    aws("s3", s3.put_object, Bucket=BUCKET_ORIG, Key=key, Body=datos,
        ContentType=archivo.content_type)
    aws("s3", s3.delete_object, Bucket=BUCKET_ORIG, Key=otra)
    aws("dynamodb", ddb.update_item, TableName=TABLA, Key={"producto_id": {"S": pid}},
        UpdateExpression="SET imagen_original_key = :k",
        ExpressionAttributeValues={":k": {"S": key}})
    return procesar(pid, key)


@app.post("/productos/{producto_id}/reprocesar")
def reprocesar(producto_id: str):
    pid = parse_id(producto_id)
    existe_producto(pid)
    item = leer_dynamo(pid)
    key = item.get("imagen_original_key") if item else None
    if not key:
        error(409, "dynamodb", "El producto no tiene imagen original registrada")
    try:
        s3.head_object(Bucket=BUCKET_ORIG, Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            error(409, "s3", "No existe la imagen original en S3")
        error(502, "s3", f"Fallo en s3: {e}")
    except BotoCoreError as e:
        error(502, "s3", f"Fallo en s3: {e}")
    return procesar(pid, key)


@app.get("/productos")
def listar():
    with conexion() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"SELECT {COLS} {FROM} WHERE p.estado = 'PUBLICADO' "
                    "ORDER BY p.fecha DESC, p.codigo")
        filas = [fila(r) for r in cur.fetchall()]
    ids = [f["producto_id"] for f in filas]
    attrs = {}
    for i in range(0, len(ids), 100):
        r = aws("dynamodb", ddb.batch_get_item, RequestItems={TABLA: {
            "Keys": [{"producto_id": {"S": x}} for x in ids[i:i + 100]]}})
        for it in r["Responses"].get(TABLA, []):
            d = item_a_dict(it)
            attrs[d["producto_id"]] = d
    for f in filas:
        d = attrs.get(f["producto_id"], {})
        f["atributos"] = d.get("atributos") or {}
        f["miniatura_key"] = d.get("miniatura_key")
        f["imagen_url"] = f"/productos/{f['producto_id']}/imagen"
    return filas


@app.get("/productos/{producto_id}")
def detalle(producto_id: str):
    pid = parse_id(producto_id)
    with conexion() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"SELECT {COLS} {FROM} WHERE p.producto_id = %s", (pid,))
        r = cur.fetchone()
    if not r:
        error(404, "rds", "Producto no encontrado")
    f = fila(r)
    d = leer_dynamo(pid) or {}
    f["atributos"] = d.get("atributos") or {}
    f["estado_procesamiento"] = d.get("estado_procesamiento")
    f["imagen_original_key"] = d.get("imagen_original_key")
    f["miniatura_key"] = d.get("miniatura_key")
    f["imagen_url"] = f"/productos/{pid}/imagen"
    return f


@app.get("/productos/{producto_id}/imagen")
def imagen(producto_id: str):
    pid = parse_id(producto_id)
    d = leer_dynamo(pid)
    key = d.get("miniatura_key") if d else None
    if not key or d.get("estado_procesamiento") != "LISTA":
        error(404, "dynamodb", "Miniatura no disponible")
    try:
        obj = s3.get_object(Bucket=BUCKET_MINI, Key=key)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            error(404, "s3", "Miniatura no disponible")
        error(502, "s3", f"Fallo en s3: {e}")
    except BotoCoreError as e:
        error(502, "s3", f"Fallo en s3: {e}")
    return Response(content=obj["Body"].read(),
                    media_type=obj.get("ContentType", "image/jpeg"))