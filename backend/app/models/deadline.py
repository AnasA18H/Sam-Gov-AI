"""
Deadline model for submission due dates
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base


class Deadline(Base):
    """Deadline model for submission due dates"""
    __tablename__ = "deadlines"
    
    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Deadline information
    due_date = Column(DateTime(timezone=True), nullable=False)
    due_time = Column(String(50), nullable=True)  # e.g., "17:00"
    timezone = Column(String(50), nullable=True)  # e.g., "EST", "CST", "PST", "UTC"
    
    # Deadline details
    deadline_type = Column(String(100), nullable=True)  # e.g., "submission", "questions", "award"
    description = Column(Text, nullable=True)
    location = Column(String(500), nullable=True)  # Submission location if specified
    
    # Status
    is_primary = Column(Boolean, default=False, nullable=False)  # Primary submission deadline
    is_passed = Column(Boolean, default=False, nullable=False)
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    opportunity = relationship("Opportunity", back_populates="deadlines")
    
    def __repr__(self):
        return f"<Deadline(id={self.id}, due_date={self.due_date}, type={self.deadline_type})>"
