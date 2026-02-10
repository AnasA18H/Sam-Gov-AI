"""
User model for authentication
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum
from ..core.database import Base


class UserRole(str, enum.Enum):
    """User role enumeration"""
    MEMBER = "member"
    ADMIN = "admin"


class AuthProvider(str, enum.Enum):
    """How the user signed up / signs in. One account per (email, auth_provider)."""
    EMAIL = "email"
    GOOGLE = "google"
    MICROSOFT = "microsoft"


class User(Base):
    """User model for member accounts. Identity is (email, auth_provider)."""
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", "auth_provider", name="uq_users_email_auth_provider"),)

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), index=True, nullable=False)
    auth_provider = Column(String(20), nullable=False, default=AuthProvider.EMAIL.value, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(Enum(UserRole), default=UserRole.MEMBER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_code = Column(String(10), nullable=True)
    verification_code_expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    sessions = relationship("Session", back_populates="user", cascade="all, delete-orphan")
    opportunities = relationship("Opportunity", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email={self.email}, auth_provider={self.auth_provider}, role={self.role})>"
