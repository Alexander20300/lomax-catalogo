import io
import os

import boto3
from PIL import Image

ENDPOINT = os.environ.get("APP_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL")
BUCKET_MINIATURAS = os.environ.get("BUCKET_MINIATURAS", "lomax-miniaturas")
TABLA = os.environ.get("TABLA_DYNAMO", "productos_atributos")
MAX_BYTES = 5 * 1024 * 1024
FORMATOS = {"JPEG", "PNG"}

kw = {"endpoint_url": ENDPOINT} if ENDPOINT else {}
s3 = boto3.client("s3", **kw)
ddb = boto3.client("dynamodb", **kw)


def marcar(producto_id, estado, original_key=None, miniatura_key=None):
    expr = "SET estado_procesamiento = :e, miniatura_key = :m"
    vals = {
        ":e": {"S": estado},
        ":m": {"S": miniatura_key} if miniatura_key else {"NULL": True},
    }
    if original_key:
        expr += ", imagen_original_key = :o"
        vals[":o"] = {"S": original_key}
    ddb.update_item(
        TableName=TABLA,
        Key={"producto_id": {"S": producto_id}},
        UpdateExpression=expr,
        ExpressionAttributeValues=vals,
    )


def lambda_handler(event, context):
    producto_id = event["producto_id"]
    bucket = event["bucket"]
    key = event["key"]
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
        if head["ContentLength"] > MAX_BYTES:
            raise ValueError("La imagen supera 5 MB")
        data = s3.get_object(Bucket=bucket, Key=key)["Body"].read()

        img = Image.open(io.BytesIO(data))
        if img.format not in FORMATOS:
            raise ValueError("Formato no permitido: " + str(img.format))
        img.verify()

        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((300, 300))  # conserva la proporcion
        salida = io.BytesIO()
        img.save(salida, "JPEG", quality=85)

        mkey = f"miniaturas/{producto_id}.jpg"  # clave determinista
        s3.put_object(Bucket=BUCKET_MINIATURAS, Key=mkey,
                      Body=salida.getvalue(), ContentType="image/jpeg")
        marcar(producto_id, "LISTA", key, mkey)
        return {"producto_id": producto_id, "estado": "LISTA",
                "miniatura_key": mkey, "ancho": img.width, "alto": img.height}
    except Exception as e:
        marcar(producto_id, "ERROR", key)
        return {"producto_id": producto_id, "estado": "ERROR", "detalle": str(e)}