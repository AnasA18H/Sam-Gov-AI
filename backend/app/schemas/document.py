"""
Document schemas
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from ..models.document import DocumentType, DocumentSource


class DocumentCreate(BaseModel):
    """Create document schema"""
    file_name: str
    file_path: str
    file_type: DocumentType
    source: DocumentSource
    source_url: Optional[str] = None


class DocumentResponse(BaseModel):
    """Document response schema"""
    id: int
    file_name: str
    original_file_name: Optional[str]
    file_url: Optional[str]
    file_size: Optional[int]
    file_type: DocumentType
    source: DocumentSource
    created_at: datetime
    
    class Config:
        from_attributes = True
