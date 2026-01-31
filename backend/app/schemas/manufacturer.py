"""
Manufacturer schemas
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime


class ManufacturerResponse(BaseModel):
    """Manufacturer response schema"""
    id: int
    opportunity_id: int
    clin_id: Optional[int] = None
    
    # Manufacturer identification
    name: str
    cage_code: Optional[str] = None
    part_number: Optional[str] = None
    nsn: Optional[str] = None
    
    # Research results
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    company_info: Optional[Dict[str, Any]] = None
    
    # Verification results
    sam_gov_status: Optional[str] = None
    sam_gov_verified: bool = False
    sam_gov_verification_date: Optional[datetime] = None
    website_verified: bool = False
    website_verification_date: Optional[datetime] = None
    verification_status: str = "not_verified"
    verification_notes: Optional[str] = None
    
    # Research metadata
    research_status: str = "pending"  # Will be serialized as enum value (e.g., "pending", "completed")
    research_started_at: Optional[datetime] = None
    research_completed_at: Optional[datetime] = None
    research_error: Optional[str] = None
    research_source: Optional[str] = None
    
    # Additional data
    additional_data: Optional[Dict[str, Any]] = None
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
