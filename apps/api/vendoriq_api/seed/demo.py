"""``load --demo`` — brief §1.10: the layer every row of which is ``is_demo=True``.

Requires ``load --real`` to have already run: it looks the 13 vendors and the category
taxonomy up by the natural keys ``real.py`` created and fails loudly (``SeedError``) if
they are missing, rather than silently building a second, disconnected copy.

Adds:

1. category *assignments* of the 13 real vendors, **confirmed** — the taxonomy itself is
   real; who sits where is demo (brief §1.10), and matching only ever looks at a confirmed
   assignment (spec §11.1). Confirmation defaults to ``False`` everywhere else in this
   codebase on purpose (spec §11.1: it is an officer's judgement about evidence) — this is
   the one place that overrides the default, because fabricated data has no officer to wait
   for and the whole point of the demo layer is to show the system working (ADR-018).
2. the 4 demo suppliers, their contacts, raw indicators and confirmed category assignments,
   driven through a real qualification against ``sup-1`` — a real ``Application``, a real
   score from ``packages/scoring``, a real state-machine transition to ``prequalified`` or
   ``rejected`` — exactly the way ``real.py`` drives the 13 subcontractors against ``sub-4``.
   Their status is earned from the computed class, never copied from a claim (ADR-018).
3. the work-package breakdown of both projects — including ``TQS-238``, whose project row
   is real but whose packages are demo — and the second project, ``TQS-301``, in full,
4. document expiry rows for the vendors ``seed/data.json`` gives one to.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from vendoriq_scoring import ScoreResult, load_model, score

from ..db import UnitOfWork
from ..models import (
    Application,
    Category,
    Document,
    Project,
    QualificationCycle,
    Vendor,
    WorkPackage,
)
from ..models.enums import (
    ApplicationStatus,
    CycleKind,
    CycleStatus,
    DecisionKind,
    DocumentStatus,
    ObservationSource,
    ScoreClass,
    UserRole,
    VendorType,
)
from ..services import applications as applications_service
from ..services import audit
from ..services import categories as categories_service
from .common import (
    PREQUALIFYING_CLASSES,
    ensure_category_assignments,
    ensure_observations,
    find_vendor_by_seed_id,
    get_or_create_contact,
    get_or_create_project,
    get_or_create_vendor,
    observed_at,
)
from .data import (
    PackageRow,
    ProjectRow,
    SupplierRow,
    load_seed_data,
    parse_date,
    parse_int,
    parse_voen,
)
from .errors import SeedError

#: The one project loaded as real (brief §1.10); its packages are still demo.
REAL_PROJECT_CODE = "TQS-238"
#: Supplier rows name their own provenance; only these two values appear in the fixture.
_SUPPLIER_SOURCES = {"excel": ObservationSource.EXCEL, "api": ObservationSource.API}
#: A synthetic cycle for the 4 demo suppliers — there is no TQS number for them (they are
#: not part of the real TQS2026006 subcontractor round), just a scoring model to qualify
#: them against, the same as ``real.py``'s cycle does for the 13 subcontractors.
SUPPLIER_CYCLE_NAME = "Demo supplier qualification (sup-1)"


@dataclass(slots=True)
class DemoSummary:
    """Counts for the operator's summary — see ``cli.py``."""

    category_assignments_created: int = 0
    suppliers_created: int = 0
    supplier_contacts_created: int = 0
    supplier_observations_created: int = 0
    supplier_cycle_created: bool = False
    supplier_applications_created: int = 0
    supplier_applications_matched: int = 0
    #: How the 4 computed classes actually landed — the honest count, not the fixture's old
    #: (now-deleted) claim. Printed so a diverging outcome is visible, not silent.
    suppliers_prequalified: int = 0
    suppliers_rejected: int = 0
    projects_created: int = 0
    work_packages_created: int = 0
    documents_created: int = 0


def load_demo(uow: UnitOfWork) -> DemoSummary:
    data = load_seed_data()
    summary = DemoSummary()

    category_by_code = {
        category.code: category
        for category in categories_service.list_all(uow.session, include_inactive=True)
    }
    if not category_by_code:
        raise SeedError(
            "no categories are loaded — run `make seed` (load --real) before "
            "`make seed-demo` (load --demo)."
        )

    # 1. category assignments on the 13 real vendors — confirmed (see the module docstring
    # for why the demo layer, alone, overrides `ensure_category_assignments`'s default).
    for vendor_row in data.vendors:
        vendor = find_vendor_by_seed_id(uow, vendor_row["id"])
        summary.category_assignments_created += ensure_category_assignments(
            uow, vendor, vendor_row.get("cats", []), category_by_code, confirmed=True
        )

    # 2. the 4 demo suppliers: profile, then a real qualification against sup-1.
    supplier_model = load_model("sup-1")
    supplier_cycle: QualificationCycle | None = None
    for supplier_row in data.suppliers:
        supplier, created = get_or_create_vendor(
            uow,
            seed_id=supplier_row["id"],
            legal_name=supplier_row["name"].strip(),
            voen=parse_voen(supplier_row.get("voen")),
            vendor_type=VendorType(supplier_row["type"]),
            registration_year=parse_int(supplier_row.get("regYear")),
            address=None,
            region=supplier_row.get("region"),
            website=None,
            is_demo=True,
        )
        summary.suppliers_created += int(created)

        _, contact_created = get_or_create_contact(
            uow,
            supplier,
            name=supplier_row.get("contact"),
            position=None,
            phone=supplier_row.get("phone"),
            email=supplier_row.get("email"),
            is_demo=True,
        )
        summary.supplier_contacts_created += int(contact_created)

        source = _SUPPLIER_SOURCES.get(supplier_row.get("source", ""), ObservationSource.MANUAL)
        summary.supplier_observations_created += ensure_observations(
            uow,
            supplier,
            supplier_row.get("raw", {}),
            source=source,
            source_ref="seed/data.json (demo suppliers)",
            at=observed_at(supplier_row.get("updated")),
        )
        summary.category_assignments_created += ensure_category_assignments(
            uow, supplier, supplier_row.get("cats", []), category_by_code, confirmed=True
        )

        if supplier_cycle is None:
            supplier_cycle, summary.supplier_cycle_created = _ensure_supplier_cycle(uow)
        result = score(supplier_model, supplier_row.get("raw", {}))
        application, application_created = _ensure_supplier_application(
            uow, supplier=supplier, cycle=supplier_cycle, row=supplier_row, result=result
        )
        summary.supplier_applications_created += int(application_created)
        summary.supplier_applications_matched += int(not application_created)
        if (application.computed or {}).get("cls") in PREQUALIFYING_CLASSES:
            summary.suppliers_prequalified += 1
        else:
            summary.suppliers_rejected += 1

    # 3. work packages of both projects.
    for project_row in data.projects:
        project, project_created = _ensure_project(uow, project_row)
        summary.projects_created += int(project_created)
        for package_row in project_row.get("packages", []):
            _, package_created = _ensure_work_package(uow, project, package_row, category_by_code)
            summary.work_packages_created += int(package_created)

    # 4. document expiry rows.
    for vendor_row in data.vendors:
        docs = vendor_row.get("docs") or {}
        if not docs:
            continue
        vendor = find_vendor_by_seed_id(uow, vendor_row["id"])
        summary.documents_created += _ensure_documents(uow, vendor, docs)

    uow.flush()
    return summary


def _ensure_supplier_cycle(uow: UnitOfWork) -> tuple[QualificationCycle, bool]:
    """The demo suppliers' own cycle — ``sup-1``, not ``sub-4``, and not TQS2026006.

    Mirrors ``real.py``'s ``_ensure_cycle`` (match by name, create closed/decided), but the
    13 subcontractors and the 4 suppliers cannot share a cycle: ``QualificationCycle`` names
    one ``scoring_model_version`` for every application inside it (spec §5), and a supplier
    is scored against ``sup-1``.
    """
    existing = uow.session.scalar(
        select(QualificationCycle).where(QualificationCycle.name == SUPPLIER_CYCLE_NAME)
    )
    if existing is not None:
        return existing, False
    cycle = QualificationCycle(
        name=SUPPLIER_CYCLE_NAME,
        kind=CycleKind.PERIODIC,
        scoring_model_version="sup-1",
        project_id=None,
        status=CycleStatus.CLOSED,
        is_demo=True,
    )
    uow.session.add(cycle)
    uow.flush()
    audit.record(
        uow,
        entity_type="qualification_cycle",
        entity_id=cycle.id,
        action="seed_demo",
        after={"name": cycle.name, "status": cycle.status.value},
    )
    return cycle, True


def _ensure_supplier_application(
    uow: UnitOfWork,
    *,
    supplier: Vendor,
    cycle: QualificationCycle,
    row: SupplierRow,
    result: ScoreResult,
) -> tuple[Application, bool]:
    """Qualify one demo supplier against ``sup-1`` — earned, not asserted (ADR-018).

    Structurally identical to ``real.py``'s ``_ensure_application``: invite, walk the same
    officer-intake / submit / review / decide edges the state machine defines for anyone
    (spec §9), then record the engine's own verdict. ``seed/data.json`` no longer carries a
    ``status`` claim for suppliers — this *is* the status now, computed, not copied.
    """
    existing = uow.session.scalar(
        select(Application).where(
            Application.vendor_id == supplier.id, Application.cycle_id == cycle.id
        )
    )
    if existing is not None:
        return existing, False

    prequalified = result.cls in PREQUALIFYING_CLASSES
    target = ApplicationStatus.PREQUALIFIED if prequalified else ApplicationStatus.REJECTED

    application = applications_service.invite(uow, supplier, cycle_id=cycle.id)
    application.raw_snapshot = dict(row.get("raw", {}))
    for step in (
        ApplicationStatus.IN_PROGRESS,
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.UNDER_REVIEW,
    ):
        applications_service.transition(uow, application, step, role=UserRole.OFFICER)
    applications_service.transition(uow, application, target, role=UserRole.MANAGER)

    application.computed = asdict(result)
    application.decision = DecisionKind.APPROVE if prequalified else DecisionKind.REJECT
    updated = parse_date(row.get("updated"))
    application.decided_at = (
        datetime(updated.year, updated.month, updated.day, tzinfo=UTC)
        if updated is not None
        else datetime.now(UTC)
    )
    application.justification = (
        f"Demo qualification against sup-1: computed class {result.cls} "
        f"(total {result.total}, KO {'passed' if result.ko else 'failed'})."
    )
    uow.flush()
    audit.record(
        uow,
        entity_type="application",
        entity_id=application.id,
        action="seed_demo_decide",
        before=None,
        after={"computed": application.computed, "decision": application.decision.value},
    )
    return application, True


def _ensure_project(uow: UnitOfWork, row: ProjectRow) -> tuple[Project, bool]:
    if row["code"] == REAL_PROJECT_CODE:
        # Real project, loaded by `load --real`; only its packages are this loader's to add.
        project = uow.session.scalar(select(Project).where(Project.code == REAL_PROJECT_CODE))
        if project is None:
            raise SeedError(
                f"project {REAL_PROJECT_CODE} is not loaded — run `make seed` "
                "(load --real) before `make seed-demo` (load --demo)."
            )
        return project, False
    return get_or_create_project(uow, row, is_demo=True)


def _ensure_work_package(
    uow: UnitOfWork,
    project: Project,
    row: PackageRow,
    category_by_code: Mapping[str, Category],
) -> tuple[WorkPackage, bool]:
    category_code = row["cat"]
    category = category_by_code.get(category_code)
    if category is None:
        raise SeedError(f"work package references unknown category code {category_code!r}.")

    existing = uow.session.scalar(
        select(WorkPackage).where(
            WorkPackage.project_id == project.id, WorkPackage.category_id == category.id
        )
    )
    if existing is not None:
        return existing, False

    package = WorkPackage(
        project_id=project.id,
        category_id=category.id,
        estimated_value=row.get("value") or 0,
        min_class=ScoreClass(row.get("minClass", "C")),
        required_certs=list(row.get("certs") or []),
        is_demo=True,
    )
    uow.session.add(package)
    uow.flush()
    audit.record(
        uow,
        entity_type="work_package",
        entity_id=package.id,
        action="seed_demo",
        after={"project_id": str(project.id), "category": category_code},
    )
    return package, True


def _ensure_documents(uow: UnitOfWork, vendor: Vendor, docs: Mapping[str, str | None]) -> int:
    created = 0
    for code, expiry_text in docs.items():
        existing = uow.session.scalar(
            select(Document).where(Document.vendor_id == vendor.id, Document.code == code)
        )
        if existing is not None:
            continue
        document = Document(
            vendor_id=vendor.id,
            code=code,
            status=DocumentStatus.UPLOADED,
            # `None` here is the fixture's own "Müddətsiz" case (brief §1.11) — a document
            # on file that never expires, not a missing date.
            expiry_date=parse_date(expiry_text) if expiry_text else None,
            is_demo=True,
        )
        uow.session.add(document)
        created += 1
    if created:
        uow.flush()
        audit.record(
            uow,
            entity_type="vendor",
            entity_id=vendor.id,
            action="seed_demo_documents",
            after={"codes": sorted(docs)},
        )
    return created
