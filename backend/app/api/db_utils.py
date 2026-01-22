"""
API endpoints for database utility functions
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from ..core.dependencies import get_db
from ..utils.db_utils import (
    display_all_database_content,
    clear_database,
    export_database_to_json,
    get_all_table_data
)

router = APIRouter(prefix="/api/v1/utils", tags=["database-utils"])


@router.get("/db/display")
def display_database(
    format: str = Query(default="text", pattern="^(text|json)$"),
    db: Session = Depends(get_db)
):
    """
    Display all database content
    
    - **format**: Output format - 'text' for formatted text, 'json' for JSON
    """
    try:
        if format == "json":
            tables_data = get_all_table_data(db)
            return {
                "status": "success",
                "data": tables_data
            }
        else:
            content = display_all_database_content(db)
            return {
                "status": "success",
                "content": content
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error displaying database: {str(e)}")


@router.post("/db/clear")
def clear_database_endpoint(
    confirm: bool = Query(..., description="Must be True to clear database"),
    db: Session = Depends(get_db)
):
    """
    Clear all data from the database
    
    ⚠️ **WARNING**: This will delete ALL data from the database!
    
    - **confirm**: Must be set to True to proceed
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Database clear operation requires confirm=true for safety"
        )
    
    try:
        result = clear_database(db=db, confirm=True)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing database: {str(e)}")


@router.get("/db/export")
def export_database(
    db: Session = Depends(get_db)
):
    """
    Export all database content as JSON
    """
    try:
        result = export_database_to_json(db=db)
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting database: {str(e)}")


@router.get("/db/stats")
def get_database_stats(
    db: Session = Depends(get_db)
):
    """
    Get database statistics (record counts per table)
    """
    try:
        from ..models.user import User
        from ..models.opportunity import Opportunity
        from ..models.clin import CLIN
        from ..models.document import Document
        from ..models.deadline import Deadline
        from ..models.session import Session as SessionModel
        
        stats = {
            "users": db.query(User).count(),
            "opportunities": db.query(Opportunity).count(),
            "clins": db.query(CLIN).count(),
            "documents": db.query(Document).count(),
            "deadlines": db.query(Deadline).count(),
            "sessions": db.query(SessionModel).count(),
        }
        
        stats["total"] = sum(stats.values())
        
        return {
            "status": "success",
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting database stats: {str(e)}")
