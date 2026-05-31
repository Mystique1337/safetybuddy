#!/usr/bin/env bash
# Apply the SafetyBuddy schema (supabase/schema.sql) to your self-hosted
# Supabase / Postgres. All objects are created in the SUPABASE_DB_SCHEMA schema
# (default: safety_buddy), so they never collide with other apps on the
# same instance. Run from the repo root after filling in .env:
#     bash scripts/setup_supabase.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a; source "$ENV_FILE"; set +a
fi

if [[ -z "${SUPABASE_DB_URL:-}" ]]; then
  echo "SUPABASE_DB_URL is not set (fill it in $ENV_FILE)." >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql not found. Install the Postgres client, or paste supabase/schema.sql" >&2
  echo "into the Supabase SQL editor instead." >&2
  exit 1
fi

echo "Applying supabase/schema.sql to schema '${SUPABASE_DB_SCHEMA:-safety_buddy}'..."
psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$ROOT/supabase/schema.sql"
echo "Done. Now seed the knowledge base with:  python ingest.py"
