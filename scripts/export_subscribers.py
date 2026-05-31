#!/usr/bin/env python
"""Export SafetyBuddy subscribers (opt-in product-updates emails) to CSV.

    python scripts/export_subscribers.py [output.csv]

Reads directly from the self-hosted Supabase `subscribers` table in the
safety_buddy schema. Defaults to writing ./subscribers.csv.
"""
import csv
import os
import sys

from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from src.config import settings
from src.db import get_pool


def main():
    if not settings.db_enabled:
        print("SUPABASE_DB_URL is not set; nothing to export.")
        return
    out = sys.argv[1] if len(sys.argv) > 1 else "subscribers.csv"

    from psycopg.rows import dict_row

    pool = get_pool()
    with pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT email, wants_updates, source, created_at "
            "FROM subscribers ORDER BY created_at"
        )
        rows = cur.fetchall()

    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "wants_updates", "source", "created_at"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Exported {len(rows)} subscriber(s) to {out}")


if __name__ == "__main__":
    main()
