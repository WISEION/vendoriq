"""``expiry_reminders``: exact 30/7-day boundaries, once-only, and honest reporting.

The boundary tests pin a document's expiry date relative to a fixed "today" (a fake clock —
never ``sleep``) and check the exact day, not a range: 29/31 and 6/8 must send nothing, only
30 and 7 must.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import Event
from vendoriq_api.models.enums import EventType
from vendoriq_api.services import settings_store
from vendoriq_worker import jobs

TODAY = date(2026, 8, 26)


def _expiring_document(make_vendor: Any, make_contact: Any, make_document: Any, days: int) -> Any:
    vendor = make_vendor()
    make_contact(vendor)
    return make_document(vendor, code="A-05", expiry_date=TODAY + timedelta(days=days))


@pytest.mark.parametrize("days,should_send", [(29, False), (30, True), (31, False)])
def test_the_30_day_boundary_is_exact(
    days: int,
    should_send: bool,
    make_vendor: Any,
    make_contact: Any,
    make_document: Any,
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _expiring_document(make_vendor, make_contact, make_document, days)
    with caplog.at_level("INFO", logger="vendoriq.worker"):
        jobs.expiry_reminders(today=TODAY)
    events = list(
        session.scalars(select(Event).where(Event.type == EventType.DOCUMENT_EXPIRING.value))
    )
    assert bool(events) is should_send, f"{days} days out: expected sent={should_send}"


@pytest.mark.parametrize("days,should_send", [(6, False), (7, True), (8, False)])
def test_the_7_day_boundary_is_exact(
    days: int,
    should_send: bool,
    make_vendor: Any,
    make_contact: Any,
    make_document: Any,
    session: Session,
) -> None:
    _expiring_document(make_vendor, make_contact, make_document, days)
    jobs.expiry_reminders(today=TODAY)
    events = list(
        session.scalars(select(Event).where(Event.type == EventType.DOCUMENT_EXPIRING.value))
    )
    assert bool(events) is should_send, f"{days} days out: expected sent={should_send}"


def test_a_second_run_the_same_day_sends_nothing_new(
    make_vendor: Any, make_contact: Any, make_document: Any, session: Session
) -> None:
    _expiring_document(make_vendor, make_contact, make_document, 30)
    jobs.expiry_reminders(today=TODAY)
    jobs.expiry_reminders(today=TODAY)  # safe to run twice in a day
    events = list(
        session.scalars(select(Event).where(Event.type == EventType.DOCUMENT_EXPIRING.value))
    )
    assert len(events) == 1


def test_both_the_30_and_7_day_reminders_fire_for_the_same_document_over_time(
    make_vendor: Any, make_contact: Any, make_document: Any, session: Session
) -> None:
    vendor = make_vendor()
    make_contact(vendor)
    document = make_document(vendor, code="A-05", expiry_date=TODAY + timedelta(days=30))
    jobs.expiry_reminders(today=TODAY)
    # Three weeks later the same document is now 7 days from expiring.
    jobs.expiry_reminders(today=TODAY + timedelta(days=23))
    events = list(
        session.scalars(
            select(Event).where(
                Event.type == EventType.DOCUMENT_EXPIRING.value, Event.entity_id == document.id
            )
        )
    )
    assert {event.payload["window_days"] for event in events} == {30, 7}


def test_a_document_that_never_expires_is_not_reminded_about(
    make_vendor: Any, make_contact: Any, make_document: Any, session: Session
) -> None:
    """ "Müddətsiz" (brief §1.11) — no expiry, so no invented date to remind about."""
    vendor = make_vendor()
    make_contact(vendor)
    make_document(vendor, code="A-05", expiry_date=None)
    jobs.expiry_reminders(today=TODAY)
    events = list(
        session.scalars(select(Event).where(Event.type == EventType.DOCUMENT_EXPIRING.value))
    )
    assert events == []


def test_the_job_reports_what_it_found_even_when_nothing_is_due(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO", logger="vendoriq.worker"):
        jobs.expiry_reminders(today=TODAY)
    message = " ".join(record.getMessage() for record in caplog.records)
    assert "expiry_reminders" in message
    assert "nothing due" in message or "0 due" in message


def test_disabling_notifications_is_reported_not_silent(
    make_vendor: Any,
    make_contact: Any,
    make_document: Any,
    session: Session,
    caplog: pytest.LogCaptureFixture,
) -> None:
    _expiring_document(make_vendor, make_contact, make_document, 30)
    settings_store.update(UnitOfWork(session), {"notifications": {"email_enabled": False}})
    session.commit()
    with caplog.at_level("INFO", logger="vendoriq.worker"):
        jobs.expiry_reminders(today=TODAY)
    message = " ".join(record.getMessage() for record in caplog.records)
    assert "email_enabled is False" in message
    events = list(
        session.scalars(select(Event).where(Event.type == EventType.DOCUMENT_EXPIRING.value))
    )
    assert events == []
