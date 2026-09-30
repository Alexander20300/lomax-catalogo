CREATE TABLE IF NOT EXISTS categoria (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(80) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS producto (
    producto_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo VARCHAR(50) NOT NULL UNIQUE,
    nombre VARCHAR(150) NOT NULL,
    descripcion TEXT NOT NULL,
    precio NUMERIC(10,2) NOT NULL CHECK (precio >= 0),
    categoria_id INT NOT NULL REFERENCES categoria(id),
    fecha TIMESTAMP NOT NULL DEFAULT now(),
    estado VARCHAR(10) NOT NULL DEFAULT 'PENDIENTE'
        CHECK (estado IN ('PENDIENTE','PUBLICADO'))
);

INSERT INTO categoria (nombre) VALUES ('Teclados'), ('Pantallas'), ('Mouses')
ON CONFLICT (nombre) DO NOTHING;