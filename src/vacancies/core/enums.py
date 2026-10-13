from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional


class WorkFormat(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    OFFICE = "office"
    UNKNOWN = "unknown"


class Currency(str, Enum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"
    UNKNOWN = "unknown"


class TaxType(str, Enum):
    GROSS = "gross"
    NET = "net"
    UNKNOWN = "unknown"


class DmsStatus(str, Enum):
    CONFIRMED = "confirmed"
    NOT_MENTIONED = "not_mentioned"
    UNKNOWN = "unknown"


class VacancyStatus(str, Enum):
    SUITABLE = "suitable"
    NEEDS_CLARIFICATION = "needs_clarification"
    NOT_SUITABLE = "not_suitable"
    CHECK_FAILED = "check_failed"


class DataCompleteness(IntEnum):
    FULL = 3
    PARTIAL = 2
    MINIMAL = 1
    UNKNOWN = 0
