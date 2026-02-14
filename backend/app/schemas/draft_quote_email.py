"""Schemas for draft quote emails (persisted per opportunity)."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class DraftQuoteEmailResponse(BaseModel):
    id: int
    opportunity_id: int
    to: str
    to_name: Optional[str]
    subject: str
    body: str
    contact_type: str
    clin_id: Optional[int]
    clin_number: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class DraftQuoteEmailList(BaseModel):
    drafts: list[DraftQuoteEmailResponse]
