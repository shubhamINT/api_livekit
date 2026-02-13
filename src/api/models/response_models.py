"""
Production-grade API response models for consistent payload structure.

This module defines standardized response schemas that ensure all API endpoints
return uniform, predictable responses for both success and error cases.
"""

from typing import Any, Dict, List, Union, Optional
from pydantic import BaseModel, Field

class ResponseStructure(BaseModel):
    """Base class for all API response schemas"""
    success: bool = Field(True, description="Indicates successful operation")
    message: str = Field("", description="Human-readable success message")
    data: Optional[Union[Dict[str, Any], List[Any]]] = Field(None, description="Response payload data")


def apiResponse(success: bool, message: str, data: Optional[Union[Dict[str, Any], List[Any]]] = None) -> ResponseStructure:
    """
    Standard success response wrapper.
    
    All successful API responses should use this structure to ensure consistency.
    """
    return ResponseStructure(success=success, message=message, data=data)