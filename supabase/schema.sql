-- ============================================================================
-- SafetyBuddy — Supabase / Postgres schema (pgvector)
--
-- Everything lives in a dedicated schema (default: safety_buddy) so it never
-- collides with other apps on the same self-hosted Supabase instance.
-- Run once (psql or the Supabase SQL editor):
--     psql "$SUPABASE_DB_URL" -v schema=safety_buddy -f supabase/schema.sql
-- or simply:  bash scripts/setup_supabase.sh
--
-- Embedding dimension is 768 (nomic-embed-text-v1.5). If you change EMBED_MODEL
-- to a different dimension, update every vector(768) below and re-run.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS vector;      -- pgvector (cosine ANN)
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- fuzzy text helpers (optional)

CREATE SCHEMA IF NOT EXISTS safety_buddy;
SET search_path = safety_buddy, public;

-- ---------------------------------------------------------------------------
-- kb_chunks : one retrievable PPE/OSHA passage per row, with its embedding.
-- The chunker emits rich metadata (filename, doc_type, page, chunk_index);
-- we keep doc_type/filename/page as columns for stats + the full dict in JSONB.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kb_chunks (
    id          BIGSERIAL PRIMARY KEY,
    chunk_uid   TEXT UNIQUE NOT NULL,        -- chunker id (e.g. osha_1910_132_chunk3); dedup
    content     TEXT NOT NULL,
    embedding   VECTOR(768),
    filename    TEXT,
    doc_type    TEXT,                        -- regulation / safety_manual / operating_procedure / incident_report
    page        INT,
    metadata    JSONB DEFAULT '{}'::jsonb,
    fts         TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Approximate-NN index for cosine similarity (HNSW: best default below ~1M rows).
CREATE INDEX IF NOT EXISTS idx_kb_embedding ON kb_chunks
    USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 200);
CREATE INDEX IF NOT EXISTS idx_kb_fts       ON kb_chunks USING GIN (fts);
CREATE INDEX IF NOT EXISTS idx_kb_doc_type  ON kb_chunks (doc_type);
CREATE INDEX IF NOT EXISTS idx_kb_metadata  ON kb_chunks USING GIN (metadata);

-- ---------------------------------------------------------------------------
-- match_chunks : pure semantic (cosine) search
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION safety_buddy.match_chunks (
    query_embedding      VECTOR(768),
    match_count          INT DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.0
)
RETURNS TABLE (content TEXT, metadata JSONB, similarity FLOAT)
LANGUAGE sql STABLE
SET search_path = safety_buddy, public AS $$
    SELECT c.content, c.metadata,
           1 - (c.embedding <=> query_embedding) AS similarity
    FROM kb_chunks c
    WHERE c.embedding IS NOT NULL
      AND 1 - (c.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- ---------------------------------------------------------------------------
-- hybrid_search : semantic + full-text fused with Reciprocal Rank Fusion.
-- websearch_to_tsquery handles arbitrary user input safely.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION safety_buddy.hybrid_search (
    query_text       TEXT,
    query_embedding  VECTOR(768),
    match_count      INT DEFAULT 20,
    rrf_k            INT DEFAULT 60,
    full_text_weight FLOAT DEFAULT 1.0,
    semantic_weight  FLOAT DEFAULT 1.0
)
RETURNS TABLE (content TEXT, metadata JSONB, score FLOAT, similarity FLOAT)
LANGUAGE sql STABLE
SET search_path = safety_buddy, public AS $$
WITH semantic AS (
    SELECT c.id,
           ROW_NUMBER() OVER (ORDER BY c.embedding <=> query_embedding) AS rank,
           1 - (c.embedding <=> query_embedding) AS similarity
    FROM kb_chunks c
    WHERE c.embedding IS NOT NULL
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count * 2
),
keyword AS (
    SELECT c.id,
           ROW_NUMBER() OVER (
               ORDER BY ts_rank_cd(c.fts, websearch_to_tsquery('english', query_text)) DESC
           ) AS rank
    FROM kb_chunks c
    WHERE c.fts @@ websearch_to_tsquery('english', query_text)
    LIMIT match_count * 2
),
fused AS (
    SELECT COALESCE(s.id, k.id) AS id,
           COALESCE(semantic_weight  / (rrf_k + s.rank), 0.0) +
           COALESCE(full_text_weight / (rrf_k + k.rank), 0.0) AS score,
           COALESCE(s.similarity, 0.0) AS similarity
    FROM semantic s
    FULL OUTER JOIN keyword k ON s.id = k.id
)
SELECT c.content, c.metadata, f.score, f.similarity
FROM fused f
JOIN kb_chunks c ON c.id = f.id
ORDER BY f.score DESC
LIMIT match_count;
$$;

-- ---------------------------------------------------------------------------
-- kb_stats : lightweight counts for status/health endpoints
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION safety_buddy.kb_stats ()
RETURNS TABLE (chunks BIGINT, doc_types BIGINT, last_ingest TIMESTAMPTZ)
LANGUAGE sql STABLE
SET search_path = safety_buddy, public AS $$
    SELECT (SELECT count(*) FROM kb_chunks),
           (SELECT count(DISTINCT doc_type) FROM kb_chunks),
           (SELECT max(created_at) FROM kb_chunks);
$$;

-- ===========================================================================
-- Runtime analytics + alerts + feedback (replace the old in-memory store)
-- ===========================================================================

-- events : usage analytics; also powers the dashboard counters.
-- kind = 'chat' | 'image' | 'video' | 'live_frame'. For 'video' the processed
-- frame count is kept in metadata->>'frames' (per-frame rows would be too chatty).
CREATE TABLE IF NOT EXISTS events (
    id          BIGSERIAL PRIMARY KEY,
    kind        TEXT NOT NULL,
    mode        TEXT,                 -- chat mode: advisor/incident/compliance/video_alert
    query       TEXT,
    tokens      INT,
    metadata    JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_events_kind    ON events (kind);
CREATE INDEX IF NOT EXISTS idx_events_created ON events (created_at);

-- alerts : PPE violations surfaced to the dashboard feed.
CREATE TABLE IF NOT EXISTS alerts (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT,                 -- 'live' | 'video' | 'image'
    severity    TEXT,                 -- 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
    summary     TEXT,                 -- comma-joined violation class names
    time_label  TEXT,                 -- '12.5s' (video) or 'HH:MM:SS' (live)
    metadata    JSONB DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_alerts_created ON alerts (created_at);

-- feedback : thumbs up/down on answers, stored with the full exchange so it is
-- usable as preference data later.
CREATE TABLE IF NOT EXISTS feedback (
    id          BIGSERIAL PRIMARY KEY,
    message_id  TEXT,
    rating      SMALLINT,             -- 1 = up, -1 = down
    comment     TEXT,
    query       TEXT,
    answer      TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);
