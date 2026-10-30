-- =====================================================================
-- DRNO — Digital Radicalization Network Observatory
-- Skema PostgreSQL (tahap 2). Prinsip: data teramati, hasil mesin, dan
-- interpretasi peneliti disimpan di tabel TERPISAH agar selalu dapat
-- dibedakan dan diaudit.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------- Kamus kata kunci berversi (penelitian longitudinal) ----------
CREATE TABLE keyword_dictionary_version (
    version_id      SERIAL PRIMARY KEY,
    label           TEXT NOT NULL,                 -- mis. "v1.0-baseline"
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      TEXT NOT NULL,                 -- peneliti, bukan mesin
    note            TEXT
);

CREATE TABLE keyword (
    keyword_id      SERIAL PRIMARY KEY,
    version_id      INT NOT NULL REFERENCES keyword_dictionary_version(version_id),
    term            TEXT NOT NULL,
    group_code      TEXT NOT NULL CHECK (group_code IN
                    ('radikalisasi','terorisme','narasi_digital','keagamaan',
                     'ideologis','politik_keagamaan','konflik','pencegahan')),
    variants        TEXT[] NOT NULL DEFAULT '{}',  -- transliterasi, salah eja, hashtag
    is_baseline_comparison BOOLEAN NOT NULL DEFAULT false, -- istilah keagamaan umum sbg pembanding
    UNIQUE (version_id, term)
);

-- Usulan kata kunci dari semantic discovery: WAJIB ditinjau peneliti
CREATE TABLE keyword_suggestion (
    suggestion_id   SERIAL PRIMARY KEY,
    seed_term       TEXT NOT NULL,
    suggested_term  TEXT NOT NULL,
    similarity      REAL NOT NULL,
    model_name      TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','accepted','rejected')),
    reviewed_by     TEXT,
    reviewed_at     TIMESTAMPTZ,
    review_note     TEXT
);

-- ---------- Pengumpulan data ----------
CREATE TABLE collection_job (
    job_id          SERIAL PRIMARY KEY,
    platform        TEXT NOT NULL,
    query           TEXT NOT NULL,                 -- ekspresi Boolean
    dictionary_version INT REFERENCES keyword_dictionary_version(version_id),
    language        TEXT DEFAULT 'id',
    date_from       DATE NOT NULL,
    date_to         DATE NOT NULL,
    max_records     INT NOT NULL DEFAULT 1000,
    interval_minutes INT,
    source_method   TEXT NOT NULL,                 -- 'official_api' | 'rss' | 'synthetic'
    legal_basis     TEXT NOT NULL,                 -- ToS/izin yang menjadi dasar akses
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE collection_run (
    run_id          SERIAL PRIMARY KEY,
    job_id          INT NOT NULL REFERENCES collection_job(job_id),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL CHECK (status IN ('running','success','partial','failed','rate_limited')),
    fetched         INT DEFAULT 0,
    inserted        INT DEFAULT 0,
    duplicates      INT DEFAULT 0,
    error_message   TEXT
);

-- Akun disimpan HANYA dalam bentuk pseudonim. Kunci HMAC disimpan di luar DB.
CREATE TABLE author (
    author_pseudonym TEXT PRIMARY KEY,             -- HMAC-SHA256(platform:id, secret)
    platform        TEXT NOT NULL,
    author_type     TEXT NOT NULL DEFAULT 'individual'
                    CHECK (author_type IN ('individual','media','organization_public','channel')),
    public_entity_name TEXT,                       -- hanya untuk media/organisasi publik
    first_seen      TIMESTAMPTZ,
    last_seen       TIMESTAMPTZ,
    CHECK (author_type <> 'individual' OR public_entity_name IS NULL)
);

-- FAKTA TERAMATI
CREATE TABLE post (
    post_id         TEXT PRIMARY KEY,              -- platform:native_id (di-hash bila perlu)
    platform        TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    text            TEXT NOT NULL,
    url             TEXT,
    author_id_pseudonym TEXT NOT NULL REFERENCES author(author_pseudonym),
    language        TEXT,
    keyword_matched TEXT[] NOT NULL DEFAULT '{}',
    reply_to        TEXT,
    mention         TEXT[] NOT NULL DEFAULT '{}',  -- pseudonim
    repost_of       TEXT,
    engagement_count INT DEFAULT 0,
    collection_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_method   TEXT NOT NULL,
    is_synthetic    BOOLEAN NOT NULL,              -- wajib diisi; tak boleh NULL
    run_id          INT REFERENCES collection_run(run_id),
    content_hash    TEXT NOT NULL,                 -- deduplikasi
    retention_until DATE NOT NULL                  -- masa retensi
);
CREATE UNIQUE INDEX ux_post_dedup ON post(platform, content_hash, author_id_pseudonym, timestamp);
CREATE INDEX ix_post_time ON post(timestamp);
CREATE INDEX ix_post_kw ON post USING GIN(keyword_matched);

-- INTERAKSI TERAMATI (dasar jaringan interaksi)
CREATE TABLE interaction (
    interaction_id  BIGSERIAL PRIMARY KEY,
    source_author   TEXT NOT NULL REFERENCES author(author_pseudonym),
    target_author   TEXT NOT NULL REFERENCES author(author_pseudonym),
    interaction_type TEXT NOT NULL CHECK (interaction_type IN ('reply','mention','repost','comment','comment_reply')),
    post_id         TEXT NOT NULL REFERENCES post(post_id),  -- bukti relasi
    timestamp       TIMESTAMPTZ NOT NULL,
    platform        TEXT NOT NULL
);

-- HASIL KLASIFIKASI MESIN (terpisah dari fakta)
CREATE TABLE machine_annotation (
    annotation_id   BIGSERIAL PRIMARY KEY,
    post_id         TEXT NOT NULL REFERENCES post(post_id),
    task            TEXT NOT NULL CHECK (task IN ('context','stance','sentiment','topic','narrative','ner','language')),
    label           TEXT NOT NULL,
    confidence      REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    model_name      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_uncertain    BOOLEAN GENERATED ALWAYS AS (confidence < 0.6) STORED
);

-- VALIDASI MANUAL PENELITI (gold standard & koreksi)
CREATE TABLE manual_annotation (
    manual_id       BIGSERIAL PRIMARY KEY,
    post_id         TEXT NOT NULL REFERENCES post(post_id),
    task            TEXT NOT NULL,
    label           TEXT NOT NULL,
    coder           TEXT NOT NULL,                 -- pengode 1/2 untuk reliabilitas
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    note            TEXT
);

-- INTERPRETASI PENELITI (tidak pernah diturunkan otomatis)
CREATE TABLE researcher_memo (
    memo_id         BIGSERIAL PRIMARY KEY,
    scope           TEXT NOT NULL,                 -- 'post' | 'community' | 'period' | 'network'
    scope_ref       TEXT NOT NULL,
    memo            TEXT NOT NULL,
    author          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Snapshot metrik jaringan per periode (hasil komputasi, berversi)
CREATE TABLE network_snapshot (
    snapshot_id     SERIAL PRIMARY KEY,
    network_kind    TEXT NOT NULL CHECK (network_kind IN ('interaction','narrative_cooccurrence')),
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    filters         JSONB NOT NULL DEFAULT '{}',
    n_nodes INT, n_edges INT, density REAL, modularity REAL, n_components INT,
    algorithm       TEXT NOT NULL,
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE node_metric (
    snapshot_id     INT NOT NULL REFERENCES network_snapshot(snapshot_id),
    node_id         TEXT NOT NULL,
    community       INT,
    degree REAL, in_degree REAL, out_degree REAL, betweenness REAL,
    closeness REAL, eigenvector REAL, pagerank REAL,
    PRIMARY KEY (snapshot_id, node_id)
);

-- Audit log seluruh aksi
CREATE TABLE audit_log (
    log_id          BIGSERIAL PRIMARY KEY,
    at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor           TEXT NOT NULL,
    action          TEXT NOT NULL,
    object_ref      TEXT,
    detail          JSONB
);

-- Catatan bias sumber & keterbatasan API (wajib diisi per job)
CREATE TABLE source_limitation (
    limitation_id   SERIAL PRIMARY KEY,
    platform        TEXT NOT NULL,
    description     TEXT NOT NULL,
    recorded_by     TEXT NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Retensi: jalankan terjadwal
-- DELETE FROM post WHERE retention_until < CURRENT_DATE;
