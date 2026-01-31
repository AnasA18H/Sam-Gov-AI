"""
Opportunity model for SAM.gov solicitations
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from ..core.database import Base


class SolicitationType(str, enum.Enum):
    """Solicitation type classification"""
    PRODUCT = "product"
    SERVICE = "service"
    BOTH = "both"
    UNKNOWN = "unknown"


class Opportunity(Base):
    """SAM.gov opportunity/solicitation model"""
    __tablename__ = "opportunities"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # SAM.gov data
    sam_gov_url = Column(String(512), unique=True, index=True, nullable=False)
    sam_gov_id = Column(String(100), unique=True, index=True, nullable=True)  # Opportunity ID from URL
    notice_id = Column(String(100), unique=True, index=True, nullable=True)  # Notice ID from SAM.gov page
    title = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)  # Full description text
    agency = Column(String(255), nullable=True)
    classification_codes = Column(JSON, nullable=True)  # Store NAICS codes, etc.
    
    # Contact Information
    primary_contact = Column(JSON, nullable=True)  # {name, email, phone}
    alternative_contact = Column(JSON, nullable=True)  # {name, email, phone}
    contracting_office_address = Column(Text, nullable=True)  # Full address as text
    
    # Classification
    solicitation_type = Column(Enum(SolicitationType), default=SolicitationType.UNKNOWN, nullable=False)
    classification_confidence = Column(String(10), nullable=True)  # e.g., "0.92"
    
    # Status
    status = Column(String(50), default="pending", nullable=False)  # pending, processing, completed, failed
    error_message = Column(Text, nullable=True)
    
    # Analysis flags
    enable_document_analysis = Column(String(10), default="false", nullable=False)  # "true" or "false" as string
    enable_clin_extraction = Column(String(10), default="false", nullable=False)  # "true" or "false" as string
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="opportunities")
    clins = relationship("CLIN", back_populates="opportunity", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="opportunity", cascade="all, delete-orphan")
    deadlines = relationship("Deadline", back_populates="opportunity", cascade="all, delete-orphan")
    manufacturers = relationship("Manufacturer", back_populates="opportunity", cascade="all, delete-orphan")
    dealers = relationship("Dealer", back_populates="opportunity", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Opportunity(id={self.id}, sam_gov_id={self.sam_gov_id}, type={self.solicitation_type})>"
