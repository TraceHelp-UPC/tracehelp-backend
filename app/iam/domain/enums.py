"""Enumeraciones del contexto IAM."""
from enum import StrEnum


class RoleName(StrEnum):
    COLLABORATOR = "COLLABORATOR"
    ANALYST_L1 = "ANALYST_L1"
    SPECIALIST_L2 = "SPECIALIST_L2"
    IT_LEADER = "IT_LEADER"


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    LOCKED = "LOCKED"


class AvailabilityStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
