"""``load --demo`` — brief §1.10: the layer every row of which is ``is_demo=True``.

Requires ``load --real`` to have already run: it looks the 13 vendors and the category
taxonomy up by the natural keys ``real.py`` created and fails loudly (``SeedError``) if
they are missing, rather than silently building a second, disconnected copy.

Adds:

1. category *assignments* of the 13 real vendors (the taxonomy itself is real; who sits
   where is demo — brief §1.10),
2. the 4 demo suppliers, their contacts, raw indicators and category assignments,
3. the work-package breakdown of both projects — including ``TQS-238``, whose project row
   is real but whose packages are demo — and the second project, ``TQS-301``, in full,
4. document expiry rows for the vendors ``seed/data.json`` gives one to.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select

from ..db import UnitOfWork
from ..models import Category, Document, Project, Vendor, WorkPackage
from ..models.enums import DocumentStatus, ObservationSource, ScoreClass, VendorType
from ..services import audit
from ..services import categories as categories_service
from .common import (
    ensure_category_assignments,
    ensure_observations,
    find_vendor_by_seed_id,
    get_or_create_contact,
    get_or_create_project,
    get_or_create_vendor,
    observed_at,
)
from .data import PackageRow, ProjectRow, load_seed_data, parse_date, parse_int, parse_voen
from .errors import SeedError

#: The one project loaded as real (brief §1.10); its packages are still demo.
REAL_PROJECT_CODE = "TQS-238"
#: Supplier rows name their own provenance; only these two values appear in the fixture.
_SUPPLIER_SOURCES = {"excel": ObservationSource.EXCEL, "api": ObservationSource.API}


@dataclass(slots=True)
class DemoSummary:
    """Counts for the operator's summary — see ``cli.py``."""

    category_assignments_created: int = 0
    suppliers_created: int = 0
    supplier_contacts_created: int = 0
    supplier_observations_created: int = 0
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

    # 1. category assignments on the 13 real vendors.
    for vendor_row in data.vendors:
        vendor = find_vendor_by_seed_id(uow, vendor_row["id"])
        summary.category_assignments_created += ensure_category_assignments(
            uow, vendor, vendor_row.get("cats", []), category_by_code
        )

    # 2. the 4 demo suppliers.
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
            uow, supplier, supplier_row.get("cats", []), category_by_code
        )

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
