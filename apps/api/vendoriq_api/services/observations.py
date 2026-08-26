"""Field observations: append-only writes and the current-value resolver (spec §4, §6.6).

There is no ``vendor.turnover`` column (ADR-004). The current value of a field is the
observation with the best trust rank and, within that rank, the newest ``observed_at``.
Trust ranks come from spec §6.6 — registry 1, api 2, document 3, portal/excel 4, manual 5 —
and are computed by the database in a generated column, so the ordering cannot drift between
the resolver and anything else that queries the table.

The tie inside a rank is broken by ``observed_at`` and then by ``created_at``: two rows with
the same observed instant (an import writing a whole form at once) must still resolve
deterministically, or the same request answers differently on two reads.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from ..db import UnitOfWork
from ..models import FieldObservation
from ..models.enums import SOURCE_TRUST_RANK, ObservationSource
from . import audit

#: Order that decides the winner: best trust first, then newest, then newest row.
_RESOLUTION_ORDER = (
    FieldObservation.trust_rank.asc(),
    FieldObservation.observed_at.desc(),
    FieldObservation.created_at.desc(),
    FieldObservation.id.desc(),
)


def trust_rank(source: ObservationSource) -> int:
    """The Python mirror of the generated column. Both must agree (ADR-004)."""
    return SOURCE_TRUST_RANK[source]


def wrap(value: Any) -> Any:
    """Scalars are stored as ``{"value": …}``; tables stay JSON arrays (ADR-004).

    Wrapping keeps one JSONB column able to hold a number, a Yes/No answer and the C.t1
    project table without a discriminator column or a type-per-table schema.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and "value" in value:
        return value
    return {"value": value}


def unwrap(stored: Any) -> Any:
    """Inverse of :func:`wrap`. A table comes back as the list it went in as."""
    if isinstance(stored, dict) and set(stored) == {"value"}:
        return stored["value"]
    return stored


def current_observations_query(vendor_id: uuid.UUID) -> Select[tuple[FieldObservation]]:
    """One winning row per field code, as a subquery-free window query.

    ``ROW_NUMBER`` over the resolution order beats ``DISTINCT ON`` here only in that it is
    portable; the index ``ix_field_observation_current`` covers both.
    """
    ranked = (
        select(
            FieldObservation,
            func.row_number()
            .over(partition_by=FieldObservation.field_code, order_by=_RESOLUTION_ORDER)
            .label("rn"),
        )
        .where(FieldObservation.vendor_id == vendor_id)
        .subquery()
    )
    entity = ranked.c
    return (
        select(FieldObservation)
        .join(ranked, FieldObservation.id == entity.id)
        .where(entity.rn == 1)
        .order_by(FieldObservation.field_code)
    )


def current_observations(session: Session, vendor_id: uuid.UUID) -> list[FieldObservation]:
    """The winning observation per field code, ordered by field code."""
    return list(session.scalars(current_observations_query(vendor_id)))


def current_profile(session: Session, vendor_id: uuid.UUID) -> dict[str, Any]:
    """``{field_code: value}`` — the vendor's current profile, unwrapped.

    This is the function the evaluation screen, the matching engine and the Excel import
    preview all call; nothing else is allowed to decide what "the current value" means.
    """
    return {
        observation.field_code: unwrap(observation.value)
        for observation in current_observations(session, vendor_id)
    }


def current_sources(session: Session, vendor_id: uuid.UUID) -> dict[str, ObservationSource]:
    """Where each current value came from — the provenance column of the vendor screen."""
    return {
        observation.field_code: observation.source
        for observation in current_observations(session, vendor_id)
    }


def current_ids(session: Session, vendor_id: uuid.UUID) -> set[uuid.UUID]:
    """Ids of the winning observations; used to stamp ``is_current`` on a history page."""
    return {observation.id for observation in current_observations(session, vendor_id)}


def value_of(session: Session, vendor_id: uuid.UUID, field_code: str) -> Any:
    """Current value of one field, or ``None`` when the vendor has never reported it."""
    observation = session.scalars(
        select(FieldObservation)
        .where(
            FieldObservation.vendor_id == vendor_id,
            FieldObservation.field_code == field_code,
        )
        .order_by(*_RESOLUTION_ORDER)
        .limit(1)
    ).first()
    return None if observation is None else unwrap(observation.value)


def latest_observed_at(session: Session, vendor_id: uuid.UUID) -> datetime | None:
    """Newest observation of any field — the "last updated" column of the register."""
    return session.scalar(
        select(func.max(FieldObservation.observed_at)).where(
            FieldObservation.vendor_id == vendor_id
        )
    )


def record(
    uow: UnitOfWork,
    vendor_id: uuid.UUID,
    field_code: str,
    value: Any,
    *,
    source: ObservationSource,
    unit: str | None = None,
    source_ref: str | None = None,
    observed_at: datetime | None = None,
    entered_by: uuid.UUID | None = None,
    reason: str | None = None,
    write_audit: bool = True,
) -> FieldObservation:
    """Append one observation. Never updates: the history is the point (ADR-004)."""
    observation = FieldObservation(
        vendor_id=vendor_id,
        field_code=field_code,
        value=wrap(value),
        unit=unit,
        source=source,
        source_ref=source_ref,
        observed_at=observed_at or datetime.now(UTC),
        entered_by=entered_by if entered_by is not None else uow.actor_id,
    )
    uow.session.add(observation)
    uow.flush()
    if write_audit:
        audit.record(
            uow,
            entity_type="field_observation",
            entity_id=observation.id,
            action="create",
            after={
                "vendor_id": vendor_id,
                "field_code": field_code,
                "value": observation.value,
                "source": source,
                "reason": reason,
            },
        )
    return observation


def record_many(
    uow: UnitOfWork,
    vendor_id: uuid.UUID,
    values: dict[str, Any],
    *,
    source: ObservationSource,
    source_ref: str | None = None,
    observed_at: datetime | None = None,
    reason: str | None = None,
) -> list[FieldObservation]:
    """Write a whole form's worth of answers with one ``observed_at``.

    Sharing the instant is what makes them a single act rather than a race; the resolution
    order's ``created_at``/``id`` tiebreak keeps the result deterministic anyway.
    """
    moment = observed_at or datetime.now(UTC)
    return [
        record(
            uow,
            vendor_id,
            field_code,
            value,
            source=source,
            source_ref=source_ref,
            observed_at=moment,
            reason=reason,
            write_audit=False,
        )
        for field_code, value in values.items()
    ]


def history(
    session: Session,
    vendor_id: uuid.UUID,
    *,
    field_codes: Sequence[str] | None = None,
    sources: Iterable[ObservationSource] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[FieldObservation], int]:
    """Newest first, optionally filtered — the provenance tab of the vendor screen."""
    query = select(FieldObservation).where(FieldObservation.vendor_id == vendor_id)
    count_query = (
        select(func.count())
        .select_from(FieldObservation)
        .where(FieldObservation.vendor_id == vendor_id)
    )
    if field_codes:
        query = query.where(FieldObservation.field_code.in_(list(field_codes)))
        count_query = count_query.where(FieldObservation.field_code.in_(list(field_codes)))
    if sources:
        source_list = list(sources)
        query = query.where(FieldObservation.source.in_(source_list))
        count_query = count_query.where(FieldObservation.source.in_(source_list))
    total = session.scalar(count_query) or 0
    query = query.order_by(FieldObservation.observed_at.desc(), FieldObservation.id.desc())
    if limit is not None:
        query = query.limit(limit).offset(offset)
    return list(session.scalars(query)), total


def stale_field_codes(
    session: Session,
    vendor_id: uuid.UUID,
    *,
    windows: dict[str, int],
    now: datetime | None = None,
) -> list[str]:
    """Field codes whose newest observation is older than its refresh window (spec §6.6).

    ``windows`` maps a field-code prefix (``"B"``, ``"E"``) to a number of days, so the
    caller expresses "financials 15 months, headcount 12" without this function knowing what
    a financial is.
    """
    moment = now or datetime.now(UTC)
    stale: list[str] = []
    for observation in current_observations(session, vendor_id):
        prefix = observation.field_code.split(".", 1)[0]
        window_days = windows.get(prefix)
        if window_days is None:
            continue
        observed = observation.observed_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        if (moment - observed).days > window_days:
            stale.append(observation.field_code)
    return sorted(stale)
