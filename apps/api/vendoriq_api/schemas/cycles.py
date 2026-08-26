"""Qualification cycles and invitations.

Contract tag ``cycles``. Owned by phase-2 task 2C.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from ..models.enums import CycleKind, CycleStatus
from .auth import User
from .base import Model, PageMeta
from .vendors import Application


class Cycle(Model):
    id: uuid.UUID
    name: str
    kind: CycleKind
    scoring_model_version: str
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    project_id: uuid.UUID | None = None
    status: CycleStatus
    application_count: int = 0
    is_demo: bool = False


class CycleInput(Model):
    name: str
    kind: CycleKind
    scoring_model_version: str
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    project_id: uuid.UUID | None = None
    status: CycleStatus | None = None


class CycleDetail(Cycle):
    counts_by_status: dict[str, int] = Field(default_factory=dict)
    #: No committee-membership table exists yet (spec §5 does not define one) — always empty
    #: rather than inventing membership data (brief §4.3: unknown facts stay empty).
    committee: list[User] = Field(default_factory=list)


class CyclePage(PageMeta):
    items: list[Cycle]


class CycleInviteInput(Model):
    vendor_ids: list[uuid.UUID]
    message_az: str | None = None
    message_en: str | None = None


class CycleInviteSkip(Model):
    vendor_id: uuid.UUID
    reason: str


class CycleInviteResult(Model):
    invited: list[Application]
    skipped: list[CycleInviteSkip]


__all__ = [
    "Cycle",
    "CycleDetail",
    "CycleInput",
    "CycleInviteInput",
    "CycleInviteResult",
    "CycleInviteSkip",
    "CyclePage",
]
