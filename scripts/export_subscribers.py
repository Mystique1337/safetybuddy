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
from src.db import select


def main():
    if not settings.db_enabled:
        print("Supabase REST credentials are not set; nothing to export.")
        return
    out = sys.argv[1] if len(sys.argv) > 1 else "subscribers.csv"

    rows = select(
        "subscribers", "email,wants_updates,source,created_at", order="created_at"
    ).json()

    with open(out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "wants_updates", "source", "created_at"])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    print(f"Exported {len(rows)} subscriber(s) to {out}")


if __name__ == "__main__":
    main()
