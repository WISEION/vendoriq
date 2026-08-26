"""SQLAlchemy 2 declarative models covering every entity of spec §5.

Importing this package registers every table on ``Base.metadata`` — Alembic's
``env.py`` and the test fixtures rely on that.
"""

from __future__ import annotations

from .auth import ApiKey, OtpCode, User
from .base import Base, TimestampMixin
from .catalog import Category, VendorCategory
from .document import Document
from .enums import (
    SOURCE_TRUST_RANK,
    ApplicationStatus,
    CategoryKind,
    CycleKind,
    CycleStatus,
    DecisionKind,
    DocumentStatus,
    MatchState,
    ObservationSource,
    ProjectStage,
    ScoreClass,
    SyncResult,
    UserRole,
    VendorStatus,
    VendorType,
)
from .events import AuditEvent, Event
from .integration import SyncLog, Webhook
from .observation import FieldObservation
from .performance import PerformanceRecord
from .project import MatchRun, Project, WorkPackage
from .qualification import Application, QualificationCycle
from .scoring_model import ScoringModel
from .setting import Setting
from .vendor import Contact, Vendor

__all__ = [
    "SOURCE_TRUST_RANK",
    "ApiKey",
    "Application",
    "ApplicationStatus",
    "AuditEvent",
    "Base",
    "Category",
    "CategoryKind",
    "Contact",
    "CycleKind",
    "CycleStatus",
    "DecisionKind",
    "Document",
    "DocumentStatus",
    "Event",
    "FieldObservation",
    "MatchRun",
    "MatchState",
    "ObservationSource",
    "OtpCode",
    "PerformanceRecord",
    "Project",
    "ProjectStage",
    "QualificationCycle",
    "ScoreClass",
    "ScoringModel",
    "Setting",
    "SyncLog",
    "SyncResult",
    "TimestampMixin",
    "User",
    "UserRole",
    "Vendor",
    "VendorCategory",
    "VendorStatus",
    "VendorType",
    "Webhook",
    "WorkPackage",
]
