"""
CLIN schemas
"""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal


class CLINCreate(BaseModel):
    """Create CLIN schema"""
    clin_number: str
    clin_name: Optional[str] = None
    product_name: Optional[str] = None
    product_description: Optional[str] = None
    manufacturer_name: Optional[str] = None
    part_number: Optional[str] = None
    model_number: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_of_measure: Optional[str] = None
    service_description: Optional[str] = None
    scope_of_work: Optional[str] = None
    timeline: Optional[str] = None
    service_requirements: Optional[str] = None


class CLINResponse(BaseModel):
    """CLIN response schema"""
    id: int
    clin_number: str
    clin_name: Optional[str]
    product_name: Optional[str]
    product_description: Optional[str]
    manufacturer_name: Optional[str]
    part_number: Optional[str]
    model_number: Optional[str]
    quantity: Optional[Decimal]
    unit_of_measure: Optional[str]
    service_description: Optional[str]
    scope_of_work: Optional[str]
    timeline: Optional[str]
    service_requirements: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True
