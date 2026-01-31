"""
Dealer schemas
"""
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal


class DealerResponse(BaseModel):
    """Dealer response schema"""
    id: int
    opportunity_id: int
    clin_id: Optional[int] = None
    manufacturer_id: Optional[int] = None
    
    # Dealer identification
    company_name: str
    website: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    company_info: Optional[Dict[str, Any]] = None
    
    # Product information
    part_number: Optional[str] = None
    nsn: Optional[str] = None
    product_listed: bool = False
    pricing_info: Optional[str] = None
    pricing_source: Optional[str] = None
    pricing_amount: Optional[Decimal] = None
    currency: str = "USD"
    stock_status: Optional[str] = None
    
    # Verification results
    sam_gov_status: Optional[str] = None
    sam_gov_verified: bool = False
    sam_gov_verification_date: Optional[datetime] = None
    website_verified: bool = False
    website_verification_date: Optional[datetime] = None
    manufacturer_authorized: Optional[bool] = None
    verification_status: str = "not_verified"
    verification_notes: Optional[str] = None
    
    # Research metadata
    research_status: str = "pending"  # Will be serialized as enum value (e.g., "pending", "completed")
    research_started_at: Optional[datetime] = None
    research_completed_at: Optional[datetime] = None
    research_error: Optional[str] = None
    research_source: Optional[str] = None
    search_query: Optional[str] = None
    rank_score: Optional[int] = None
    
    # Additional data
    additional_data: Optional[Dict[str, Any]] = None
    
    # Metadata
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
