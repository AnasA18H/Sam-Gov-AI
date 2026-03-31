"""Contractor profile schemas for form-fill persistence."""
from pydantic import BaseModel, field_validator
from typing import Optional, List, Any
from datetime import datetime
import json


class CustomStampItem(BaseModel):
    """Single custom stamp: name + image data URL."""
    name: str
    dataUrl: str


class ContractorProfileUpdate(BaseModel):
    """Schema for creating/updating contractor profile."""
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    uei: Optional[str] = None
    cage: Optional[str] = None
    tin: Optional[str] = None
    contract_officer_name: Optional[str] = None
    digital_signature: Optional[str] = None  # Base64 data URL or path
    digital_signature_2: Optional[str] = None
    digital_signature_3: Optional[str] = None
    custom_stamps: Optional[List[CustomStampItem]] = None  # Digital stamps workbench (name + dataUrl each)
    email: Optional[str] = None
    phone: Optional[str] = None


class ContractorProfileResponse(BaseModel):
    """Schema for contractor profile response."""
    id: int
    user_id: int
    company_name: Optional[str] = None
    company_address: Optional[str] = None
    uei: Optional[str] = None
    cage: Optional[str] = None
    tin: Optional[str] = None
    contract_officer_name: Optional[str] = None
    digital_signature: Optional[str] = None
    digital_signature_2: Optional[str] = None
    digital_signature_3: Optional[str] = None
    custom_stamps: Optional[List[CustomStampItem]] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("custom_stamps", mode="before")
    @classmethod
    def parse_custom_stamps(cls, v: Any) -> Optional[List[CustomStampItem]]:
        if v is None:
            return None
        if isinstance(v, list):
            return [CustomStampItem.model_validate(x) for x in v]
        if isinstance(v, str):
            try:
                data = json.loads(v)
                return [CustomStampItem.model_validate(x) for x in data] if data else []
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    class Config:
        from_attributes = True
