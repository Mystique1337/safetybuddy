#!/usr/bin/env bash
# Apply the SafetyBuddy schema (supabase/schema.sql) to your self-hosted
# Supabase / Postgres. All objects are created in the SUPABASE_DB_SCHEMA schema
# (default: safety_buddy), so they never collide with other apps on the
# same instance.
#
# The app itself talks to Supabase over REST (no raw Postgres port needed), but
# the schema is DDL and must be applied with database access. Two options:
#   1. Supabase Studio -> SQL editor: paste supabase/schema.sql and run it, then
#      supabase/fix_pgvector_search_path.sql (self-hosted pgvector fix).
#   2. If you have direct psql access, set DB_URL below and run this script:
#         DB_URL=postgresql://... bash scripts/setup_supabase.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

# Accept DB_URL (or a legacy SUPABASE_DB_URL) for the direct-psql path.
DB_URL="${DB_URL:-${SUPABASE_DB_URL:-}}"

if [[ -z "$DB_URL" ]]; then
  echo "No DB_URL set. Your Supabase exposes only REST, so apply the schema in" >&2
  echo "Supabase Studio -> SQL editor instead:" >&2
  echo "  1. Paste + run supabase/schema.sql" >&2
  echo "  2. Paste + run supabase/fix_pgvector_search_path.sql" >&2
  echo "Or, with direct psql access:  DB_URL=postgresql://... bash $0" >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql not found. Install the Postgres client, or paste supabase/schema.sql" >&2
  echo "and supabase/fix_pgvector_search_path.sql into the Supabase SQL editor." >&2
  exit 1
fi

echo "Applying supabase/schema.sql to schema '${SUPABASE_DB_SCHEMA:-safety_buddy}'..."
psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$ROOT/supabase/schema.sql"
psql "$DB_URL" -v ON_ERROR_STOP=1 -f "$ROOT/supabase/fix_pgvector_search_path.sql"
echo "Done. Now seed the knowledge base with:  python ingest.py"
