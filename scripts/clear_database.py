#!/usr/bin/env python3
"""
Clear all application data from the database.
Schema and migrations are preserved; only table data is removed.
"""
import os
import sys

# Add backend to path so we can import app config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import text
from app.core.database import engine
from app.core.config import settings


def main():
    force = "--force" in sys.argv or "-f" in sys.argv
    print(f"Using database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else 'default'}")
    if not force:
        confirm = input("This will DELETE ALL data (users, opportunities, documents, deadlines, CLINs, sessions, etc.). Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            return 1

    tables = [
        "oauth_states",
        "sessions",
        "user_email_connections",
        "clins",
        "deadlines",
        "documents",
        "opportunities",
        "users",
    ]
    with engine.connect() as conn:
        conn.execute(
            text("TRUNCATE TABLE " + ", ".join(f'"{t}"' for t in tables) + " RESTART IDENTITY CASCADE;")
        )
        conn.commit()
    print("  Truncated:", ", ".join(tables))

    print("Database cleared.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
