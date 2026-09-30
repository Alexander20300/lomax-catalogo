INSERT INTO producto (producto_id, codigo, nombre, descripcion, precio, categoria_id)
SELECT 'aaaaaaaa-0000-0000-0000-000000000001'::uuid, 'TEC-001', 'Teclado Mecanico K1',
       'Teclado mecanico con cable', 45.90, id
FROM categoria WHERE nombre = 'Teclados'
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO producto (producto_id, codigo, nombre, descripcion, precio, categoria_id)
SELECT 'aaaaaaaa-0000-0000-0000-000000000002'::uuid, 'PAN-001', 'Monitor 24 pulgadas',
       'Monitor Full HD para oficina', 189.00, id
FROM categoria WHERE nombre = 'Pantallas'
ON CONFLICT (codigo) DO NOTHING;