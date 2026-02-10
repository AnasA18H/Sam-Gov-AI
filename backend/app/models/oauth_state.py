"""Temporary OAuth state for connect-email flow (state -> user_id)."""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from ..core.database import Base


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id = Column(Integer, primary_key=True, index=True)
    state = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    provider = Column(String(20), nullable=False)  # 'google' | 'microsoft'
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
