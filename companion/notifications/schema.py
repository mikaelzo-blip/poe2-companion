"""Domain schemas and models for companion notifications."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any
import uuid
from pydantic import BaseModel, ConfigDict, Field


class NotificationSeverity(str, Enum):
    """Notification urgency levels."""

    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class NotificationCategory(str, Enum):
    """Categorical source of notification."""

    SURVIVAL = "SURVIVAL"
    TRANSITION = "TRANSITION"
    STAT_REQUIREMENT = "STAT_REQUIREMENT"
    RULE_VIOLATION = "RULE_VIOLATION"
    OPTIMIZATION = "OPTIMIZATION"


class NotificationPayload(BaseModel):
    """Immutable notification payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    title: str
    message: str
    severity: NotificationSeverity
    category: NotificationCategory
    dedupe_key: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def create(
        cls,
        title: str,
        message: str,
        severity: NotificationSeverity,
        category: NotificationCategory,
        dedupe_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> NotificationPayload:
        if dedupe_key is None:
            raw = f"{category.value}:{title}:{message}"
            dedupe_key = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

        return cls(
            title=title,
            message=message,
            severity=severity,
            category=category,
            dedupe_key=dedupe_key,
            metadata=metadata or {},
        )
