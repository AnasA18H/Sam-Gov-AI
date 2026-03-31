"""
Contractor/offeror profile for form filling (SF 1449 etc.). One per user; persisted for autofill.
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base


class ContractorProfile(Base):
    """Stored company and signer info for the logged-in user; used when autofilling government forms."""
    __tablename__ = "contractor_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)

    company_name = Column(String(500), nullable=True)
    company_address = Column(Text, nullable=True)
    uei = Column(String(50), nullable=True)  # Unique Entity ID
    cage = Column(String(20), nullable=True)  # Commercial and Government Entity code
    tin = Column(String(50), nullable=True)  # Tax Identification Number
    contract_officer_name = Column(String(255), nullable=True)  # Name/title of person signing (offeror)
    digital_signature = Column(Text, nullable=True)  # Optional: base64 image data URL or path for signature image
    digital_signature_2 = Column(Text, nullable=True)  # Second signature (user can have up to 3)
    digital_signature_3 = Column(Text, nullable=True)  # Third signature
    custom_stamps = Column(Text, nullable=True)  # JSON array of {"name": str, "dataUrl": str} for digital stamps (Acrobat-style)
    email = Column(String(255), nullable=True)  # Contact email (if different from user.email)
    phone = Column(String(50), nullable=True)  # Contact phone for forms

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", back_populates="contractor_profile")

    def __repr__(self):
        return f"<ContractorProfile(user_id={self.user_id}, company={self.company_name})>"
