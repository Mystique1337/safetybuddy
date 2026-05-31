#!/usr/bin/env bash
# Create/update the Modal secret bundle "safetybuddy-secrets" from your local .env.
# Uses Modal's own dotenv parser (--from-dotenv), which is robust to passwords /
# connection strings containing shell-special characters.
# Run from the repo root after filling in .env:  bash scripts/setup_modal_secret.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "No .env found at $ENV_FILE — copy .env.example to .env and fill it in." >&2
  exit 1
fi

echo "Creating/updating Modal secret 'safetybuddy-secrets' from .env…"
modal secret create safetybuddy-secrets --from-dotenv "$ENV_FILE" --force
echo "Done. Now: modal deploy modal_app.py"
