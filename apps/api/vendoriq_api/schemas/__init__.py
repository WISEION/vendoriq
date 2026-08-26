"""Request and response shapes, transcribed from ``docs/openapi.yaml``.

These models do **not** generate the published schema (ADR-006 — the hand-written contract is
served verbatim). They exist so the handlers parse and serialise exactly what the contract
declares, and ``tests/test_contract_shapes.py`` checks the two against each other.

One module per contract tag. This was a single 454-line module until phase 2, where seven
tasks build in parallel: one file per tag means one owner per file, so two workers adding
shapes for different tags do not meet in the same diff. Everything is re-exported here, so
``from ..schemas import Vendor`` keeps working and no handler had to change.

The phase-2 modules start empty; the task that implements a tag fills its own.
"""

from __future__ import annotations

from . import applications as applications
from . import cycles as cycles
from . import integrations as integrations
from . import intel as intel
from . import projects as projects
from . import scoring_models as scoring_models
from .admin import (
    AuditEvent,
    AuditEventPage,
    Event,
    EventPage,
    FreshnessSettings,
    MatchingSettings,
    NotificationSettings,
    OrganisationSettings,
    QualificationSettings,
    Settings,
)
from .auth import (
    Health,
    Me,
    OtpChallenge,
    OtpRequest,
    OtpVerification,
    Session,
    StaffLogin,
    TotpChallenge,
    TotpVerification,
    User,
    UserCreated,
    UserInput,
    UserPage,
    UserRoleInput,
    VendorRegistration,
)
from .base import EmailStr, Model, PageMeta
from .vendors import (
    Application,
    Category,
    CategoryCodes,
    CategoryConfirmation,
    CategoryInput,
    Contact,
    ContactInput,
    Document,
    DocumentPatch,
    DownloadTicket,
    EvaluationSummary,
    FieldObservation,
    FieldObservationPage,
    InviteInput,
    ObservationInput,
    SuspendInput,
    UploadCompletion,
    UploadInit,
    UploadTicket,
    Vendor,
    VendorCategory,
    VendorCreate,
    VendorDetail,
    VendorPage,
    VendorPatch,
)

__all__ = [
    "Application",
    "AuditEvent",
    "AuditEventPage",
    "Category",
    "CategoryCodes",
    "CategoryConfirmation",
    "CategoryInput",
    "Contact",
    "ContactInput",
    "Document",
    "DocumentPatch",
    "DownloadTicket",
    "EmailStr",
    "EvaluationSummary",
    "Event",
    "EventPage",
    "FieldObservation",
    "FieldObservationPage",
    "FreshnessSettings",
    "Health",
    "InviteInput",
    "MatchingSettings",
    "Me",
    "Model",
    "NotificationSettings",
    "ObservationInput",
    "OrganisationSettings",
    "OtpChallenge",
    "OtpRequest",
    "OtpVerification",
    "PageMeta",
    "QualificationSettings",
    "Session",
    "Settings",
    "StaffLogin",
    "SuspendInput",
    "TotpChallenge",
    "TotpVerification",
    "UploadCompletion",
    "UploadInit",
    "UploadTicket",
    "User",
    "UserCreated",
    "UserInput",
    "UserPage",
    "UserRoleInput",
    "Vendor",
    "VendorCategory",
    "VendorCreate",
    "VendorDetail",
    "VendorPage",
    "VendorPatch",
    "VendorRegistration",
]
