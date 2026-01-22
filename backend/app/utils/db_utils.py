"""
Database utility functions for clearing and viewing database content
"""
import json
from typing import Dict, List, Any
from sqlalchemy.orm import Session
from sqlalchemy import inspect
from ..core.database import SessionLocal, engine
from ..models.user import User
from ..models.opportunity import Opportunity
from ..models.clin import CLIN
from ..models.document import Document
from ..models.deadline import Deadline
from ..models.session import Session as SessionModel


def get_all_table_data(db: Session) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get all data from all tables in the database
    
    Returns:
        Dictionary with table names as keys and lists of records as values
    """
    tables_data = {}
    
    # Get all models
    models = {
        'users': User,
        'opportunities': Opportunity,
        'clins': CLIN,
        'documents': Document,
        'deadlines': Deadline,
        'sessions': SessionModel
    }
    
    for table_name, model in models.items():
        try:
            records = db.query(model).all()
            tables_data[table_name] = []
            
            for record in records:
                # Convert SQLAlchemy object to dictionary
                record_dict = {}
                for column in inspect(model).columns:
                    value = getattr(record, column.name)
                    # Handle datetime and other non-serializable types
                    if hasattr(value, 'isoformat'):
                        value = value.isoformat()
                    elif hasattr(value, '__dict__'):
                        value = str(value)
                    record_dict[column.name] = value
                tables_data[table_name].append(record_dict)
        except Exception as e:
            tables_data[table_name] = {'error': str(e)}
    
    return tables_data


def display_all_database_content(db: Session = None) -> str:
    """
    Display all database content in a formatted string
    
    Args:
        db: Database session (optional, will create one if not provided)
    
    Returns:
        Formatted string with all database content
    """
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        tables_data = get_all_table_data(db)
        
        output = []
        output.append("=" * 80)
        output.append("DATABASE CONTENT SUMMARY")
        output.append("=" * 80)
        output.append("")
        
        total_records = 0
        for table_name, records in tables_data.items():
            if isinstance(records, dict) and 'error' in records:
                output.append(f"❌ {table_name.upper()}: Error - {records['error']}")
            else:
                count = len(records)
                total_records += count
                output.append(f"📊 {table_name.upper()}: {count} record(s)")
        
        output.append("")
        output.append(f"Total Records: {total_records}")
        output.append("")
        output.append("=" * 80)
        output.append("DETAILED CONTENT")
        output.append("=" * 80)
        output.append("")
        
        for table_name, records in tables_data.items():
            if isinstance(records, dict) and 'error' in records:
                continue
                
            output.append(f"\n{'=' * 80}")
            output.append(f"TABLE: {table_name.upper()} ({len(records)} records)")
            output.append(f"{'=' * 80}")
            
            if not records:
                output.append("  (No records)")
            else:
                for idx, record in enumerate(records, 1):
                    output.append(f"\n  Record #{idx}:")
                    for key, value in record.items():
                        # Truncate long values
                        if isinstance(value, str) and len(value) > 100:
                            value = value[:100] + "..."
                        output.append(f"    {key}: {value}")
        
        output.append("\n" + "=" * 80)
        
        return "\n".join(output)
    
    finally:
        if should_close:
            db.close()


def clear_database(db: Session = None, confirm: bool = False) -> Dict[str, Any]:
    """
    Clear all data from all tables in the database
    
    Args:
        db: Database session (optional, will create one if not provided)
        confirm: Must be True to actually clear the database (safety check)
    
    Returns:
        Dictionary with operation status and counts of deleted records
    """
    if not confirm:
        return {
            "status": "error",
            "message": "Database clear operation requires confirm=True for safety"
        }
    
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        deletion_counts = {}
        
        # Delete in reverse order of dependencies (children first, then parents)
        # This respects foreign key constraints
        
        # Delete CLINs
        clin_count = db.query(CLIN).count()
        db.query(CLIN).delete()
        deletion_counts['clins'] = clin_count
        
        # Delete Documents
        doc_count = db.query(Document).count()
        db.query(Document).delete()
        deletion_counts['documents'] = doc_count
        
        # Delete Deadlines
        deadline_count = db.query(Deadline).count()
        db.query(Deadline).delete()
        deletion_counts['deadlines'] = deadline_count
        
        # Delete Opportunities
        opp_count = db.query(Opportunity).count()
        db.query(Opportunity).delete()
        deletion_counts['opportunities'] = opp_count
        
        # Delete Sessions
        session_count = db.query(SessionModel).count()
        db.query(SessionModel).delete()
        deletion_counts['sessions'] = session_count
        
        # Delete Users (last, as they might be referenced)
        user_count = db.query(User).count()
        db.query(User).delete()
        deletion_counts['users'] = user_count
        
        db.commit()
        
        total_deleted = sum(deletion_counts.values())
        
        return {
            "status": "success",
            "message": f"Database cleared successfully. Deleted {total_deleted} total records.",
            "deletion_counts": deletion_counts,
            "total_deleted": total_deleted
        }
    
    except Exception as e:
        db.rollback()
        return {
            "status": "error",
            "message": f"Error clearing database: {str(e)}"
        }
    
    finally:
        if should_close:
            db.close()


def export_database_to_json(db: Session = None, file_path: str = None) -> Dict[str, Any]:
    """
    Export all database content to JSON format
    
    Args:
        db: Database session (optional, will create one if not provided)
        file_path: Optional file path to save JSON to
    
    Returns:
        Dictionary with export status and data
    """
    if db is None:
        db = SessionLocal()
        should_close = True
    else:
        should_close = False
    
    try:
        tables_data = get_all_table_data(db)
        
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(tables_data, f, indent=2, default=str)
        
        return {
            "status": "success",
            "message": f"Database exported successfully" + (f" to {file_path}" if file_path else ""),
            "data": tables_data,
            "file_path": file_path
        }
    
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error exporting database: {str(e)}"
        }
    
    finally:
        if should_close:
            db.close()


# CLI functions for direct script execution
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python db_utils.py display    - Display all database content")
        print("  python db_utils.py clear     - Clear all database content (requires confirmation)")
        print("  python db_utils.py export    - Export database to JSON")
        print("  python db_utils.py export <file> - Export database to specific JSON file")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "display":
        print(display_all_database_content())
    
    elif command == "clear":
        print("⚠️  WARNING: This will delete ALL data from the database!")
        response = input("Type 'DELETE ALL' to confirm: ")
        if response == "DELETE ALL":
            result = clear_database(confirm=True)
            print(json.dumps(result, indent=2))
        else:
            print("Operation cancelled.")
    
    elif command == "export":
        file_path = sys.argv[2] if len(sys.argv) > 2 else "database_export.json"
        result = export_database_to_json(file_path=file_path)
        print(json.dumps(result, indent=2))
        if result["status"] == "success":
            print(f"\n✅ Database exported to: {file_path}")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
