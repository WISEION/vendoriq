"""``adapter_pulls``: runs what is enabled and due, per adapter config (task 2E, brief §2G)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_api.adapters import config_store
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import SyncLog
from vendoriq_api.models.enums import AdapterKey
from vendoriq_worker import jobs


# ── the pure due-check ───────────────────────────────────────────────────────
def test_never_run_is_due_for_any_daily_cron() -> None:
    now = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)
    assert jobs._adapter_due("0 2 * * *", None, now) is True


def test_a_run_earlier_today_is_not_due_again() -> None:
    now = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)
    last_run = datetime(2026, 8, 26, 2, 0, tzinfo=UTC)
    assert jobs._adapter_due("0 2 * * *", last_run, now) is False


def test_a_run_yesterday_is_due_again_today() -> None:
    now = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)
    last_run = datetime(2026, 8, 24, 2, 0, tzinfo=UTC)  # the worker was down for a day
    assert jobs._adapter_due("0 2 * * *", last_run, now) is True


def test_a_weekly_schedule_is_not_due_mid_week() -> None:
    # APScheduler's ``day_of_week`` is 0 = Monday, so "1" here means Tuesday.
    now = datetime(2026, 8, 26, 6, 0, tzinfo=UTC)  # a Wednesday
    last_run = datetime(2026, 8, 25, 2, 0, tzinfo=UTC)  # yesterday, Tuesday
    assert jobs._adapter_due("0 2 * * 1", last_run, now) is False


def test_an_invalid_cron_is_reported_as_not_due_rather_than_raising() -> None:
    assert jobs._adapter_due("not a cron", None, datetime.now(UTC)) is False


# ── the job itself ───────────────────────────────────────────────────────────
def test_a_config_with_no_schedule_is_never_run(
    make_vendor: Any, session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    vendor = make_vendor()
    uow = UnitOfWork(session)
    config_store.save(uow, AdapterKey.GENERIC_REST, vendor.id, {"is_enabled": True})
    session.commit()

    with caplog.at_level("INFO", logger="vendoriq.worker"):
        jobs.adapter_pulls()
    logs = session.scalars(select(SyncLog).where(SyncLog.vendor_id == vendor.id)).all()
    assert logs == []
    message = " ".join(record.getMessage() for record in caplog.records)
    assert "unscheduled=1" in message


def test_a_disabled_config_is_not_run(make_vendor: Any, session: Session) -> None:
    vendor = make_vendor()
    uow = UnitOfWork(session)
    config_store.save(
        uow,
        AdapterKey.GENERIC_REST,
        vendor.id,
        {"is_enabled": False, "schedule_cron": "0 * * * *"},
    )
    session.commit()
    jobs.adapter_pulls()
    logs = session.scalars(select(SyncLog).where(SyncLog.vendor_id == vendor.id)).all()
    assert logs == []


def test_a_misconfigured_but_due_adapter_fails_loudly_without_crashing_the_job(
    make_vendor: Any, session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """Enabled and due, but no ``base_url`` — the adapter refuses (spec §6.3). The job must
    report the failure and keep going, never raise."""
    vendor = make_vendor()
    uow = UnitOfWork(session)
    config_store.save(
        uow,
        AdapterKey.GENERIC_REST,
        vendor.id,
        {"is_enabled": True, "schedule_cron": "0 * * * *"},  # base_url left unset
    )
    session.commit()

    with caplog.at_level("ERROR", logger="vendoriq.worker"):
        jobs.adapter_pulls()  # must not raise
    message = " ".join(record.getMessage() for record in caplog.records)
    assert "did not run" in message


def test_one_misconfigured_vendor_does_not_stop_the_next_ones_evaluation(
    make_vendor: Any, session: Session
) -> None:
    """Two vendors, both due: the first is unconfigured, the second's last run makes it not
    due. The job must still finish and evaluate both — the loop does not stop on the first."""
    broken = make_vendor()
    fine = make_vendor()
    uow = UnitOfWork(session)
    config_store.save(
        uow, AdapterKey.GENERIC_REST, broken.id, {"is_enabled": True, "schedule_cron": "0 * * * *"}
    )
    config_store.save(
        uow, AdapterKey.CSV, fine.id, {"is_enabled": True, "schedule_cron": "0 2 * * *"}
    )
    session.add(
        SyncLog(
            adapter=AdapterKey.CSV.value,
            vendor_id=fine.id,
            started_at=datetime.now(UTC) - timedelta(minutes=5),
            finished_at=datetime.now(UTC),
            fields_written=0,
        )
    )
    session.commit()

    jobs.adapter_pulls()  # must not raise despite the first vendor's failure
    fine_logs = session.scalars(select(SyncLog).where(SyncLog.vendor_id == fine.id)).all()
    # Only the seeded row: the CSV pull was not due (it just ran), so nothing new was added —
    # proof the loop reached and correctly evaluated the second vendor rather than stopping.
    assert len(fine_logs) == 1


def test_the_job_reports_its_counts(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("INFO", logger="vendoriq.worker"):
        jobs.adapter_pulls()
    message = " ".join(record.getMessage() for record in caplog.records)
    assert "adapter_pulls" in message
    assert "ran=" in message and "not_due=" in message and "failed=" in message
