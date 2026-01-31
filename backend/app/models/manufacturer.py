"""
Manufacturer model for storing manufacturer research results
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum, JSON, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from ..core.database import Base


class ResearchStatus(str, enum.Enum):
    """Research status enumeration"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NOT_FOUND = "not_found"


class VerificationStatus(str, enum.Enum):
    """Verification status enumeration"""
    NOT_VERIFIED = "not_verified"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"


class Manufacturer(Base):
    """Manufacturer research results model"""
    __tablename__ = "manufacturers"
    
    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    clin_id = Column(Integer, ForeignKey("clins.id", ondelete="CASCADE"), nullable=True, index=True)
    
    # Manufacturer identification (extracted from CLIN)
    name = Column(String(255), nullable=False, index=True)
    cage_code = Column(String(20), nullable=True, index=True)  # CAGE code from contract
    part_number = Column(String(255), nullable=True)  # Associated part number
    nsn = Column(String(50), nullable=True)  # National Stock Number if available
    
    # Research results
    website = Column(String(512), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    company_info = Column(JSON, nullable=True)  # Additional company information
    
    # Verification results
    sam_gov_status = Column(String(50), nullable=True)  # "Active", "Inactive", etc.
    sam_gov_verified = Column(Boolean, default=False, nullable=False)
    sam_gov_verification_date = Column(DateTime(timezone=True), nullable=True)
    website_verified = Column(Boolean, default=False, nullable=False)
    website_verification_date = Column(DateTime(timezone=True), nullable=True)
    verification_status = Column(Enum(VerificationStatus), default=VerificationStatus.NOT_VERIFIED, nullable=False)
    verification_notes = Column(Text, nullable=True)
    
    # Research metadata
    research_status = Column(Enum(ResearchStatus), default=ResearchStatus.PENDING, nullable=False)
    research_started_at = Column(DateTime(timezone=True), nullable=True)
    research_completed_at = Column(DateTime(timezone=True), nullable=True)
    research_error = Column(Text, nullable=True)
    research_source = Column(String(100), nullable=True)  # "contract", "web_search", etc.
    
    # Additional data
    additional_data = Column(JSON, nullable=True)  # Store any extra research data
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    opportunity = relationship("Opportunity", back_populates="manufacturers")
    clin = relationship("CLIN", back_populates="manufacturers")
    dealers = relationship("Dealer", back_populates="manufacturer", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Manufacturer(id={self.id}, name={self.name}, status={self.research_status})>"
