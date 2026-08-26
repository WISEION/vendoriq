"""Vendor <-> project-package matching: the DB adapter around ``packages/scoring`` (spec §11).

This module never decides a threshold, a capacity ratio or a gap label — that is
``vendoriq_scoring.match_project``'s job alone (packages/scoring/README.md §4). What lives
here is entirely about *assembling the engine's inputs from the database*: which vendors are
candidates, what raw indicators and scored model they carry, and what a project's packages
look like as ``PackageInput`` rows. ``services/projects.py`` calls :func:`run` and persists
the result; nothing here writes to the database.
"""

from __future__ import annotations

from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_scoring import derive_raw
from vendoriq_scoring import match_project as _match_project
from vendoriq_scoring.types import (
    CandidateInput,
    PackageInput,
    ProjectInput,
    ProjectMatch,
    RawIndicators,
)
from vendoriq_scoring.types import MatchParams as EngineMatchParams

from ..models import Application, Project, Vendor
from ..models.enums import VendorStatus, VendorType
from . import categories as categories_service
from . import observations as observations_service
from . import settings_store

__all__ = [
    "EngineMatchParams",
    "build_candidates",
    "project_input",
    "resolve_params",
    "run",
    "serialize",
]

#: Fallback model version by vendor type, when the vendor has never had an application to
#: read a scored ``model_version`` from — mirrors ``routers/vendors.py``'s ``_raw_indicators``
#: (``kind = "sup" if vendor_type is VendorType.SUP else "sub"``).
_DEFAULT_MODEL_VERSION: dict[VendorType, str] = {
    VendorType.SUB: "sub-4",
    VendorType.SUP: "sup-1",
    VendorType.BOTH: "sub-4",
}


def resolve_params(
    session: Session, override: dict[str, float | int | None] | None
) -> EngineMatchParams:
    """Organisation defaults from ``setting``, overridden per run (spec §11.2, ``MatchParams``)."""
    defaults = settings_store.group(session, "matching")
    merged = {
        "strong_min": defaults.get("strong_min", 2),
        "capacity_ratio": defaults.get("capacity_ratio", 0.40),
        "supplier_turnover_divisor": defaults.get("supplier_turnover_divisor", 4.0),
    }
    if override:
        for key, value in override.items():
            if value is not None and key in merged:
                merged[key] = value
    return EngineMatchParams(
        strong_min=int(merged["strong_min"]),
        capacity_ratio=float(merged["capacity_ratio"]),
        supplier_turnover_divisor=float(merged["supplier_turnover_divisor"]),
    )


def _best_application(session: Session, vendor_id: object) -> Application | None:
    """The application whose score and model best describe this vendor right now.

    A decided application (spec §9's terminal states) wins over an in-flight one, and the
    most recently decided wins over an older one — the same rule
    ``services.vendors.latest_result`` uses for the register's score column, so the matching
    screen and the register never disagree about which score is "the" score.
    """
    decided = session.scalars(
        select(Application)
        .where(Application.vendor_id == vendor_id, Application.decided_at.is_not(None))
        .order_by(Application.decided_at.desc())
        .limit(1)
    ).first()
    if decided is not None:
        return decided
    return session.scalars(
        select(Application)
        .where(Application.vendor_id == vendor_id)
        .order_by(Application.updated_at.desc())
        .limit(1)
    ).first()


def candidate_input_for(session: Session, vendor: Vendor) -> CandidateInput:
    """One vendor as the engine needs it (``vendoriq_scoring.types.CandidateInput``).

    Categories are the vendor's *confirmed* ones only (packages/scoring/README.md §4 rule 1:
    "candidates are vendors whose confirmed categories contain the package category") —
    an unconfirmed self-declared category is the vendor's claim, not yet the officer's.
    """
    application = _best_application(session, vendor.id)
    raw: RawIndicators
    model_version: str
    if application is not None and application.raw_snapshot:
        raw = cast(RawIndicators, dict(application.raw_snapshot))
        cycle = application.cycle
        model_version = (
            cycle.scoring_model_version
            if cycle is not None
            else _DEFAULT_MODEL_VERSION[vendor.type]
        )
    else:
        # Never scored: best-effort raw indicators from the current profile, the same
        # derivation the vendor detail screen shows (routers/vendors.py `_raw_indicators`).
        # The engine still returns a real (low) score for this — an unscored vendor is
        # honestly not eligible, not silently absent from the candidate list.
        profile = observations_service.current_profile(session, vendor.id)
        kind = "sup" if vendor.type is VendorType.SUP else "sub"
        raw = derive_raw(profile, kind)  # type: ignore[arg-type]
        model_version = _DEFAULT_MODEL_VERSION[vendor.type]

    confirmed_codes = [
        row.category.code
        for row in categories_service.list_for_vendor(session, vendor.id)
        if row.confirmed
    ]

    return CandidateInput(
        id=str(vendor.id),
        legal_name=vendor.legal_name,
        vendor_type=vendor.type.value,
        category_codes=confirmed_codes,
        is_prequalified=vendor.status is VendorStatus.PREQUALIFIED,
        raw=raw,
        model_version=model_version,
    )


def build_candidates(session: Session) -> list[CandidateInput]:
    """Every vendor in the register, as a matching candidate.

    Unfiltered by category on purpose: :func:`vendoriq_scoring.match_package` itself narrows
    to the vendors whose categories contain the package's, and keeping the filter there (not
    here) is what lets it report *why* a vendor was not a candidate for a specific package.
    """
    vendors = session.scalars(select(Vendor).order_by(Vendor.legal_name.asc())).all()
    return [candidate_input_for(session, vendor) for vendor in vendors]


def project_input(project: Project) -> ProjectInput:
    """The project's packages as the engine needs them."""
    packages: list[PackageInput] = [
        PackageInput(
            id=str(package.id),
            category_code=package.category.code,
            estimated_value=float(package.estimated_value),
            min_class=package.min_class.value,
            required_certs=list(package.required_certs),
        )
        for package in sorted(project.packages, key=lambda row: row.created_at)
    ]
    return ProjectInput(id=str(project.id), packages=packages)


def run(session: Session, project: Project, params: EngineMatchParams) -> ProjectMatch:
    """Run the engine for one project. Pure with respect to the database — nothing is written."""
    candidates = build_candidates(session)
    return _match_project(project_input(project), candidates, params)


def serialize(result: ProjectMatch) -> dict[str, object]:
    """The engine's dataclasses as the plain JSON ``MatchRun.result`` stores and the contract
    ``MatchRun`` response returns — field names match exactly, so the router can splat this
    straight into the response schema alongside ``id``/``project_id``/``ran_at``/``params``.
    """
    return {
        "state": result.state,
        "coverage_pct": result.coverage_pct,
        "recommendation_key": result.recommendation_key,
        "packages": [
            {
                "package_id": package.package_id,
                "state": package.state,
                "gap": package.gap,
                "missing_certs": package.missing_certs,
                "eligible_count": len(package.eligible),
                "strong_count": len(package.strong),
                "candidates": [
                    {
                        "vendor_id": candidate.vendor_id,
                        "legal_name": candidate.legal_name,
                        "total": candidate.score.total,
                        "cls": candidate.score.cls,
                        "capacity_value": candidate.capacity_value,
                        "capacity_fit": candidate.capacity_fit,
                        "certs_ok": candidate.certs_ok,
                        "eligible": candidate.eligible,
                        "reasons": candidate.reasons,
                        "missing_certs": candidate.missing_certs,
                    }
                    for candidate in package.candidates
                ],
            }
            for package in result.packages
        ],
    }
