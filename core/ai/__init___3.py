# Models package
"""
Shared Pydantic Models
======================
Data models for API requests/responses and domain entities
Shared between all microservices
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

try:
    from core.financial.base import PaymentMethod, PaymentStatus, PaymentType
except ImportError:
    PaymentMethod = None
    PaymentStatus = None
    PaymentType = None

try:
    pass
except ImportError:
    pass

__all__ = [
    'BaseModel',
    'Field',
    'EmailStr',
    'datetime',
    'Optional',
    'List',
    'Dict',
    'Any',
    'Enum',
    'field_validator',
]