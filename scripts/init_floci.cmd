@echo off
set AWS_ENDPOINT_URL=http://localhost:4566
set AWS_DEFAULT_REGION=us-east-1
set AWS_ACCESS_KEY_ID=test
set AWS_SECRET_ACCESS_KEY=test

echo === RDS ===
aws rds describe-db-instances --db-instance-identifier lomax-db >nul 2>&1
if errorlevel 1 aws rds create-db-instance --db-instance-identifier lomax-db --engine postgres --db-instance-class db.t3.micro --allocated-storage 20 --master-username admin --master-user-password lomax12345 --db-name lomax >nul

set RDS=
:esperar
for /f %%i in ('docker ps --filter "name=floci-rds-db" --format "{{.Names}}"') do set RDS=%%i
if "%RDS%"=="" (timeout /t 3 >nul & goto esperar)
docker exec %RDS% pg_isready -U admin -d lomax >nul 2>&1
if errorlevel 1 (timeout /t 3 >nul & goto esperar)
echo Contenedor RDS: %RDS%

type scripts\rds_schema.sql | docker exec -i -e PGPASSWORD=lomax12345 %RDS% psql -U admin -d lomax
type scripts\seed_productos.sql | docker exec -i -e PGPASSWORD=lomax12345 %RDS% psql -U admin -d lomax

echo === DynamoDB ===
aws dynamodb describe-table --table-name productos_atributos >nul 2>&1
if errorlevel 1 aws dynamodb create-table --table-name productos_atributos --attribute-definitions AttributeName=producto_id,AttributeType=S --key-schema AttributeName=producto_id,KeyType=HASH --billing-mode PAY_PER_REQUEST >nul
aws dynamodb put-item --table-name productos_atributos --item file://scripts/dynamo_teclado.json
aws dynamodb put-item --table-name productos_atributos --item file://scripts/dynamo_pantalla.json
echo === Listo ===