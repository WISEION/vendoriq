"""``load --real`` — brief §1.10: the facts that do not carry ``is_demo``.

Loads, in the order ``seed/README.md`` documents (models and categories first, then
vendors, then the cycle and applications that need the vendors to already exist):

1. the two scoring models (``sub-4``, ``sup-1``) from the packages/scoring JSON,
2. the 15-code category taxonomy,
3. the 13 real vendors, their contacts and their raw indicators as ``FieldObservation``
   rows (``source=excel``),
4. the real project ``TQS-238`` (its packages are demo — ``demo.py`` adds them),
5. the qualification cycle ``TQS2026006`` and the 13 vendors' applications in it, each
   recomputed with ``packages/scoring`` and checked against the sheet's own total before a
   single row is written,
6. the seeded test accounts, when ``AUTH_MODE=test`` (brief §6).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime

from sqlalchemy import select
from vendoriq_scoring import BUILTIN_MODEL_VERSIONS, ScoreResult, load_model, score

from ..config import Settings
from ..db import UnitOfWork
from ..models import (
    Application,
    Category,
    QualificationCycle,
    ScoringModel,
    ScoringModelStatus,
    User,
    Vendor,
)
from ..models.enums import (
    ApplicationStatus,
    CategoryKind,
    CycleKind,
    CycleStatus,
    DecisionKind,
    ObservationSource,
    UserRole,
    VendorType,
)
from ..services import accounts as accounts_service
from ..services import applications as applications_service
from ..services import audit
from ..services import categories as categories_service
from .common import (
    ensure_observations,
    get_or_create_contact,
    get_or_create_project,
    get_or_create_vendor,
    observed_at,
)
from .data import (
    DATA_JSON_SOURCE_REF,
    CategoryLabel,
    VendorRow,
    load_seed_data,
    parse_date,
    parse_int,
    parse_voen,
)
from .errors import SeedError

#: The qualification cycle these 13 vendors were scored in (brief §1.10).
CYCLE_NAME = "TQS2026006 Rev4"
#: The one project named as a real fact alongside them (brief §1.10).
PROJECT_CODE = "TQS-238"
#: Classes the Rev4 process invites; the rest is rejected (brief §1.6, §1.10).
PREQUALIFYING_CLASSES = frozenset({"A", "B", "C"})


@dataclass(slots=True)
class RealSummary:
    """Counts for the operator's summary — see ``cli.py``."""

    categories_created: int = 0
    scoring_models_loaded: int = 0
    vendors_created: int = 0
    vendors_matched: int = 0
    contacts_created: int = 0
    observations_created: int = 0
    project_created: bool = False
    cycle_created: bool = False
    applications_created: int = 0
    applications_matched: int = 0
    test_accounts: list[tuple[User, str | None]] = field(default_factory=list)


def load_real(uow: UnitOfWork, *, settings: Settings) -> RealSummary:
    data = load_seed_data()
    summary = RealSummary()

    summary.scoring_models_loaded = _ensure_scoring_models(uow)
    _, summary.categories_created = _ensure_categories(uow, data.categories)

    model = load_model("sub-4")
    vendor_by_seed_id: dict[str, Vendor] = {}
    for row in data.vendors:
        vendor, created = get_or_create_vendor(
            uow,
            seed_id=row["id"],
            legal_name=row["name"].strip(),
            voen=parse_voen(row.get("voen")),
            vendor_type=VendorType(row["type"]),
            registration_year=parse_int(row.get("regYear")),
            address=row.get("address"),
            region=row.get("region"),
            website=row.get("website"),
            is_demo=False,
        )
        vendor_by_seed_id[row["id"]] = vendor
        summary.vendors_created += int(created)
        summary.vendors_matched += int(not created)

        _, contact_created = get_or_create_contact(
            uow,
            vendor,
            name=row.get("contact"),
            position=row.get("position"),
            phone=row.get("phone"),
            email=row.get("email"),
        )
        summary.contacts_created += int(contact_created)

        summary.observations_created += ensure_observations(
            uow,
            vendor,
            row["raw"],
            source=ObservationSource.EXCEL,
            source_ref=DATA_JSON_SOURCE_REF,
            at=observed_at(row.get("updated")),
        )

        # Fail loudly before any application row is written (brief §1.10).
        _assert_matches_sheet(row, score(model, row["raw"]))

    project_row = next(p for p in data.projects if p["code"] == PROJECT_CODE)
    project, summary.project_created = get_or_create_project(uow, project_row, is_demo=False)

    cycle, summary.cycle_created = _ensure_cycle(uow, project_id=project.id)

    used_sub4 = False
    for row in data.vendors:
        vendor = vendor_by_seed_id[row["id"]]
        result = score(model, row["raw"])
        _, application_created = _ensure_application(
            uow, vendor=vendor, cycle=cycle, row=row, result=result
        )
        summary.applications_created += int(application_created)
        summary.applications_matched += int(not application_created)
        used_sub4 = used_sub4 or application_created

    if used_sub4:
        sub4 = uow.session.get(ScoringModel, "sub-4")
        if sub4 is not None and not sub4.is_locked:
            # spec §10.3: a model version becomes immutable once an application is scored
            # with it, and these 13 applications now are (brief §1.10 — "real Rev4 outcome").
            sub4.is_locked = True

    if settings.auth_mode == "test":
        summary.test_accounts = accounts_service.create_test_accounts(uow, settings)

    uow.flush()
    return summary


def _assert_matches_sheet(row: VendorRow, result: ScoreResult) -> None:
    if result.total != row["sheetTotal"]:
        raise SeedError(
            f"{row['id']} {row['name']!r} recomputed to {result.total}, but the Rev4 "
            f"sheet says {row['sheetTotal']} — refusing to store a wrong score "
            "(brief §1.10: fail loudly, not quietly)."
        )


def _ensure_scoring_models(uow: UnitOfWork) -> int:
    """Load the two built-in models. Locking is left to the caller (used vs. proposed)."""
    created = 0
    for version in BUILTIN_MODEL_VERSIONS:
        document = load_model(version)
        row = uow.session.get(ScoringModel, version)
        if row is None:
            row = ScoringModel(version=version)
            uow.session.add(row)
            created += 1
        row.vendor_type = VendorType(document.vendor_type)
        # Migration 0003 gave the table the columns the contract requires, so every field the
        # JSON carries now lands in one. `currency` and `total_max` stay out by design — see
        # the migration and the model docstring. The JSON file remains the contract
        # (CONTRIBUTING); this row is what the API serves from.
        row.name_az = document.name_az
        row.name_en = document.name_en
        row.status = ScoringModelStatus(document.status)
        row.groups = list(document.groups)
        row.criteria = list(document.criteria)
        row.classes = list(document.classes)
        row.pass_mark = document.pass_mark
        row.validity_months = document.validity_months
        row.notes = {
            "source": f"packages/scoring/vendoriq_scoring/models/{version}.json",
        }
    uow.flush()
    return created


def _ensure_categories(
    uow: UnitOfWork, categories: dict[str, CategoryLabel]
) -> tuple[dict[str, Category], int]:
    created = 0
    by_code: dict[str, Category] = {}
    for code, label in categories.items():
        existing = categories_service.by_code(uow.session, code)
        if existing is not None:
            by_code[code] = existing
            continue
        kind = CategoryKind.MATERIAL if code.startswith("m_") else CategoryKind.WORK
        by_code[code] = categories_service.create(
            uow,
            {"code": code, "name_az": label["az"], "name_en": label["en"], "kind": kind.value},
        )
        created += 1
    return by_code, created


def _ensure_cycle(uow: UnitOfWork, *, project_id: uuid.UUID) -> tuple[QualificationCycle, bool]:
    existing = uow.session.scalar(
        select(QualificationCycle).where(QualificationCycle.name == CYCLE_NAME)
    )
    if existing is not None:
        return existing, False
    cycle = QualificationCycle(
        name=CYCLE_NAME,
        kind=CycleKind.TENDER,
        scoring_model_version="sub-4",
        project_id=project_id,
        status=CycleStatus.CLOSED,
        # The one date the fixture gives for the whole cycle: every vendor's Rev4 history
        # entry is dated 2026-04-28 (seed/data.json) — not invented, just uniform.
        closes_at=datetime(2026, 4, 28, tzinfo=UTC),
        is_demo=False,
    )
    uow.session.add(cycle)
    uow.flush()
    audit.record(
        uow,
        entity_type="qualification_cycle",
        entity_id=cycle.id,
        action="seed",
        after={"name": cycle.name, "status": cycle.status.value},
    )
    return cycle, True


def _rev4_decision_date(row: VendorRow) -> date:
    for entry in row.get("history", []):
        if "Rev4" in str(entry.get("cycle", "")):
            parsed = parse_date(entry.get("date"))
            if parsed is not None:
                return parsed
    raise SeedError(f"{row['id']} has no dated Rev4 entry in its history (seed/data.json).")


def _ensure_application(
    uow: UnitOfWork,
    *,
    vendor: Vendor,
    cycle: QualificationCycle,
    row: VendorRow,
    result: ScoreResult,
) -> tuple[Application, bool]:
    existing = uow.session.scalar(
        select(Application).where(
            Application.vendor_id == vendor.id, Application.cycle_id == cycle.id
        )
    )
    if existing is not None:
        return existing, False

    prequalified = result.cls in PREQUALIFYING_CLASSES
    target = ApplicationStatus.PREQUALIFIED if prequalified else ApplicationStatus.REJECTED

    application = applications_service.invite(uow, vendor, cycle_id=cycle.id)
    application.raw_snapshot = dict(row["raw"])
    # Officer intake -> submission -> review, then the manager's decision (spec §9). The
    # seed plays the officer's part for the first three edges — brief's state machine
    # names "an officer typing on the vendor's behalf (an Excel intake)" as the same move.
    for step in (
        ApplicationStatus.IN_PROGRESS,
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
    ):
        applications_service.transition(uow, application, step, role=UserRole.OFFICER)
    applications_service.transition(uow, application, target, role=UserRole.MANAGER)

    application.computed = asdict(result)
    application.decision = DecisionKind.APPROVE if prequalified else DecisionKind.REJECT
    application.decided_at = _decided_at(row)
    application.justification = f"Rev4 workbook TQS2026006: {row['sheetDecision']}"
    uow.flush()
    audit.record(
        uow,
        entity_type="application",
        entity_id=application.id,
        action="seed_decide",
        before=None,
        after={"computed": application.computed, "decision": application.decision.value},
    )
    return application, True


def _decided_at(row: VendorRow) -> datetime:
    decided_date = _rev4_decision_date(row)
    return datetime(decided_date.year, decided_date.month, decided_date.day, tzinfo=UTC)
