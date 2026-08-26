"""Get-or-create helpers shared by ``real.py`` and ``demo.py``.

Every loader in this package is idempotent by the same recipe: look the row up by a
natural key, create it if absent, otherwise touch only the columns that actually differ.
Putting that recipe here once means the 13 vendors, the 4 demo suppliers and the two
projects are all matched the same way instead of five slightly different ones.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from ..db import UnitOfWork
from ..models import Category, Contact, FieldObservation, Project, Vendor, VendorCategory
from ..models.enums import ObservationSource, ProjectStage, VendorType
from ..services import audit
from ..services import contacts as contacts_service
from ..services import observations as observations_service
from ..services import vendors as vendors_service
from .data import ProjectRow, parse_date
from .errors import SeedError

#: Classes a Rev4/sup-1 qualification invites; the rest is rejected (brief §1.6, §1.10).
#: Shared by ``real.py`` (the 13 subcontractors) and ``demo.py`` (the 4 demo suppliers) —
#: one earned-outcome rule, not two copies that could quietly drift apart.
PREQUALIFYING_CLASSES = frozenset({"A", "B", "C"})


def external_ref(seed_id: str) -> str:
    """The stable natural key a seed-loaded row carries in ``external_ref``.

    Vöen cannot serve as that key on its own: four of the thirteen real vendors have none
    (brief §1.10 — they submitted nothing), and matching by legal name is fragile once a
    staff edit is allowed to change it. The seed's own row id (``V01`` … ``V13``, ``S01`` …
    ``S04``, ``P238``/``P301``) is stable for the life of the fixture, so it becomes the
    ``external_ref`` — a legitimate use of the column spec §2 already reserves for
    cross-system mapping.
    """
    return f"seed:{seed_id}"


def observed_at(updated: str | None) -> datetime:
    """``row["updated"]`` as a UTC instant, or "now" when the fixture carries none."""
    parsed = parse_date(updated)
    if parsed is None:
        return datetime.now(UTC)
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=UTC)


def get_or_create_vendor(
    uow: UnitOfWork,
    *,
    seed_id: str,
    legal_name: str,
    voen: str | None,
    vendor_type: VendorType,
    registration_year: int | None,
    address: str | None,
    region: str | None,
    website: str | None,
    is_demo: bool,
) -> tuple[Vendor, bool]:
    """Match by ``external_ref``; create through the service, otherwise patch what changed."""
    ref = external_ref(seed_id)
    existing = uow.session.scalar(select(Vendor).where(Vendor.external_ref == ref))
    if existing is None:
        vendor = vendors_service.create(
            uow,
            legal_name=legal_name,
            type=vendor_type,
            voen=voen,
            is_demo=is_demo,
            external_ref=ref,
            registration_year=registration_year,
            address=address,
            region=region,
            website=website,
        )
        return vendor, True

    changes: dict[str, Any] = {}
    for key, value in (
        ("legal_name", legal_name),
        ("voen", voen),
        ("type", vendor_type),
        ("registration_year", registration_year),
        ("address", address),
        ("region", region),
        ("website", website),
    ):
        if value is not None and getattr(existing, key) != value:
            changes[key] = value
    if changes:
        # `role=None`: a re-seed is not a staff edit and needs no reason (spec §6.5 exists
        # to make a *human* justify overwriting a vendor's own claim, not to gate the
        # fixture reproducing itself).
        vendors_service.patch(uow, existing, changes, role=None)
    return existing, False


def get_or_create_contact(
    uow: UnitOfWork,
    vendor: Vendor,
    *,
    name: str | None,
    position: str | None,
    phone: str | None,
    email: str | None,
    is_demo: bool = False,
) -> tuple[Contact | None, bool]:
    """One contact per vendor from the fixture; matched by e-mail, falling back to name."""
    if not name:
        return None, False
    existing = None
    if email:
        existing = uow.session.scalar(
            select(Contact).where(
                Contact.vendor_id == vendor.id, func.lower(Contact.email) == email.lower()
            )
        )
    if existing is None:
        existing = uow.session.scalar(
            select(Contact).where(Contact.vendor_id == vendor.id, Contact.name == name)
        )
    if existing is not None:
        changes: dict[str, Any] = {}
        for key, value in (
            ("name", name),
            ("position", position),
            ("phone", phone),
            ("email", email),
        ):
            if value is not None and getattr(existing, key) != value:
                changes[key] = value
        if changes:
            contacts_service.patch(uow, existing, changes)
        return existing, False

    contact = contacts_service.create(
        uow,
        vendor.id,
        {"name": name, "position": position, "phone": phone, "email": email, "is_primary": True},
    )
    if is_demo:
        contact.is_demo = True
        uow.flush()
    return contact, True


def ensure_observations(
    uow: UnitOfWork,
    vendor: Vendor,
    raw: Mapping[str, float | int],
    *,
    source: ObservationSource,
    source_ref: str,
    at: datetime,
) -> int:
    """Write one observation per raw indicator, skipping any the seed already wrote.

    "Already wrote" means the same vendor, field code, source and ``source_ref`` — the
    seed's own natural key for a row it authored (README: "Provenance"). A later change of
    *value* in the fixture is still a new append, which is the point of an append-only log;
    a second run with the same value is not.
    """
    created = 0
    for field_code, value in raw.items():
        exists = uow.session.scalar(
            select(FieldObservation.id).where(
                FieldObservation.vendor_id == vendor.id,
                FieldObservation.field_code == field_code,
                FieldObservation.source == source,
                FieldObservation.source_ref == source_ref,
            )
        )
        if exists is not None:
            continue
        observations_service.record(
            uow,
            vendor.id,
            field_code,
            value,
            source=source,
            source_ref=source_ref,
            observed_at=at,
        )
        created += 1
    return created


def ensure_category_assignments(
    uow: UnitOfWork,
    vendor: Vendor,
    codes: Sequence[str],
    category_by_code: Mapping[str, Category],
    *,
    confirmed: bool = False,
) -> int:
    """Add the vendor's category codes as ``is_demo`` assignments (brief §1.10).

    ``confirmed`` defaults to ``False`` — the real/import path's protection stays exactly
    as it was (spec §11.1: only a *confirmed* assignment is a matching candidate, and
    confirming one is an officer's judgement about evidence, never the seed's to assert on
    a vendor's own say-so). The demo layer passes ``confirmed=True`` explicitly instead of
    this default changing under it: fabricated data has no officer to wait for, and the
    whole point of the demo layer is to show matching working (ADR-018).

    Written directly rather than through ``services.categories.set_for_vendor``: that
    function replaces the whole selection and has neither an ``is_demo`` nor a
    ``confirmed`` parameter, and the seed only ever adds — it must never remove, or
    un-confirm, a category an officer has since reviewed. For the same reason, an existing
    row only has its ``confirmed`` flag corrected here when it is itself ``is_demo`` — a
    real assignment's confirmation is never the seed's to move either way.
    """
    existing_rows = {
        row.category.code: row
        for row in uow.session.scalars(
            select(VendorCategory).where(VendorCategory.vendor_id == vendor.id)
        )
    }
    created = 0
    touched: list[str] = []
    for code in codes:
        existing = existing_rows.get(code)
        if existing is not None:
            if existing.is_demo and existing.confirmed != confirmed:
                existing.confirmed = confirmed
                touched.append(code)
            continue
        category = category_by_code.get(code)
        if category is None:
            raise SeedError(
                f"vendor {vendor.legal_name!r} references unknown category code {code!r}."
            )
        uow.session.add(
            VendorCategory(
                vendor_id=vendor.id,
                category_id=category.id,
                confirmed=confirmed,
                is_demo=True,
            )
        )
        created += 1
        touched.append(code)
    if touched:
        uow.flush()
        audit.record(
            uow,
            entity_type="vendor",
            entity_id=vendor.id,
            action="seed_demo_categories",
            after={"codes": sorted(touched), "confirmed": confirmed},
        )
    return created


def get_or_create_project(
    uow: UnitOfWork, row: ProjectRow, *, is_demo: bool
) -> tuple[Project, bool]:
    """Match by ``Project.code`` — already the model's own unique natural key."""
    code = row["code"]
    existing = uow.session.scalar(select(Project).where(Project.code == code))
    if existing is not None:
        return existing, False

    project = Project(
        code=code,
        name=row["name"],
        client=row.get("client"),
        stage=ProjectStage(row["stage"]),
        estimated_value=row.get("value"),
        deadline=parse_date(row.get("deadline")),
        external_ref=external_ref(row["id"]),
        is_demo=is_demo,
    )
    uow.session.add(project)
    uow.flush()
    audit.record(
        uow,
        entity_type="project",
        entity_id=project.id,
        action="seed",
        after={"code": project.code, "name": project.name, "is_demo": is_demo},
    )
    return project, True


def find_vendor_by_seed_id(uow: UnitOfWork, seed_id: str) -> Vendor:
    """The looked-up counterpart of :func:`get_or_create_vendor`, for the demo pass."""
    vendor = uow.session.scalar(select(Vendor).where(Vendor.external_ref == external_ref(seed_id)))
    if vendor is None:
        raise SeedError(
            f"vendor {seed_id} is not loaded — run `make seed` (load --real) before "
            "`make seed-demo` (load --demo)."
        )
    return vendor
