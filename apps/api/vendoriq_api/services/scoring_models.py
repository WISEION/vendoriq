"""Scoring model versions and the editor (contract tag ``scoring-models``, spec §10.3).

**ADR-017 is binding here.** ``is_locked`` freezes a model's *definition* — editing it
(:func:`patch_draft`) is refused once it is set. It says nothing about whether the version may
still score applications; that is ``status = retired``, enforced in ``services/evaluation.py``
(task 2B), not here. The two are orthogonal by design (ADR-014): a version can be locked and
active, locked and retired, or — briefly, as a draft — neither.

Every mutation here writes an audit event with ``entity_id=None`` (like
``services/settings_store.py``): ``scoring_model``'s primary key is the version string, not a
UUID, so the version travels in the event's ``before``/``after`` payload instead of the
``entity_id`` column ``audit.record`` expects.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from vendoriq_scoring import derive_raw
from vendoriq_scoring import score as engine_score
from vendoriq_scoring.types import ClassBand as EngineClassBand
from vendoriq_scoring.types import Criterion as EngineCriterion
from vendoriq_scoring.types import GroupDef as EngineGroupDef
from vendoriq_scoring.types import ModelStatusName, RawIndicators
from vendoriq_scoring.types import ScoringModel as EngineScoringModel

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Application, QualificationCycle, Vendor
from ..models import ScoringModel as ScoringModelRow
from ..models.enums import ScoringModelStatus, VendorType
from . import audit
from . import observations as observations_service

__all__ = [
    "application_count",
    "create_draft",
    "get",
    "list_models",
    "patch_draft",
    "publish",
    "summary_payload",
    "test_rescore",
    "total_max",
]


def get(session: Session, version: str) -> ScoringModelRow:
    row = session.get(ScoringModelRow, version)
    if row is None:
        raise ApiError(
            404, "not_found", f"No such scoring model version {version!r}.", {"version": version}
        )
    return row


def list_models(session: Session, vendor_type: VendorType | None = None) -> list[ScoringModelRow]:
    """Every version, newest first (contract: ``listScoringModels``)."""
    query = select(ScoringModelRow)
    if vendor_type is not None:
        query = query.where(ScoringModelRow.vendor_type == vendor_type)
    query = query.order_by(ScoringModelRow.created_at.desc(), ScoringModelRow.version.desc())
    return list(session.scalars(query))


def total_max(row: ScoringModelRow) -> float:
    """The sum of the criteria maxima — deliberately not a column (ADR-014)."""
    return sum(float(criterion["max"]) for criterion in row.criteria)


def application_count(session: Session, version: str) -> int:
    """How many applications were scored with this version — every cycle that names it."""
    return (
        session.scalar(
            select(func.count())
            .select_from(Application)
            .join(QualificationCycle, QualificationCycle.id == Application.cycle_id)
            .where(QualificationCycle.scoring_model_version == version)
        )
        or 0
    )


def summary_payload(session: Session, row: ScoringModelRow) -> dict[str, Any]:
    return {
        "version": row.version,
        "vendor_type": row.vendor_type,
        "name_az": row.name_az,
        "name_en": row.name_en,
        "status": row.status.value,
        "pass_mark": float(row.pass_mark),
        "validity_months": row.validity_months,
        "effective_from": row.effective_from,
        "is_locked": row.is_locked,
        "application_count": application_count(session, row.version),
    }


def full_payload(session: Session, row: ScoringModelRow) -> dict[str, Any]:
    return {
        **summary_payload(session, row),
        "currency": "AZN",
        "total_max": total_max(row),
        "groups": list(row.groups),
        "criteria": list(row.criteria),
        "classes": list(row.classes),
    }


# ── draft creation & editing ────────────────────────────────────────────────
def create_draft(
    uow: UnitOfWork,
    *,
    from_version: str,
    version: str,
    name_az: str | None = None,
    name_en: str | None = None,
    note: str | None = None,
) -> ScoringModelRow:
    """Copy ``from_version`` into a new, unlocked draft (contract: ``createScoringModelDraft``).

    Never mutates the source: spec §10.3 says a version is immutable once used, so the only
    way to change a weight is a new row. The draft starts ``status = draft`` and
    ``is_locked = False`` — nothing has been scored with it yet.
    """
    session = uow.session
    source = get(session, from_version)
    version = version.strip()
    if not version:
        raise ApiError(422, "validation_error", "The new version id must not be blank.")
    if session.get(ScoringModelRow, version) is not None:
        raise ApiError(
            409, "conflict", f"Version {version!r} already exists.", {"version": version}
        )

    draft = ScoringModelRow(
        version=version,
        vendor_type=source.vendor_type,
        name_az=name_az or source.name_az,
        name_en=name_en or source.name_en,
        status=ScoringModelStatus.DRAFT,
        groups=[dict(group) for group in source.groups],
        criteria=[dict(criterion) for criterion in source.criteria],
        classes=[dict(band) for band in source.classes],
        pass_mark=source.pass_mark,
        validity_months=source.validity_months,
        is_locked=False,
        notes={"based_on": from_version, "note": note} if note else {"based_on": from_version},
    )
    session.add(draft)
    uow.flush()
    audit.record(
        uow,
        entity_type="scoring_model",
        entity_id=None,
        action="create_draft",
        after={"version": version, "based_on": from_version, "note": note},
    )
    return draft


_PATCHABLE_FIELDS = ("name_az", "name_en", "pass_mark", "validity_months", "criteria", "classes")


def patch_draft(uow: UnitOfWork, row: ScoringModelRow, changes: dict[str, Any]) -> ScoringModelRow:
    """Edit an unlocked draft (contract: ``patchScoringModelDraft``).

    **ADR-017**: refused with 409 whenever ``is_locked`` is true, regardless of ``status`` —
    that is exactly where spec §10.3's immutability bites. A locked model that is also
    ``proposed`` or ``active`` is still refused here; create a new draft instead.
    """
    if row.is_locked:
        raise ApiError(
            409,
            "conflict",
            "This version has been scored with at least one application and its definition "
            "is now immutable (spec §10.3) — create a new draft to change it.",
            {"version": row.version, "is_locked": True},
        )

    before = audit.snapshot(row, _PATCHABLE_FIELDS)
    for field in _PATCHABLE_FIELDS:
        value = changes.get(field)
        if value is None:
            continue
        if field in ("criteria", "classes"):
            setattr(row, field, [dict(item) for item in value])
        else:
            setattr(row, field, value)
    uow.flush()
    after = audit.snapshot(row, _PATCHABLE_FIELDS)
    audit.record(
        uow,
        entity_type="scoring_model",
        entity_id=None,
        action="patch_draft",
        before={key: before[key] for key in audit.diff(before, after)},
        after=audit.diff(before, after),
    )
    return row


# ── publishing ───────────────────────────────────────────────────────────────
_PUBLISHABLE_STATUSES = frozenset({ScoringModelStatus.DRAFT, ScoringModelStatus.PROPOSED})


def publish(
    uow: UnitOfWork, row: ScoringModelRow, effective_from: _dt.date | None = None
) -> ScoringModelRow:
    """Move a draft (or a proposed version) to ``active`` (contract: ``publishScoringModel``)."""
    if row.status not in _PUBLISHABLE_STATUSES:
        raise ApiError(
            409,
            "conflict",
            f"Only a draft or proposed version can be published; {row.version!r} is "
            f"{row.status.value!r}.",
            {"version": row.version, "status": row.status.value},
        )
    before_status = row.status.value
    before_effective_from = row.effective_from
    row.status = ScoringModelStatus.ACTIVE
    row.effective_from = effective_from or _dt.date.today()
    uow.flush()
    audit.record(
        uow,
        entity_type="scoring_model",
        entity_id=None,
        action="publish",
        before={
            "version": row.version,
            "status": before_status,
            "effective_from": before_effective_from.isoformat() if before_effective_from else None,
        },
        after={
            "version": row.version,
            "status": row.status.value,
            "effective_from": row.effective_from.isoformat(),
        },
    )
    return row


# ── test re-score ────────────────────────────────────────────────────────────
def _to_engine_model(row: ScoringModelRow) -> EngineScoringModel:
    """The same construction ``services/evaluation.py``'s ``_engine_model`` does, kept local
    rather than imported: that function is private to task 2B's module, and the shape here is
    a dozen lines built straight off the row's own columns, not a second scoring rule."""
    criteria = cast(list[EngineCriterion], row.criteria)
    return EngineScoringModel(
        version=row.version,
        vendor_type=row.vendor_type.value,
        name_az=row.name_az,
        name_en=row.name_en,
        status=cast(ModelStatusName, row.status.value),
        pass_mark=float(row.pass_mark),
        validity_months=row.validity_months,
        currency="AZN",
        total_max=sum(float(criterion["max"]) for criterion in criteria),
        groups=cast(list[EngineGroupDef], row.groups),
        criteria=criteria,
        classes=cast(list[EngineClassBand], row.classes),
        source=f"scoring_model:{row.version}",
    )


def _application_raw(
    session: Session, application: Application, vendor: Vendor, criteria: list[EngineCriterion]
) -> RawIndicators:
    """Raw indicators for one model's criteria, from this application's own record.

    Mirrors ``services/evaluation.py``'s ``_base_raw``/``_scoring_raw`` precedence: the
    frozen snapshot (or, absent one, the current profile through ``derive_raw``) for numeric
    criteria, the officer's rubric cell — when one was entered — for rubric criteria. Testing
    a candidate version must compare like with like: the same evidence the officer actually
    recorded, scored twice.
    """
    if application.raw_snapshot is not None:
        base: dict[str, Any] = dict(application.raw_snapshot)
    else:
        profile = observations_service.current_profile(session, vendor.id)
        kind = "sup" if vendor.type is VendorType.SUP else "sub"
        base = dict(derive_raw(profile, kind))  # type: ignore[arg-type]
    rubric = dict(application.rubric_scores or {})

    raw: dict[str, float | int | None] = {}
    for criterion in criteria:
        code = criterion["code"]
        if criterion["kind"] == "rubric" and code in rubric:
            raw[code] = rubric[code]
        else:
            raw[code] = base.get(code)
    return raw


def test_rescore(
    session: Session, candidate: ScoringModelRow, cycle_id: uuid.UUID
) -> dict[str, Any]:
    """Re-score every application of a cycle against ``candidate`` — nothing is written.

    Both the "before" and the "after" number are computed fresh, from the same raw evidence,
    with the cycle's own model and with ``candidate`` respectively: "what would this change
    have done?" compares two scores of the same facts, not a stored score against a new one
    that might also have drifted from a profile edited since the decision.
    """
    cycle = session.get(QualificationCycle, cycle_id)
    if cycle is None:
        raise ApiError(
            404, "not_found", "No such qualification cycle.", {"cycle_id": str(cycle_id)}
        )

    from_row = get(session, cycle.scoring_model_version)
    from_model = _to_engine_model(from_row)
    to_model = _to_engine_model(candidate)

    applications = list(
        session.scalars(
            select(Application)
            .where(Application.cycle_id == cycle_id)
            .order_by(Application.created_at.asc())
        )
    )

    rows: list[dict[str, Any]] = []
    changed_count = 0
    class_changes = 0
    for application in applications:
        vendor = session.get(Vendor, application.vendor_id)
        if vendor is None:  # pragma: no cover - FK guarantees this in practice
            continue
        raw_from = _application_raw(session, application, vendor, from_model.criteria)
        raw_to = _application_raw(session, application, vendor, to_model.criteria)
        old = engine_score(from_model, raw_from)
        new = engine_score(to_model, raw_to)
        changed = old.total != new.total or old.cls != new.cls
        if changed:
            changed_count += 1
            if old.cls != new.cls:
                class_changes += 1
        rows.append(
            {
                "vendor_id": application.vendor_id,
                "vendor_name": vendor.legal_name,
                "old_total": old.total,
                "new_total": new.total,
                "old_class": old.cls,
                "new_class": new.cls,
                "changed": changed,
            }
        )

    return {
        "cycle_id": cycle_id,
        "from_version": from_row.version,
        "to_version": candidate.version,
        "rows": rows,
        "summary": {"changed_count": changed_count, "class_changes": class_changes},
    }
