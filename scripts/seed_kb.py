#!/usr/bin/env python
"""Seed the SafetyBuddy knowledge base with curated authoritative PPE sources.

Run once after applying the schema:
    bash scripts/setup_supabase.sh   # create the safety_buddy schema
    python scripts/seed_kb.py        # fetch + ingest the seed sources

After this, the self-improving retriever keeps the knowledge base growing as the
app is used (and via live web search if TAVILY_API_KEY is set).
"""
import os
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from src.config import settings
from src.rag.sources import SEED_SOURCES
from src.rag.web_ingest import ingest_urls


def main():
    if not settings.db_enabled:
        print("Supabase REST credentials are not set. Fill in .env (SUPABASE_URL + "
              "SUPABASE_SERVICE_ROLE_KEY) first.")
        return
    print(f"Seeding {len(SEED_SOURCES)} authoritative sources into schema "
          f"'{settings.supabase_db_schema}'...")
    summary = ingest_urls(SEED_SOURCES)
    print(f"\nDone: added={summary['added']} skipped={summary['skipped']} failed={summary['failed']}")


if __name__ == "__main__":
    main()
