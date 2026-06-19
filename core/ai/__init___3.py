# Models package
"""
Shared Pydantic Models
======================
Data models for API requests/responses and domain entities
Shared between all microservices
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, EmailStr, field_validator
import re

try:
    from core.financial.base import PaymentMethod, PaymentStatus, PaymentType
except ImportError:
    PaymentMethod = None
    PaymentStatus = None
    PaymentType = None

try:
    from payment.models import PaymentTransaction, IdempotencyKey
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