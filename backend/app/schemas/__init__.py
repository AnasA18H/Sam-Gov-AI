"""
Pydantic schemas for request/response validation
"""
from .auth import UserRegister, UserLogin, Token, TokenData, UserResponse
from .opportunity import OpportunityCreate, OpportunityResponse, OpportunityList
from .clin import CLINCreate, CLINResponse
from .document import DocumentCreate, DocumentResponse
from .deadline import DeadlineCreate, DeadlineResponse

__all__ = [
    "UserRegister",
    "UserLogin",
    "Token",
    "TokenData",
    "UserResponse",
    "OpportunityCreate",
    "OpportunityResponse",
    "OpportunityList",
    "CLINCreate",
    "CLINResponse",
    "DocumentCreate",
    "DocumentResponse",
    "DeadlineCreate",
    "DeadlineResponse",
]
