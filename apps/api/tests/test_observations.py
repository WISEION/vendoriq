"""The current-value resolver (ADR-004, spec §6.6).

The precedence rule is the single most load-bearing piece of the data model: it decides what
"the vendor's turnover" *is*, and every screen, the scoring engine and the matching engine
read the answer. These tests pin it from both ends — the Python trust table and the
database's generated column must agree, and the tie-breaks must be deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models.enums import SOURCE_TRUST_RANK, ObservationSource
from vendoriq_api.services import observations

SOURCES = list(ObservationSource)


def _at(days_ago: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days_ago)


def test_trust_ranks_match_the_spec_table() -> None:
    """Spec §6.6: registry 1, api 2, document 3, portal/excel 4, manual 5."""
    assert SOURCE_TRUST_RANK == {
        ObservationSource.REGISTRY: 1,
        ObservationSource.API: 2,
        ObservationSource.DOCUMENT: 3,
        ObservationSource.PORTAL: 4,
        ObservationSource.EXCEL: 4,
        ObservationSource.MANUAL: 5,
    }


@pytest.mark.parametrize("source", SOURCES)
def test_the_database_computes_the_same_rank_as_python(
    uow: UnitOfWork, make_vendor: Any, source: ObservationSource
) -> None:
    """The generated column and ``enums.SOURCE_TRUST_RANK`` are two copies of one rule."""
    vendor = make_vendor()
    row = observations.record(uow, vendor.id, "B.1", 1, source=source)
    uow.session.refresh(row)
    assert row.trust_rank == SOURCE_TRUST_RANK[source]


def test_a_better_source_wins_even_when_it_is_older(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    """This is the whole point of the rank: recency does not beat trust."""
    vendor = make_vendor()
    observations.record(
        uow, vendor.id, "B.1", 999, source=ObservationSource.MANUAL, observed_at=_at(0)
    )
    observations.record(
        uow, vendor.id, "B.1", 111, source=ObservationSource.REGISTRY, observed_at=_at(400)
    )
    assert observations.current_profile(session, vendor.id)["B.1"] == 111


def test_within_one_rank_the_newest_observation_wins(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    """``portal`` and ``excel`` share rank 4, so the tie is broken by ``observed_at``."""
    vendor = make_vendor()
    observations.record(
        uow, vendor.id, "E.1", 40, source=ObservationSource.PORTAL, observed_at=_at(10)
    )
    observations.record(
        uow, vendor.id, "E.1", 80, source=ObservationSource.EXCEL, observed_at=_at(1)
    )
    assert observations.current_profile(session, vendor.id)["E.1"] == 80


def test_the_full_precedence_order_holds_as_observations_arrive(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    """Add sources worst-first; the current value must improve at every better rank."""
    vendor = make_vendor()
    worst_first = [
        (ObservationSource.MANUAL, 5),
        (ObservationSource.EXCEL, 4),
        (ObservationSource.PORTAL, 4),
        (ObservationSource.DOCUMENT, 3),
        (ObservationSource.API, 2),
        (ObservationSource.REGISTRY, 1),
    ]
    best_rank = 99
    for index, (source, rank) in enumerate(worst_first):
        observations.record(
            uow, vendor.id, "C.2", index, source=source, observed_at=_at(len(worst_first) - index)
        )
        current = observations.current_profile(session, vendor.id)["C.2"]
        if rank < best_rank:
            best_rank = rank
            assert current == index, f"{source} (rank {rank}) should have taken over"
        else:
            # Same rank as the incumbent, but newer — it wins on recency.
            assert current == index


def test_scalars_are_wrapped_and_tables_are_not(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    """ADR-004: ``{"value": …}`` for scalars, a bare array for a table such as ``C.t1``."""
    vendor = make_vendor()
    table = [{"name": "Tower A", "value": 4_500_000}, {"name": "Tower B", "value": 900_000}]
    scalar = observations.record(uow, vendor.id, "B.5", 1_208_443, source=ObservationSource.PORTAL)
    rows = observations.record(uow, vendor.id, "C.t1", table, source=ObservationSource.PORTAL)
    assert scalar.value == {"value": 1_208_443}
    assert observations.unwrap(rows.value) == table
    profile = observations.current_profile(session, vendor.id)
    assert profile["B.5"] == 1_208_443
    assert profile["C.t1"] == table


def test_observations_are_append_only(uow: UnitOfWork, make_vendor: Any, session: Session) -> None:
    """A correction adds a row; the superseded value is still there to be shown."""
    vendor = make_vendor()
    observations.record(uow, vendor.id, "E.1", 40, source=ObservationSource.PORTAL)
    observations.record(uow, vendor.id, "E.1", 80, source=ObservationSource.PORTAL)
    history, total = observations.history(session, vendor.id, field_codes=["E.1"])
    assert total == 2
    assert [observations.unwrap(row.value) for row in history] == [80, 40]


def test_current_profile_returns_one_row_per_field_code(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    vendor = make_vendor()
    observations.record_many(
        uow,
        vendor.id,
        {"A.1": "Wesa", "B.1": 5_189_111, "E.1": 80},
        source=ObservationSource.EXCEL,
    )
    observations.record(uow, vendor.id, "B.1", 6_000_000, source=ObservationSource.API)
    profile = observations.current_profile(session, vendor.id)
    assert set(profile) == {"A.1", "B.1", "E.1"}
    assert profile["B.1"] == 6_000_000


def test_value_of_and_current_sources_agree_with_the_profile(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    vendor = make_vendor()
    observations.record(uow, vendor.id, "B.1", 10, source=ObservationSource.PORTAL)
    observations.record(uow, vendor.id, "B.1", 20, source=ObservationSource.REGISTRY)
    assert observations.value_of(session, vendor.id, "B.1") == 20
    assert observations.current_sources(session, vendor.id)["B.1"] is ObservationSource.REGISTRY
    assert observations.value_of(session, vendor.id, "Z.9") is None


def test_stale_fields_use_the_configured_window(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    """Spec §6.6: financials 15 months, headcount 12. Fresh values are not reported."""
    vendor = make_vendor()
    observations.record(
        uow, vendor.id, "B.1", 1, source=ObservationSource.PORTAL, observed_at=_at(500)
    )
    observations.record(
        uow, vendor.id, "E.1", 2, source=ObservationSource.PORTAL, observed_at=_at(10)
    )
    stale = observations.stale_field_codes(session, vendor.id, windows={"B": 456, "E": 365})
    assert stale == ["B.1"]


def test_isolation_between_vendors(uow: UnitOfWork, make_vendor: Any, session: Session) -> None:
    """A resolver bug that leaks across vendors would silently merge two registers."""
    one, other = make_vendor(), make_vendor()
    observations.record(uow, one.id, "B.1", 1, source=ObservationSource.PORTAL)
    observations.record(uow, other.id, "B.1", 2, source=ObservationSource.PORTAL)
    assert observations.current_profile(session, one.id) == {"B.1": 1}
    assert observations.current_profile(session, other.id) == {"B.1": 2}
