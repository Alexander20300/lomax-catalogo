\echo === 1. Insercion valida ===
INSERT INTO producto (codigo, nombre, descripcion, precio, categoria_id)
VALUES ('TEST-VALIDO', 'Producto de prueba', 'Prueba valida', 10.00, 1)
RETURNING producto_id, codigo;

\echo === 2. Codigo duplicado (debe fallar) ===
INSERT INTO producto (codigo, nombre, descripcion, precio, categoria_id)
VALUES ('TEC-001', 'Duplicado', 'Prueba', 10.00, 1);

\echo === 3. Precio negativo (debe fallar) ===
INSERT INTO producto (codigo, nombre, descripcion, precio, categoria_id)
VALUES ('TEST-NEG', 'Negativo', 'Prueba', -5.00, 1);

\echo === 4. Categoria inexistente (debe fallar) ===
INSERT INTO producto (codigo, nombre, descripcion, precio, categoria_id)
VALUES ('TEST-CAT', 'Sin categoria', 'Prueba', 10.00, 999);

\echo === 5. Nombre nulo (debe fallar) ===
INSERT INTO producto (codigo, nombre, descripcion, precio, categoria_id)
VALUES ('TEST-NULO', NULL, 'Prueba', 10.00, 1);

\echo === Verificacion: no quedaron registros parciales ===
SELECT codigo FROM producto ORDER BY codigo;

DELETE FROM producto WHERE codigo = 'TEST-VALIDO';