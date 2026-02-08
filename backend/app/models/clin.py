"""
CLIN (Contract Line Item Number) model
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, Numeric, DateTime, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base


class CLIN(Base):
    """Contract Line Item Number model"""
    __tablename__ = "clins"
    
    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # CLIN identification
    clin_number = Column(String(50), nullable=False)  # e.g., "0001", "CLIN 1"
    clin_name = Column(String(500), nullable=True)
    base_item_number = Column(String(50), nullable=True)  # e.g., "S01", supplementary reference code
    
    # Product details
    product_name = Column(String(500), nullable=True)
    product_description = Column(Text, nullable=True)
    manufacturer_name = Column(String(255), nullable=True)
    part_number = Column(String(255), nullable=True)
    model_number = Column(String(255), nullable=True)
    quantity = Column(Numeric(10, 2), nullable=True)
    unit_of_measure = Column(String(50), nullable=True)  # e.g., "each", "lot"
    contract_type = Column(String(100), nullable=True)  # e.g., "Firm Fixed Price", "Cost Plus"
    extended_price = Column(Numeric(12, 2), nullable=True)  # Extended price (quantity * unit price)
    
    # Service details
    service_description = Column(Text, nullable=True)
    scope_of_work = Column(Text, nullable=True)
    timeline = Column(String(255), nullable=True)
    service_requirements = Column(Text, nullable=True)
    
    # Additional data
    additional_data = Column(JSON, nullable=True)  # Store any extra extracted data
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    opportunity = relationship("Opportunity", back_populates="clins")
    
    def __repr__(self):
        return f"<CLIN(id={self.id}, clin_number={self.clin_number}, product={self.product_name})>"
