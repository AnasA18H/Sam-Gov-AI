#!/usr/bin/env python3
"""
Clear all data from the database and optionally verify schema/connection.

Usage:
  python scripts/reset_database.py              # Clear data (prompt for confirmation)
  python scripts/reset_database.py --force      # Clear data without confirmation
  python scripts/reset_database.py --check      # Only check DB connection and current schema (no clear)
  python scripts/reset_database.py --recreate   # Downgrade to base then upgrade head (drops all tables, recreates)

Requires DATABASE_URL (or default postgres) to be set. Run from project root.
"""
import os
import sys
import subprocess

# Project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, "backend"))

def main():
    force = "--force" in sys.argv
    check_only = "--check" in sys.argv
    recreate = "--recreate" in sys.argv

    os.chdir(project_root)

    # Use same config as app
    from backend.app.core.config import settings
    url = settings.DATABASE_URL
    # Mask password in logs
    if "@" in url and ":" in url:
        try:
            pre, rest = url.split("@", 1)
            if ":" in pre:
                user = pre.split(":")[0] + ":****"
                masked = user + "@" + rest
            else:
                masked = url
        except Exception:
            masked = "***"
    else:
        masked = url
    print("DATABASE_URL:", masked)

    if check_only:
        print("\n--- Check connection and schema ---")
        try:
            from backend.app.core.database import engine
            from sqlalchemy import text
            with engine.connect() as conn:
                r = conn.execute(text("SELECT 1"))
                r.fetchone()
            print("Connection: OK")
            # Show current revision
            r = subprocess.run(
                [sys.executable, "-m", "alembic", "current"],
                capture_output=True,
                text=True,
                cwd=project_root,
            )
            if r.returncode == 0:
                print("Alembic current:", (r.stdout or r.stderr or "").strip() or "(none)")
            return 0
        except Exception as e:
            print("Connection: FAILED", e)
            return 1

    if recreate:
        print("\n--- Recreate schema (drop public schema + upgrade head) ---")
        print("This will DROP the public schema (all tables, types, data) and recreate from migrations.")
        if not force:
            reply = input("Type 'yes' to continue: ")
            if reply.strip().lower() != "yes":
                print("Aborted.")
                return 0
        # Drop and recreate public schema so ENUMs and all objects are removed (downgrade leaves ENUMs)
        from backend.app.core.database import engine
        from sqlalchemy import text
        from urllib.parse import unquote, urlparse
        parsed = urlparse(url)
        db_user = unquote(parsed.username) if parsed.username else "postgres"
        with engine.connect() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text(f"GRANT ALL ON SCHEMA public TO {db_user}"))
            conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
            conn.commit()
        print("Schema dropped and recreated.")
        r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=project_root, shell=False)
        if r.returncode != 0:
            print("Alembic upgrade failed.")
            return r.returncode
        print("Schema recreated successfully.")
        return 0

    # Clear data
    print("\n--- Clear all database data ---")
    if not force:
        print("This will delete all rows in all tables (users, opportunities, sessions, etc.).")
        reply = input("Type 'DELETE ALL' to confirm: ")
        if reply.strip() != "DELETE ALL":
            print("Aborted.")
            return 0

    from backend.app.core.database import SessionLocal
    from backend.app.utils.db_utils import clear_database

    db = SessionLocal()
    try:
        result = clear_database(db=db, confirm=True)
        print(result.get("message", result))
        if result.get("status") == "success":
            print("Deletion counts:", result.get("deletion_counts", {}))
        else:
            return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
