"""Market intelligence: the six views of spec §12, computed from current observations.

Nothing here reads a cached column. Every count, share and total is assembled from the same
records the rest of the system writes — ``vendor``/``application`` for status and class
(``services.vendors.latest_result``, the same resolver the register and the matching engine
use, so the three screens never disagree about a vendor's class), ``field_observation`` for
provenance and freshness (``services.observations``), and ``document`` for expiry
(``services.documents``). Spec §12: "the intelligence views are as honest as the freshness
counter beside them" — an empty category is a gap to report, not a row to hide, and a share
with nothing to divide by is ``None``, never a fabricated zero.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from vendoriq_scoring import derive_raw

from ..catalog import DOCUMENT_CATALOG
from ..models import Application, Category, FieldObservation, Vendor, VendorCategory
from ..models import Document as DocumentRow
from ..models.enums import (
    ApplicationStatus,
    CategoryKind,
    ObservationSource,
    ScoreClass,
    VendorStatus,
    VendorType,
)
from . import applications as applications_service
from . import documents as documents_service
from . import observations as observations_service
from . import settings_store
from . import vendors as vendors_service

__all__ = [
    "attention",
    "capacity",
    "certification",
    "class_distribution",
    "coverage",
    "expiring_documents",
    "gaps",
    "overview",
    "sources",
]

#: Certification/insurance keys the penetration view reports, mapped to the ``sub-4`` raw
#: indicator code that evidences them (packages/scoring/README.md §10.1, spec §12). Scoped to
#: the subcontractor model on purpose — the contract restricts this view to "prequalified
#: subcontractors", and ``sub-4`` is the only model those vendors are ever scored with.
_CERTIFICATION_CODES: tuple[tuple[str, str], ...] = (
    ("iso9001", "C.4"),
    ("iso14001_45001", "F.2"),
    ("liability_insurance", "G.1"),
    ("audited_statements", "B.4"),
    ("hse_specialist", "E.3"),
)

#: Sources a vendor itself supplied, as opposed to what a registry, an ERP pull or an
#: officer's correction produced (spec §6.3: "the dashboard shows when a vendor's
#: self-reported number diverges from the API value").
_SELF_REPORTED_SOURCES = frozenset({ObservationSource.PORTAL, ObservationSource.EXCEL})

#: Application states still short of a decision — the officer's queue (spec §9).
_AWAITING_REVIEW_STATUSES = (
    ApplicationStatus.SUBMITTED,
    ApplicationStatus.UNDER_REVIEW,
    ApplicationStatus.INFORMATION_REQUESTED,
)


def _now() -> datetime:
    return datetime.now(UTC)


# ── shared building blocks ──────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class _VendorClass:
    vendor: Vendor
    cls: ScoreClass | None


def _all_vendors(session: Session) -> list[Vendor]:
    return list(session.scalars(select(Vendor).order_by(Vendor.legal_name.asc())))


def _classes(session: Session, vendors: list[Vendor]) -> list[_VendorClass]:
    """Every vendor with the class of its newest *decided* application, or ``None``.

    The same resolver ``services.vendors.latest_result`` uses for the register's score
    column and ``services.matching`` uses for eligibility, so the register, the matching
    screen and the market views never disagree about which class a vendor sits in.
    """
    return [
        _VendorClass(vendor=vendor, cls=vendors_service.latest_result(session, vendor.id).cls)
        for vendor in vendors
    ]


#: The newest decided application. Was a private copy here; four modules needed the same
#: query and the same "prefer the frozen snapshot" rule, and one of them had drifted, so it
#: lives in `services/applications.py` now (ADR-021).
_decided_application = applications_service.decided_application


def _raw_for_decided(session: Session, vendor: Vendor) -> dict[str, Any] | None:
    """Raw indicators *and* rubric cells of a vendor's newest decided application.

    Numeric criteria (turnover, engineers, ongoing projects) live in ``raw_snapshot`` (or, for
    a vendor scored before there was one to freeze, the current profile run through
    ``derive_raw`` — the same derivation the vendor portal and the register already use).
    Rubric criteria (the certification checks — C.4, F.2, G.1, B.4, E.3 are all 0–3 rubric
    cells in ``sub-4``) are then overlaid from ``rubric_scores``, mirroring the precedence
    ``services/evaluation.py``'s scoring path uses: the officer's cell wins when one was
    entered, the frozen/derived value stands otherwise. ``None`` when the vendor was never
    decided — there is honestly nothing to report.
    """
    application = _decided_application(session, vendor.id)
    if application is None:
        return None
    if application.raw_snapshot is not None:
        base = dict(application.raw_snapshot)
    else:
        profile = observations_service.current_profile(session, vendor.id)
        kind = "sup" if vendor.type is VendorType.SUP else "sub"
        base = dict(derive_raw(profile, kind))  # type: ignore[arg-type]
    return {**base, **dict(application.rubric_scores or {})}


def _number(value: Any) -> float:
    """``Number(v) || 0`` (packages/scoring/README.md §2) — the same coercion the engine uses,
    so a blank or non-numeric raw cell contributes nothing rather than raising."""
    if value is None:
        return 0.0
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(result) else result


def _confirmed_categories(session: Session, vendor_id: uuid.UUID) -> set[uuid.UUID]:
    return set(
        session.scalars(
            select(VendorCategory.category_id).where(
                VendorCategory.vendor_id == vendor_id, VendorCategory.confirmed.is_(True)
            )
        )
    )


def _categories(session: Session, kind: CategoryKind | None = None) -> list[Category]:
    query = select(Category).where(Category.is_active.is_(True))
    if kind is not None:
        query = query.where(Category.kind == kind)
    return list(session.scalars(query.order_by(Category.kind.asc(), Category.code.asc())))


# ── overview (KPI tiles) ─────────────────────────────────────────────────────
def overview(session: Session) -> dict[str, Any]:
    vendors = _all_vendors(session)
    classes = _classes(session, vendors)

    vendors_sub = sum(1 for v in vendors if v.type in (VendorType.SUB, VendorType.BOTH))
    vendors_sup = sum(1 for v in vendors if v.type in (VendorType.SUP, VendorType.BOTH))
    prequalified = sum(1 for v in vendors if v.status is VendorStatus.PREQUALIFIED)
    prequalified_ab = sum(
        1
        for row in classes
        if row.vendor.status is VendorStatus.PREQUALIFIED
        and row.cls in (ScoreClass.A, ScoreClass.B)
    )
    awaiting_review = (
        session.scalar(
            select(func.count())
            .select_from(Application)
            .where(Application.status.in_(_AWAITING_REVIEW_STATUSES))
        )
        or 0
    )
    incomplete = (
        session.scalar(
            select(func.count())
            .select_from(Application)
            .where(Application.status == ApplicationStatus.IN_PROGRESS)
        )
        or 0
    )
    expiring_60d = len(documents_service.expiring(session, within_days=60))
    category_gaps = len(gaps(session))

    return {
        "vendors_total": len(vendors),
        "vendors_sub": vendors_sub,
        "vendors_sup": vendors_sup,
        "prequalified": prequalified,
        "prequalified_ab": prequalified_ab,
        "awaiting_review": awaiting_review,
        "incomplete": incomplete,
        "documents_expiring_60d": expiring_60d,
        "category_gaps": category_gaps,
    }


# ── coverage matrix ──────────────────────────────────────────────────────────
def coverage(session: Session, kind: CategoryKind | None = None) -> list[dict[str, Any]]:
    """Category × class counts of *scored* vendors (spec §12) — prequalified and rejected

    alike, because the matrix answers "what does the market look like by class", not only
    "who is currently prequalified" (that narrower question is ``capacity``'s). A category
    nobody has ever confirmed and scored comes back with empty ``counts`` — a gap, per spec
    §12, not a row to hide.
    """
    vendors = _all_vendors(session)
    classes = {row.vendor.id: row.cls for row in _classes(session, vendors)}
    confirmed_by_vendor = {
        vendor.id: _confirmed_categories(session, vendor.id) for vendor in vendors
    }

    rows: list[dict[str, Any]] = []
    for category in _categories(session, kind):
        counts: dict[str, int] = {}
        for vendor in vendors:
            if category.id not in confirmed_by_vendor[vendor.id]:
                continue
            cls = classes.get(vendor.id)
            if cls is None:
                continue
            counts[cls.value] = counts.get(cls.value, 0) + 1
        total = sum(counts.values())
        ab_count = counts.get("A", 0) + counts.get("B", 0)
        rows.append(
            {
                "category_code": category.code,
                "name_az": category.name_az,
                "name_en": category.name_en,
                "kind": category.kind,
                "counts": counts,
                "total": total,
                "ab_share": (ab_count / total) if total > 0 else None,
            }
        )
    return rows


def _matches_type(filter_type: VendorType | None, vendor: Vendor) -> bool:
    """Same rule ``services.vendors._filtered`` applies: a ``both`` vendor answers a filter
    for ``sub`` or ``sup`` too, but a ``both`` filter means only ``both``."""
    if filter_type is None:
        return True
    if filter_type is VendorType.BOTH:
        return vendor.type is VendorType.BOTH
    return vendor.type in (filter_type, VendorType.BOTH)


def class_distribution(
    session: Session, vendor_type: VendorType | None = None
) -> list[dict[str, Any]]:
    """How many vendors sit in each class (spec §12), optionally narrowed to one vendor type.

    Every class band is reported, including the ones with nobody in them — a real zero, not
    an absence, so a chart never silently drops a class.
    """
    vendors = [vendor for vendor in _all_vendors(session) if _matches_type(vendor_type, vendor)]
    counts: dict[ScoreClass, int] = dict.fromkeys(ScoreClass, 0)
    for row in _classes(session, vendors):
        if row.cls is not None:
            counts[row.cls] += 1
    return [{"cls": cls, "count": counts[cls]} for cls in ScoreClass]


# ── capacity ─────────────────────────────────────────────────────────────────
def capacity(session: Session) -> list[dict[str, Any]]:
    """Prequalified vendors only: count, combined turnover, engineers, ongoing load (spec §12).

    Turnover is raw ``B.1`` (the 3-year average for subcontractors, the annual figure for
    suppliers — both models call it ``B.1``); engineers and ongoing projects are ``sub-4``'s
    ``E.2``/``C.3`` and are honestly absent (contribute 0) for a supplier, whose model has no
    such criterion.
    """
    vendors = [v for v in _all_vendors(session) if v.status is VendorStatus.PREQUALIFIED]
    confirmed_by_vendor = {
        vendor.id: _confirmed_categories(session, vendor.id) for vendor in vendors
    }
    raw_by_vendor = {vendor.id: _raw_for_decided(session, vendor) for vendor in vendors}

    rows: list[dict[str, Any]] = []
    for category in _categories(session):
        members = [v for v in vendors if category.id in confirmed_by_vendor[v.id]]
        if not members:
            continue
        turnover = 0.0
        engineers = 0
        ongoing = 0
        for vendor in members:
            raw = raw_by_vendor[vendor.id] or {}
            turnover += _number(raw.get("B.1"))
            engineers += int(_number(raw.get("E.2")))
            ongoing += int(_number(raw.get("C.3")))
        rows.append(
            {
                "category_code": category.code,
                "name_az": category.name_az,
                "name_en": category.name_en,
                "vendor_count": len(members),
                "total_turnover": turnover,
                "engineers": engineers,
                "ongoing_projects": ongoing,
            }
        )
    return rows


# ── certification & insurance penetration ───────────────────────────────────
def certification(session: Session) -> list[dict[str, Any]]:
    """Share of prequalified *subcontractors* holding each certificate/cover (spec §12)."""
    subs = [
        v
        for v in _all_vendors(session)
        if v.status is VendorStatus.PREQUALIFIED and v.type in (VendorType.SUB, VendorType.BOTH)
    ]
    total = len(subs)
    raw_by_vendor = [(_raw_for_decided(session, v) or {}) for v in subs]

    rows: list[dict[str, Any]] = []
    for key, code in _CERTIFICATION_CODES:
        held = sum(1 for raw in raw_by_vendor if _number(raw.get(code)) > 0)
        rows.append(
            {
                "key": key,
                "share": (held / total) if total > 0 else 0.0,
                "count": held,
                "total": total,
            }
        )
    return rows


# ── data sources & freshness ─────────────────────────────────────────────────
def sources(session: Session) -> dict[str, Any]:
    """Source mix and freshness (spec §6.6, §12) — the honesty check on the whole register."""
    total = session.scalar(select(func.count()).select_from(FieldObservation)) or 0
    counts: dict[ObservationSource, int] = dict(
        session.execute(
            select(FieldObservation.source, func.count()).group_by(FieldObservation.source)
        ).all()  # type: ignore[arg-type]
    )
    by_source = [
        {
            "source": source,
            "count": counts.get(source, 0),
            "share": (counts.get(source, 0) / total) if total > 0 else 0.0,
        }
        for source in ObservationSource
        if counts.get(source, 0) > 0
    ]

    stale_days = int(settings_store.group(session, "freshness").get("stale_profile_days", 90))
    now = _now()
    stale = 0
    diverging = 0
    for vendor in _all_vendors(session):
        newest = observations_service.latest_observed_at(session, vendor.id)
        if newest is None:
            # No data at all is at least as stale as data that has aged out (spec §12's
            # honesty requirement: an unknown profile is never counted as current).
            stale += 1
        else:
            if newest.tzinfo is None:
                newest = newest.replace(tzinfo=UTC)
            if (now - newest).days > stale_days:
                stale += 1
        if _diverges(session, vendor.id):
            diverging += 1

    return {
        "total_observations": total,
        "by_source": by_source,
        "stale_profiles": stale,
        "diverging_vendors": diverging,
    }


def _diverges(session: Session, vendor_id: uuid.UUID) -> bool:
    """True when at least one field carries both an API observation and a self-reported one
    (portal/excel) whose values disagree (spec §6.3, §12)."""
    by_field: dict[str, dict[ObservationSource, Any]] = {}
    for observation in session.scalars(
        select(FieldObservation).where(FieldObservation.vendor_id == vendor_id)
    ):
        by_field.setdefault(observation.field_code, {})
        existing = by_field[observation.field_code].get(observation.source)
        if existing is None or observation.observed_at >= existing[0]:
            by_field[observation.field_code][observation.source] = (
                observation.observed_at,
                observations_service.unwrap(observation.value),
            )
    for sources_for_field in by_field.values():
        api_entry = sources_for_field.get(ObservationSource.API)
        if api_entry is None:
            continue
        for source, entry in sources_for_field.items():
            if source not in _SELF_REPORTED_SOURCES:
                continue
            if entry[1] != api_entry[1]:
                return True
    return False


# ── expiring documents ───────────────────────────────────────────────────────
def expiring_documents(
    session: Session, *, within_days: int = 60, page: int = 1, page_size: int = 25
) -> dict[str, Any]:
    """Documents expiring within ``within_days``, with the vendor they belong to (spec §12)."""
    rows = documents_service.expiring(session, within_days=within_days)
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]

    vendor_ids = {row.vendor_id for row in page_rows}
    names = {
        vendor.id: vendor.legal_name
        for vendor in session.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids)))
    }
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_expiring_document_payload(row, names) for row in page_rows],
    }


def _expiring_document_payload(
    document: DocumentRow, names: dict[uuid.UUID, str]
) -> dict[str, Any]:
    definition = DOCUMENT_CATALOG.get(document.code)
    today = _now().date()
    return {
        "id": document.id,
        "vendor_id": document.vendor_id,
        "vendor_name": names.get(document.vendor_id, ""),
        "code": document.code,
        "name_az": definition.name_az if definition else document.code,
        "name_en": definition.name_en if definition else document.code,
        "mandatory": definition.mandatory if definition else False,
        "status": document.status,
        "filename": document.filename,
        "file_key": document.file_key,
        "issue_date": document.issue_date,
        "expiry_date": document.expiry_date,
        "days_to_expiry": (document.expiry_date - today).days if document.expiry_date else None,
        "verified_by": document.verified_by,
        "verified_at": document.verified_at,
    }


# ── market gaps ──────────────────────────────────────────────────────────────
def gaps(session: Session) -> list[dict[str, Any]]:
    """Categories with no prequalified, confirmed vendor (spec §11.2, §12) — the exact reason
    a package like TQS-238's flooring package comes back NO-GO."""
    vendors = _all_vendors(session)
    confirmed_by_vendor = {
        vendor.id: _confirmed_categories(session, vendor.id) for vendor in vendors
    }

    rows: list[dict[str, Any]] = []
    for category in _categories(session):
        members = [v for v in vendors if category.id in confirmed_by_vendor[v.id]]
        prequalified = [v for v in members if v.status is VendorStatus.PREQUALIFIED]
        if prequalified:
            continue
        rows.append(
            {
                "category_code": category.code,
                "name_az": category.name_az,
                "name_en": category.name_en,
                "kind": category.kind,
                "registered_vendors": len(members),
            }
        )
    return rows


# ── attention list ───────────────────────────────────────────────────────────
def attention(session: Session) -> list[dict[str, Any]]:
    """What needs a human today (spec §8, §12) — expiring documents, pending reviews,
    incomplete applications, category gaps, as i18n keys with counts (contract:
    ``AttentionItem``)."""
    kpis = overview(session)
    items = [
        {
            "key": "att_exp",
            "count": kpis["documents_expiring_60d"],
            "severity": "warn" if kpis["documents_expiring_60d"] > 0 else "info",
            "link": "/market",
        },
        {
            "key": "att_rev",
            "count": kpis["awaiting_review"],
            "severity": "warn" if kpis["awaiting_review"] > 0 else "info",
            "link": "/applications",
        },
        {
            "key": "att_inc",
            "count": kpis["incomplete"],
            "severity": "info",
            "link": "/applications",
        },
        {
            "key": "att_gap",
            "count": kpis["category_gaps"],
            "severity": "crit" if kpis["category_gaps"] > 0 else "info",
            "link": "/market",
        },
    ]
    return items
