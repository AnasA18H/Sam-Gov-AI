"""
Draft quote email – persisted per opportunity. Generate saves these; send/discard delete from DB.
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base


class DraftQuoteEmail(Base):
    __tablename__ = "draft_quote_emails"

    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)

    to = Column(String(255), nullable=False)
    to_name = Column(String(255), nullable=True)
    subject = Column(String(500), nullable=False)
    body = Column(Text, nullable=False)
    contact_type = Column(String(20), nullable=False)  # 'manufacturer' | 'dealer'
    clin_id = Column(Integer, ForeignKey("clins.id", ondelete="SET NULL"), nullable=True, index=True)
    clin_number = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    opportunity = relationship("Opportunity", back_populates="draft_quote_emails")
