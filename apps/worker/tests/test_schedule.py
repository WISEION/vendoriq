"""The job registry is part of the runbook — assert it stays well formed."""

from __future__ import annotations

from vendoriq_worker.jobs import JOBS


def test_job_keys_are_unique() -> None:
    keys = [job.key for job in JOBS]
    assert len(keys) == len(set(keys))


def test_every_job_has_a_five_field_cron_and_a_description() -> None:
    for job in JOBS:
        assert len(job.cron.split()) == 5, job.key
        assert job.description.strip(), job.key
        assert callable(job.run), job.key
