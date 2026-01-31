"""
Dealer/Distributor model for storing dealer research results
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum, JSON, Boolean, Numeric
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


class Dealer(Base):
    """Dealer/Distributor research results model"""
    __tablename__ = "dealers"
    
    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    clin_id = Column(Integer, ForeignKey("clins.id", ondelete="CASCADE"), nullable=True, index=True)
    manufacturer_id = Column(Integer, ForeignKey("manufacturers.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Dealer identification
    company_name = Column(String(255), nullable=False, index=True)
    website = Column(String(512), nullable=True)
    contact_email = Column(String(255), nullable=True)
    contact_phone = Column(String(50), nullable=True)
    address = Column(Text, nullable=True)
    company_info = Column(JSON, nullable=True)  # Additional company information
    
    # Product information
    part_number = Column(String(255), nullable=True)  # Part they sell
    nsn = Column(String(50), nullable=True)  # National Stock Number
    product_listed = Column(Boolean, default=False, nullable=False)  # Whether product is listed on their site
    pricing_info = Column(Text, nullable=True)  # Pricing information if found
    pricing_source = Column(String(100), nullable=True)  # Where pricing was found
    pricing_amount = Column(Numeric(12, 2), nullable=True)  # Numeric price if available
    currency = Column(String(10), default="USD", nullable=False)
    stock_status = Column(String(50), nullable=True)  # "in_stock", "out_of_stock", "unknown"
    
    # Verification results
    sam_gov_status = Column(String(50), nullable=True)  # "Active", "Inactive", etc.
    sam_gov_verified = Column(Boolean, default=False, nullable=False)
    sam_gov_verification_date = Column(DateTime(timezone=True), nullable=True)
    website_verified = Column(Boolean, default=False, nullable=False)
    website_verification_date = Column(DateTime(timezone=True), nullable=True)
    manufacturer_authorized = Column(Boolean, nullable=True)  # Whether authorized by manufacturer
    verification_status = Column(Enum(VerificationStatus), default=VerificationStatus.NOT_VERIFIED, nullable=False)
    verification_notes = Column(Text, nullable=True)
    
    # Research metadata
    research_status = Column(Enum(ResearchStatus), default=ResearchStatus.PENDING, nullable=False)
    research_started_at = Column(DateTime(timezone=True), nullable=True)
    research_completed_at = Column(DateTime(timezone=True), nullable=True)
    research_error = Column(Text, nullable=True)
    research_source = Column(String(100), nullable=True)  # "google", "manufacturer_website", "dla", "asap_nsn_hub", etc.
    search_query = Column(String(500), nullable=True)  # The search query used to find this dealer
    rank_score = Column(Integer, nullable=True)  # Ranking/relevance score (1-10, higher is better)
    
    # Additional data
    additional_data = Column(JSON, nullable=True)  # Store any extra research data
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    opportunity = relationship("Opportunity", back_populates="dealers")
    clin = relationship("CLIN", back_populates="dealers")
    manufacturer = relationship("Manufacturer", back_populates="dealers")
    
    def __repr__(self):
        return f"<Dealer(id={self.id}, company_name={self.company_name}, status={self.research_status})>"
