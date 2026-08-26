"""``prequalification_expiry``: warns before the 12-month validity lapses (spec §9).

Lapse date is calendar months from the real approval decision (``Application.decided_at``),
so each boundary test picks a ``decided_at`` that lands the lapse exactly on the day under
test — the same "pin the boundary, don't sleep" approach as the document-expiry tests.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_api.models import AuditEvent
from vendoriq_api.models.enums import ApplicationStatus, DecisionKind, VendorStatus
from vendoriq_worker import jobs

TODAY = date(2026, 8, 26)
_ACTION = "notification.prequalification_lapsing"


def _decided_at_for_lapse_in(days: int) -> datetime:
    """A ``decided_at`` twelve calendar months before ``TODAY + days`` lapses."""
    lapse = TODAY + timedelta(days=days)
    return datetime(lapse.year - 1, lapse.month, lapse.day, 12, 0, tzinfo=UTC)


def _prequalified_vendor(
    make_vendor: Any, make_contact: Any, make_application: Any, *, days_to_lapse: int
) -> Any:
    vendor = make_vendor(status=VendorStatus.PREQUALIFIED)
    make_contact(vendor)
    make_application(
        vendor,
        status=ApplicationStatus.PREQUALIFIED,
        decision=DecisionKind.APPROVE,
        decided_at=_decided_at_for_lapse_in(days_to_lapse),
    )
    return vendor


def _lapse_markers(session: Session, vendor_id: Any) -> list[AuditEvent]:
    return list(
        session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_type == "vendor",
                AuditEvent.entity_id == vendor_id,
                AuditEvent.action == _ACTION,
            )
        )
    )


@pytest.mark.parametrize("days,should_warn", [(29, False), (30, True), (31, False)])
def test_the_30_day_boundary_is_exact(
    days: int,
    should_warn: bool,
    make_vendor: Any,
    make_contact: Any,
    make_application: Any,
    session: Session,
) -> None:
    vendor = _prequalified_vendor(make_vendor, make_contact, make_application, days_to_lapse=days)
    jobs.prequalification_expiry(today=TODAY)
    assert bool(_lapse_markers(session, vendor.id)) is should_warn


@pytest.mark.parametrize("days,should_warn", [(6, False), (7, True), (8, False)])
def test_the_7_day_boundary_is_exact(
    days: int,
    should_warn: bool,
    make_vendor: Any,
    make_contact: Any,
    make_application: Any,
    session: Session,
) -> None:
    vendor = _prequalified_vendor(make_vendor, make_contact, make_application, days_to_lapse=days)
    jobs.prequalification_expiry(today=TODAY)
    assert bool(_lapse_markers(session, vendor.id)) is should_warn


def test_a_second_run_the_same_day_warns_nothing_new(
    make_vendor: Any, make_contact: Any, make_application: Any, session: Session
) -> None:
    vendor = _prequalified_vendor(make_vendor, make_contact, make_application, days_to_lapse=30)
    jobs.prequalification_expiry(today=TODAY)
    jobs.prequalification_expiry(today=TODAY)
    assert len(_lapse_markers(session, vendor.id)) == 1


def test_a_suspended_vendor_is_not_warned(
    make_vendor: Any, make_contact: Any, make_application: Any, session: Session
) -> None:
    """A manager's suspension overrides the application record (spec §9); the warning
    would be about a status that no longer describes the vendor."""
    vendor = make_vendor(status=VendorStatus.SUSPENDED)
    make_contact(vendor)
    make_application(
        vendor,
        status=ApplicationStatus.PREQUALIFIED,
        decision=DecisionKind.APPROVE,
        decided_at=_decided_at_for_lapse_in(30),
    )
    jobs.prequalification_expiry(today=TODAY)
    assert _lapse_markers(session, vendor.id) == []


def test_an_officer_recorded_validity_override_is_used_over_the_default(
    make_vendor: Any, make_contact: Any, make_application: Any, session: Session
) -> None:
    """``application.declaration["valid_months"]`` (set at approval) beats the org default."""
    vendor = make_vendor(status=VendorStatus.PREQUALIFIED)
    make_contact(vendor)
    # Six-month validity instead of the default twelve: decided six months before TODAY+30
    # lapses under the override, not under the default (which would put it far in the future).
    lapse = TODAY + timedelta(days=30)
    decided_at = datetime(lapse.year, lapse.month - 6, lapse.day, 12, 0, tzinfo=UTC)
    make_application(
        vendor,
        status=ApplicationStatus.PREQUALIFIED,
        decision=DecisionKind.APPROVE,
        decided_at=decided_at,
        declaration={"valid_months": 6},
    )
    jobs.prequalification_expiry(today=TODAY)
    assert len(_lapse_markers(session, vendor.id)) == 1


def test_the_job_reports_what_it_found_even_when_nothing_is_due(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO", logger="vendoriq.worker"):
        jobs.prequalification_expiry(today=TODAY)
    message = " ".join(record.getMessage() for record in caplog.records)
    assert "prequalification_expiry" in message
    assert "nothing due" in message or "0 due" in message
