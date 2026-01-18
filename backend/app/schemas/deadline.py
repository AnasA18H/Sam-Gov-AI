"""
Deadline schemas
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DeadlineCreate(BaseModel):
    """Create deadline schema"""
    due_date: datetime
    due_time: Optional[str] = None
    timezone: Optional[str] = None
    deadline_type: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    is_primary: bool = False


class DeadlineResponse(BaseModel):
    """Deadline response schema"""
    id: int
    due_date: datetime
    due_time: Optional[str]
    timezone: Optional[str]
    deadline_type: Optional[str]
    description: Optional[str]
    location: Optional[str]
    is_primary: bool
    is_passed: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
