"""Settings, the audit log and the domain event log.

Contract tags ``admin`` (settings and audit) and ``events``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from ..models.enums import (
    ScoreClass,
)
from .base import Model, PageMeta


class MatchingSettings(Model):
    strong_min: int
    capacity_ratio: float
    supplier_turnover_divisor: float
    default_min_class: ScoreClass


class QualificationSettings(Model):
    validity_months: int
    pass_mark: float
    tax_clearance_validity_months: int


class FreshnessSettings(Model):
    financials_months: int
    headcount_months: int
    stale_profile_days: int


class NotificationSettings(Model):
    expiry_reminder_days: list[int]
    expiring_window_days: int
    email_enabled: bool


class OrganisationSettings(Model):
    name: str
    default_locale: Literal["az", "en"]
    currency: Literal["AZN"]


class Settings(Model):
    matching: MatchingSettings
    qualification: QualificationSettings
    freshness: FreshnessSettings
    notifications: NotificationSettings
    organisation: OrganisationSettings


class AuditEvent(Model):
    id: uuid.UUID
    actor_id: uuid.UUID | None = None
    actor_email: str | None = None
    entity_type: str
    entity_id: uuid.UUID | None = None
    action: str
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    created_at: datetime


class AuditEventPage(PageMeta):
    items: list[AuditEvent]


class Event(Model):
    id: uuid.UUID
    type: str
    entity_type: str
    entity_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class EventPage(PageMeta):
    items: list[Event]
