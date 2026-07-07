-- ============================================================================
-- SafetyBuddy — one-time fix for self-hosted Supabase
--
-- On self-hosted Supabase, pgvector is installed in the `extensions` schema, so
-- the `<=>` cosine operator is `extensions.<=>`. The search functions were
-- created with `search_path = safety_buddy, public`, which excludes extensions,
-- so hybrid_search / match_chunks failed with:
--     operator does not exist: extensions.vector <=> extensions.vector
--
-- This re-declares the two vector functions with `extensions` on the search_path.
-- Run once in the Supabase SQL editor (Studio). Safe to re-run (idempotent).
-- No data is touched — only function definitions.
-- ============================================================================

CREATE OR REPLACE FUNCTION safety_buddy.match_chunks (
    query_embedding      VECTOR(768),
    match_count          INT DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.0
)
RETURNS TABLE (content TEXT, metadata JSONB, similarity FLOAT)
LANGUAGE sql STABLE
SET search_path = safety_buddy, public, extensions AS $$
    SELECT c.content, c.metadata,
           1 - (c.embedding <=> query_embedding) AS similarity
    FROM kb_chunks c
    WHERE c.embedding IS NOT NULL
      AND 1 - (c.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
$$;

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
SET search_path = safety_buddy, public, extensions AS $$
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
