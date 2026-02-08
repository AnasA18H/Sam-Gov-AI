"""
Opportunity schemas
"""
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, List
from datetime import datetime
from ..models.opportunity import SolicitationType


class OpportunityCreate(BaseModel):
    """Create opportunity schema"""
    sam_gov_url: HttpUrl = Field(..., description="SAM.gov opportunity URL")
    additional_documents: Optional[List[str]] = Field(default=None, description="Optional uploaded document IDs")


class OpportunityResponse(BaseModel):
    """Opportunity response schema"""
    id: int
    sam_gov_url: str
    sam_gov_id: Optional[str]
    notice_id: Optional[str]
    title: Optional[str]
    description: Optional[str]
    agency: Optional[str]
    solicitation_type: SolicitationType
    classification_confidence: Optional[str]
    status: str
    error_message: Optional[str]
    primary_contact: Optional[dict] = None  # {name, email, phone}
    alternative_contact: Optional[dict] = None  # {name, email, phone}
    contracting_office_address: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class OpportunityDetailResponse(OpportunityResponse):
    """Extended opportunity response with relationships"""
    documents: List["DocumentResponse"] = []
    deadlines: List["DeadlineResponse"] = []
    clins: List["CLINResponse"] = []
    
    class Config:
        from_attributes = True


class OpportunityList(BaseModel):
    """List of opportunities"""
    opportunities: List[OpportunityResponse]
    total: int


# Forward references to avoid circular imports
from ..schemas.document import DocumentResponse
from ..schemas.deadline import DeadlineResponse
from ..schemas.clin import CLINResponse

OpportunityDetailResponse.model_rebuild()
