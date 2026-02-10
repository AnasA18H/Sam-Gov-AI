"""
Stores a user's connected email account (Gmail or Outlook) for sending from the app.
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from ..core.database import Base


class UserEmailConnection(Base):
    """OAuth tokens for sending email as the user (Gmail or Microsoft)."""
    __tablename__ = "user_email_connections"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(20), nullable=False)  # 'google' | 'microsoft'
    refresh_token = Column(String(2048), nullable=False)
    access_token = Column(String(2048), nullable=True)
    token_expires_at = Column(DateTime(timezone=True), nullable=True)
    sender_email = Column(String(255), nullable=True)  # user's email for this provider
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User", backref="email_connections")
