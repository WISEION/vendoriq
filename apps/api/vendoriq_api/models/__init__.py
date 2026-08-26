"""SQLAlchemy 2 declarative models covering every entity of spec §5.

Importing this package registers every table on ``Base.metadata`` — Alembic's
``env.py`` and the test fixtures rely on that.
"""

from __future__ import annotations

from .auth import ApiKey, OtpCode, RevokedSession, User
from .base import Base, TimestampMixin
from .catalog import Category, VendorCategory
from .document import Document
from .enums import (
    CONTRACT_ADAPTER_KEYS,
    SOURCE_TRUST_RANK,
    AdapterKey,
    ApplicationStatus,
    CategoryKind,
    CycleKind,
    CycleStatus,
    DecisionKind,
    DocumentExpiryState,
    DocumentStatus,
    EventType,
    MatchState,
    ObservationSource,
    ProjectStage,
    Scope,
    ScoreClass,
    ScoringModelStatus,
    SyncResult,
    UserRole,
    VendorStatus,
    VendorType,
)
from .evaluation import Evaluation
from .events import AuditEvent, Event
from .integration import AdapterConfig, ImportPreview, SyncLog, Webhook
from .observation import FieldObservation
from .performance import PerformanceRecord
from .project import MatchRun, Project, WorkPackage
from .qualification import Application, QualificationCycle
from .scoring_model import ScoringModel
from .setting import Setting
from .vendor import Contact, Vendor

__all__ = [
    "CONTRACT_ADAPTER_KEYS",
    "SOURCE_TRUST_RANK",
    "AdapterConfig",
    "AdapterKey",
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
    "DocumentExpiryState",
    "DocumentStatus",
    "Evaluation",
    "Event",
    "EventType",
    "FieldObservation",
    "ImportPreview",
    "MatchRun",
    "MatchState",
    "ObservationSource",
    "OtpCode",
    "PerformanceRecord",
    "Project",
    "ProjectStage",
    "QualificationCycle",
    "RevokedSession",
    "Scope",
    "ScoreClass",
    "ScoringModel",
    "ScoringModelStatus",
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
