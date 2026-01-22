#!/usr/bin/env python3
"""
CLI script for database utilities
Usage:
    python scripts/db_utils.py display    - Display all database content
    python scripts/db_utils.py clear       - Clear all database content
    python scripts/db_utils.py export     - Export database to JSON
    python scripts/db_utils.py stats      - Show database statistics
"""
import sys
import os
import json

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.utils.db_utils import (
    display_all_database_content,
    clear_database,
    export_database_to_json,
    get_all_table_data
)
from app.core.database import SessionLocal


def main():
    if len(sys.argv) < 2:
        print("Database Utility Script")
        print("=" * 60)
        print("\nUsage:")
        print("  python scripts/db_utils.py display    - Display all database content")
        print("  python scripts/db_utils.py clear     - Clear all database content (requires confirmation)")
        print("  python scripts/db_utils.py export    - Export database to JSON")
        print("  python scripts/db_utils.py export <file> - Export to specific file")
        print("  python scripts/db_utils.py stats     - Show database statistics")
        print("\nExamples:")
        print("  python scripts/db_utils.py display")
        print("  python scripts/db_utils.py clear")
        print("  python scripts/db_utils.py export database_backup.json")
        print("  python scripts/db_utils.py stats")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    db = SessionLocal()
    
    try:
        if command == "display":
            print(display_all_database_content(db))
        
        elif command == "clear":
            print("⚠️  WARNING: This will delete ALL data from the database!")
            print("This includes:")
            print("  - All users (except you might need to recreate admin)")
            print("  - All opportunities")
            print("  - All CLINs")
            print("  - All documents")
            print("  - All deadlines")
            print("  - All sessions")
            print()
            response = input("Type 'DELETE ALL' to confirm: ")
            if response == "DELETE ALL":
                result = clear_database(db=db, confirm=True)
                print("\n" + "=" * 60)
                print(json.dumps(result, indent=2))
                print("=" * 60)
            else:
                print("Operation cancelled.")
        
        elif command == "export":
            file_path = sys.argv[2] if len(sys.argv) > 2 else "database_export.json"
            result = export_database_to_json(db=db, file_path=file_path)
            print(json.dumps(result, indent=2))
            if result["status"] == "success":
                print(f"\n✅ Database exported to: {file_path}")
        
        elif command == "stats":
            from app.models.user import User
            from app.models.opportunity import Opportunity
            from app.models.clin import CLIN
            from app.models.document import Document
            from app.models.deadline import Deadline
            from app.models.session import Session as SessionModel
            
            stats = {
                "users": db.query(User).count(),
                "opportunities": db.query(Opportunity).count(),
                "clins": db.query(CLIN).count(),
                "documents": db.query(Document).count(),
                "deadlines": db.query(Deadline).count(),
                "sessions": db.query(SessionModel).count(),
            }
            
            stats["total"] = sum(stats.values())
            
            print("=" * 60)
            print("DATABASE STATISTICS")
            print("=" * 60)
            for table, count in stats.items():
                print(f"  {table.capitalize()}: {count}")
            print("=" * 60)
        
        else:
            print(f"❌ Unknown command: {command}")
            print("Run without arguments to see usage.")
            sys.exit(1)
    
    except Exception as e:
        print(f"❌ Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    finally:
        db.close()


if __name__ == "__main__":
    main()
