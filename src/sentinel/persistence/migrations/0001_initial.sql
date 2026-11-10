-- SENTINEL AI — esquema v1 (docs/ARQUITETURA.md §8)
-- Convenções:
--   * IDs de entidades de negócio: TEXT com UUID v4.
--   * Horários: INTEGER em milissegundos Unix UTC (sufixo _ms).
--   * Caminhos de arquivo: relativos à raiz de dados (sufixo _rel).
--   * Colunas *_enc: conteúdo criptografado pela aplicação (AES-256-GCM).

CREATE TABLE schema_migrations (
    version        INTEGER PRIMARY KEY,
    name           TEXT    NOT NULL,
    applied_at_ms  INTEGER NOT NULL
);

-- ------------------------------------------------------------------ configurações
CREATE TABLE settings (
    key            TEXT PRIMARY KEY,
    value_json     TEXT    NOT NULL CHECK (json_valid(value_json)),
    updated_at_ms  INTEGER NOT NULL
);

-- ------------------------------------------------------------------ câmeras
CREATE TABLE cameras (
    id             TEXT PRIMARY KEY,
    name           TEXT    NOT NULL,
    kind           TEXT    NOT NULL CHECK (kind IN ('local', 'rtsp', 'onvif')),
    device_ref     TEXT,                       -- ID estável do dispositivo local
    secret_ref     TEXT,                       -- referência ao cofre do SO (nunca a senha)
    enabled        INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    width          INTEGER CHECK (width  > 0),
    height         INTEGER CHECK (height > 0),
    fps            REAL    CHECK (fps > 0),
    codec_pref     TEXT,
    quality        TEXT    NOT NULL DEFAULT 'medium' CHECK (quality IN ('low', 'medium', 'high')),
    created_at_ms  INTEGER NOT NULL,
    updated_at_ms  INTEGER NOT NULL
);

CREATE TABLE camera_settings (
    camera_id                 TEXT PRIMARY KEY REFERENCES cameras(id) ON DELETE CASCADE,
    motion_sensitivity        INTEGER NOT NULL DEFAULT 5 CHECK (motion_sensitivity BETWEEN 1 AND 10),
    roi_json                  TEXT    CHECK (roi_json IS NULL OR json_valid(roi_json)),
    schedule_json             TEXT    CHECK (schedule_json IS NULL OR json_valid(schedule_json)),
    min_event_gap_s           REAL    NOT NULL DEFAULT 10 CHECK (min_event_gap_s >= 0),
    ai_fps                    REAL    NOT NULL DEFAULT 2  CHECK (ai_fps > 0),
    person_detection_enabled  INTEGER NOT NULL DEFAULT 1 CHECK (person_detection_enabled IN (0, 1))
);

CREATE TABLE retention_policies (
    id                INTEGER PRIMARY KEY,
    scope             TEXT    NOT NULL CHECK (scope IN ('global', 'camera')),
    camera_id         TEXT    REFERENCES cameras(id) ON DELETE CASCADE,
    max_days          INTEGER CHECK (max_days > 0),
    max_bytes         INTEGER CHECK (max_bytes > 0),
    min_free_bytes    INTEGER CHECK (min_free_bytes >= 0),
    protect_events    INTEGER NOT NULL DEFAULT 1 CHECK (protect_events IN (0, 1)),
    CHECK ((scope = 'global' AND camera_id IS NULL) OR (scope = 'camera' AND camera_id IS NOT NULL))
);
CREATE UNIQUE INDEX ux_retention_global ON retention_policies(scope) WHERE scope = 'global';
CREATE UNIQUE INDEX ux_retention_camera ON retention_policies(camera_id) WHERE camera_id IS NOT NULL;

-- ------------------------------------------------------------------ sessões de vigilância
CREATE TABLE surveillance_sessions (
    id                       TEXT PRIMARY KEY,
    started_at_ms            INTEGER NOT NULL,
    ended_at_ms              INTEGER,
    desired_state            TEXT    NOT NULL CHECK (desired_state IN ('STOPPED', 'ACTIVE', 'PAUSED')),
    observed_state           TEXT    NOT NULL CHECK (observed_state IN
                                 ('STOPPED', 'STARTING', 'ACTIVE', 'PAUSED', 'STOPPING', 'ERROR')),
    state_reason             TEXT,
    end_reason               TEXT    CHECK (end_reason IN ('USER_STOP', 'INTERRUPTED', 'ERROR')),
    last_heartbeat_at_ms     INTEGER,
    resumed_from_session_id  TEXT    REFERENCES surveillance_sessions(id) ON DELETE SET NULL,
    CHECK (ended_at_ms IS NULL OR ended_at_ms >= started_at_ms)
);
-- No máximo uma sessão aberta por vez.
CREATE UNIQUE INDEX ux_sessions_single_open ON surveillance_sessions((1)) WHERE ended_at_ms IS NULL;
CREATE INDEX ix_sessions_started ON surveillance_sessions(started_at_ms);

CREATE TABLE session_cameras (
    session_id  TEXT NOT NULL REFERENCES surveillance_sessions(id) ON DELETE CASCADE,
    camera_id   TEXT NOT NULL REFERENCES cameras(id) ON DELETE RESTRICT,
    PRIMARY KEY (session_id, camera_id)
);

-- ------------------------------------------------------------------ gravações
CREATE TABLE recordings (
    id             TEXT PRIMARY KEY,
    session_id     TEXT    NOT NULL REFERENCES surveillance_sessions(id) ON DELETE RESTRICT,
    camera_id      TEXT    NOT NULL REFERENCES cameras(id) ON DELETE RESTRICT,
    started_at_ms  INTEGER NOT NULL,
    ended_at_ms    INTEGER,
    CHECK (ended_at_ms IS NULL OR ended_at_ms >= started_at_ms)
);
CREATE INDEX ix_recordings_camera_start ON recordings(camera_id, started_at_ms);

CREATE TABLE segments (
    id             TEXT PRIMARY KEY,
    recording_id   TEXT    NOT NULL REFERENCES recordings(id) ON DELETE RESTRICT,
    camera_id      TEXT    NOT NULL REFERENCES cameras(id) ON DELETE RESTRICT,
    seq            INTEGER NOT NULL CHECK (seq >= 0),
    path_rel       TEXT    NOT NULL UNIQUE,
    status         TEXT    NOT NULL CHECK (status IN
                       ('WRITING', 'CLOSED', 'RECOVERED', 'CORRUPT', 'MISSING', 'DELETING')),
    start_ms       INTEGER NOT NULL,
    end_ms         INTEGER,
    duration_ms    INTEGER CHECK (duration_ms >= 0),
    bytes          INTEGER CHECK (bytes >= 0),
    codec          TEXT,
    width          INTEGER,
    height         INTEGER,
    fps            REAL,
    sha256         TEXT,
    protected      INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
    created_at_ms  INTEGER NOT NULL,
    UNIQUE (recording_id, seq)
);
CREATE INDEX ix_segments_camera_start ON segments(camera_id, start_ms);
CREATE INDEX ix_segments_status ON segments(status);

-- ------------------------------------------------------------------ pessoas (biometria opcional)
CREATE TABLE people (
    id                 TEXT PRIMARY KEY,
    name_enc           BLOB    NOT NULL,
    description_enc    BLOB,
    created_at_ms      INTEGER NOT NULL,
    first_seen_at_ms   INTEGER,
    last_seen_at_ms    INTEGER,
    appearance_count   INTEGER NOT NULL DEFAULT 0 CHECK (appearance_count >= 0)
);

CREATE TABLE consents (
    id              TEXT PRIMARY KEY,
    person_id       TEXT    NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    granted_at_ms   INTEGER NOT NULL,
    granted_by      TEXT    NOT NULL,
    scope           TEXT    NOT NULL,
    revoked_at_ms   INTEGER,
    evidence_note   TEXT
);
CREATE INDEX ix_consents_person ON consents(person_id);

CREATE TABLE person_references (
    id              TEXT PRIMARY KEY,
    person_id       TEXT    NOT NULL REFERENCES people(id) ON DELETE CASCADE,
    image_rel       TEXT    NOT NULL UNIQUE,
    embedding_enc   BLOB,
    model_version   TEXT,
    created_at_ms   INTEGER NOT NULL
);
CREATE INDEX ix_person_refs_person ON person_references(person_id);

-- ------------------------------------------------------------------ eventos
CREATE TABLE events (
    id                  TEXT PRIMARY KEY,
    camera_id           TEXT    NOT NULL REFERENCES cameras(id) ON DELETE RESTRICT,
    session_id          TEXT    REFERENCES surveillance_sessions(id) ON DELETE SET NULL,
    type                TEXT    NOT NULL CHECK (type IN
                            ('MOTION', 'PERSON', 'ANIMAL', 'VEHICLE', 'LIGHTING_CHANGE',
                             'CAMERA_LOST', 'CAMERA_RESTORED', 'STORAGE_CRITICAL')),
    started_at_ms       INTEGER NOT NULL,
    ended_at_ms         INTEGER,
    peak_confidence     REAL    CHECK (peak_confidence BETWEEN 0 AND 1),
    max_people          INTEGER CHECK (max_people >= 0),
    thumbnail_rel       TEXT,
    primary_segment_id  TEXT    REFERENCES segments(id) ON DELETE SET NULL,
    offset_ms           INTEGER CHECK (offset_ms >= 0),
    person_id           TEXT    REFERENCES people(id) ON DELETE SET NULL,
    review_status       TEXT    NOT NULL DEFAULT 'NONE'
                            CHECK (review_status IN ('NONE', 'PENDING', 'CONFIRMED', 'REJECTED')),
    protected           INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0, 1)),
    CHECK (ended_at_ms IS NULL OR ended_at_ms >= started_at_ms)
);
CREATE INDEX ix_events_camera_start ON events(camera_id, started_at_ms);
CREATE INDEX ix_events_type_start ON events(type, started_at_ms);
CREATE INDEX ix_events_person ON events(person_id) WHERE person_id IS NOT NULL;
CREATE INDEX ix_events_review ON events(review_status) WHERE review_status = 'PENDING';

-- Um evento pode atravessar vários segmentos.
CREATE TABLE event_segments (
    event_id    TEXT NOT NULL REFERENCES events(id)   ON DELETE CASCADE,
    segment_id  TEXT NOT NULL REFERENCES segments(id) ON DELETE CASCADE,
    PRIMARY KEY (event_id, segment_id)
);
CREATE INDEX ix_event_segments_segment ON event_segments(segment_id);

-- Detecções amostradas (no máximo ~1/s por track), não por frame.
CREATE TABLE detections (
    id          INTEGER PRIMARY KEY,
    event_id    TEXT    NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    ts_ms       INTEGER NOT NULL,
    track_id    INTEGER,
    class       TEXT    NOT NULL,
    confidence  REAL    NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    bbox_json   TEXT    NOT NULL CHECK (json_valid(bbox_json))
);
CREATE INDEX ix_detections_event ON detections(event_id);

CREATE TABLE match_reviews (
    id                   TEXT PRIMARY KEY,
    event_id             TEXT    NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    candidate_person_id  TEXT    REFERENCES people(id) ON DELETE CASCADE,
    score                REAL    NOT NULL,
    decision             TEXT    CHECK (decision IN ('CONFIRMED', 'REJECTED')),
    decided_by           TEXT,
    decided_at_ms        INTEGER
);
CREATE INDEX ix_match_reviews_event ON match_reviews(event_id);

-- ------------------------------------------------------------------ histórico operacional
-- Sem dados sensíveis (nomes, credenciais, imagens).
CREATE TABLE operation_log (
    id            INTEGER PRIMARY KEY,
    ts_ms         INTEGER NOT NULL,
    actor         TEXT    NOT NULL CHECK (actor IN ('user', 'agent', 'system')),
    action        TEXT    NOT NULL,
    target        TEXT,
    details_json  TEXT    CHECK (details_json IS NULL OR json_valid(details_json))
);
CREATE INDEX ix_operation_log_ts ON operation_log(ts_ms);

-- Estado do agente (linha única): última parada limpa e heartbeat.
CREATE TABLE agent_state (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    clean_shutdown        INTEGER NOT NULL DEFAULT 1 CHECK (clean_shutdown IN (0, 1)),
    last_started_at_ms    INTEGER,
    last_heartbeat_at_ms  INTEGER,
    agent_version         TEXT
);
INSERT INTO agent_state(id) VALUES (1);
