"""The scheduler skeleton (brief §2G, spec §6.6).

Phase 1C shipped the registry, the APScheduler wiring and a working stale-profile scan, with
the other three jobs as deliberate no-ops that logged the phase that would fill them. Phase
2G gives ``expiry_reminders``, ``adapter_pulls`` and ``prequalification_expiry`` real bodies
— see ``test_expiry_reminders.py``, ``test_adapter_pulls.py`` and
``test_prequalification_expiry.py`` for their behaviour. What stays here is the schedule
itself: keys, cron expressions, the scheduler wiring, ``--once`` — the shape that does not
change no matter which job body is behind it.
"""

from __future__ import annotations

import logging

import pytest
from apscheduler.triggers.cron import CronTrigger
from vendoriq_worker import jobs, main


def test_job_keys_are_unique() -> None:
    keys = [job.key for job in jobs.JOBS]
    assert len(keys) == len(set(keys))
    assert set(jobs.JOBS_BY_KEY) == set(keys)


def test_every_job_has_a_five_field_cron_and_a_description() -> None:
    for job in jobs.JOBS:
        assert len(job.cron.split()) == 5, job.key
        assert job.description.strip(), job.key
        assert callable(job.run), job.key


def test_every_cron_expression_actually_parses() -> None:
    """A malformed crontab would only surface when the worker starts in production."""
    for job in jobs.JOBS:
        assert CronTrigger.from_crontab(job.cron, timezone="UTC") is not None


def test_the_registry_covers_the_jobs_the_brief_names() -> None:
    """Brief §2G: expiry reminders, stale-profile scan, adapter schedule."""
    assert {"expiry_reminders", "stale_profile_scan", "adapter_pulls"} <= set(jobs.JOBS_BY_KEY)


def test_the_scheduler_registers_every_job() -> None:
    scheduler = main.build_scheduler()
    try:
        registered = {job.id for job in scheduler.get_jobs()}
        assert registered == {job.key for job in jobs.JOBS}
    finally:
        scheduler.shutdown(wait=False) if scheduler.running else None


def test_the_stale_profile_scan_reports_counts(caplog: pytest.LogCaptureFixture) -> None:
    """The scan is what makes the intelligence honest about its own accuracy (spec §12)."""
    with caplog.at_level(logging.INFO, logger="vendoriq.worker"):
        jobs.stale_profile_scan()
    messages = [record.getMessage() for record in caplog.records]
    assert any("stale_profile_scan" in message for message in messages)
    assert any("vendor(s) stale" in message for message in messages)


def test_run_once_dispatches_a_known_job(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="vendoriq.worker"):
        assert main.run_once("adapter_pulls") == 0


def test_run_once_refuses_an_unknown_job(caplog: pytest.LogCaptureFixture) -> None:
    assert main.run_once("no-such-job") == 2


def test_main_without_a_job_key_after_once_is_an_error() -> None:
    assert main.main(["--once"]) == 2


def test_the_jobs_import_the_api_rather_than_reimplementing_it() -> None:
    """CONTRIBUTING: the worker "imports vendoriq_api, never duplicates its rules".

    The freshness windows, the expiry window and the stale-field rule are all read from
    ``vendoriq_api.services``; the worker contributes the schedule and the log line. What
    it must never contain is a rule of its own — checked here as "no hand-written SQL",
    which is where a duplicated rule would first appear.
    """
    with open(jobs.__file__, encoding="utf-8") as handle:
        text = handle.read()
    assert "from vendoriq_api" in text
    for smell in ("sqlalchemy.text(", 'text("SELECT', "cursor.execute"):
        assert smell not in text, smell
    for service in (
        "observations.stale_field_codes",
        "settings_store.freshness_windows",
        "documents.expiring",
        "notifications.notify_document_expiring",
        "notifications.notify_prequalification_lapsing",
        "run_sync",
    ):
        assert service in text, service


def test_no_job_body_raises(caplog: pytest.LogCaptureFixture) -> None:
    """A scheduled job that raises floods the log with tracebacks — none of them may, even
    against an empty database (nothing configured, nothing due, nothing to warn about)."""
    with caplog.at_level(logging.INFO, logger="vendoriq.worker"):
        for job in jobs.JOBS:
            job.run()


def test_the_schedule_is_documented_in_utc() -> None:
    """Baku is UTC+4; a reader has to be able to tell which clock the crontab is in."""
    with open(jobs.__file__, encoding="utf-8") as handle:
        text = handle.read()
    assert "UTC" in text and "Baku" in text


def test_build_scheduler_uses_utc() -> None:
    scheduler = main.build_scheduler()
    assert str(scheduler.timezone) == "UTC"


def test_job_specs_are_immutable() -> None:
    """The registry is read at start-up and printed in the runbook; it must not be edited."""
    with pytest.raises((AttributeError, TypeError)):
        jobs.JOBS[0].cron = "* * * * *"  # type: ignore[misc]


def test_jobs_by_key_matches_the_tuple() -> None:
    assert all(jobs.JOBS_BY_KEY[job.key] is job for job in jobs.JOBS)
