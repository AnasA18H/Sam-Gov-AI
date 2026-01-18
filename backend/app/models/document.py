"""
Document model for uploaded/downloaded solicitation documents
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum, BigInteger
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from ..core.database import Base


class DocumentType(str, enum.Enum):
    """Document type enumeration"""
    PDF = "pdf"
    WORD = "word"
    EXCEL = "excel"
    OTHER = "other"


class DocumentSource(str, enum.Enum):
    """Document source enumeration"""
    SAM_GOV = "sam_gov"
    USER_UPLOAD = "user_upload"


class Document(Base):
    """Document model for solicitation attachments"""
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Document identification
    file_name = Column(String(500), nullable=False)
    original_file_name = Column(String(500), nullable=True)
    file_path = Column(String(1000), nullable=False)  # Local path or S3 key
    file_url = Column(String(1000), nullable=True)  # Public URL if stored in S3
    file_size = Column(BigInteger, nullable=True)  # Size in bytes
    file_type = Column(Enum(DocumentType), nullable=False)
    mime_type = Column(String(100), nullable=True)
    
    # Source
    source = Column(Enum(DocumentSource), nullable=False)
    source_url = Column(String(1000), nullable=True)  # Original URL if from SAM.gov
    
    # Storage
    storage_type = Column(String(50), default="local", nullable=False)  # local or s3
    
    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    # Relationships
    opportunity = relationship("Opportunity", back_populates="documents")
    
    def __repr__(self):
        return f"<Document(id={self.id}, file_name={self.file_name}, type={self.file_type})>"
