-- Fase 3: adiciona o tipo de câmera 'file' (arquivo de vídeo para testes e demonstração).
-- SQLite não altera CHECK: a tabela é recriada (procedimento oficial de 12 passos;
-- o migrador desliga foreign_keys durante a migração e roda foreign_key_check antes do COMMIT).

CREATE TABLE cameras_new (
    id             TEXT PRIMARY KEY,
    name           TEXT    NOT NULL,
    kind           TEXT    NOT NULL CHECK (kind IN ('local', 'rtsp', 'onvif', 'file')),
    device_ref     TEXT,
    secret_ref     TEXT,
    enabled        INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    width          INTEGER CHECK (width  > 0),
    height         INTEGER CHECK (height > 0),
    fps            REAL    CHECK (fps > 0),
    codec_pref     TEXT,
    quality        TEXT    NOT NULL DEFAULT 'medium' CHECK (quality IN ('low', 'medium', 'high')),
    created_at_ms  INTEGER NOT NULL,
    updated_at_ms  INTEGER NOT NULL
);

INSERT INTO cameras_new
SELECT id, name, kind, device_ref, secret_ref, enabled, width, height, fps, codec_pref, quality,
       created_at_ms, updated_at_ms
FROM cameras;

DROP TABLE cameras;
ALTER TABLE cameras_new RENAME TO cameras;
