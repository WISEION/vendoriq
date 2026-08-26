"""Job registry.

Each entry declares *when* a job runs and *what* it is for; the bodies land in phase 2G.
Jobs share the API's code — they import ``vendoriq_api`` rather than reimplementing rules.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobSpec:
    """One scheduled job. ``cron`` is a 5-field crontab expression, evaluated in UTC."""

    key: str
    cron: str
    description: str
    run: Callable[[], None]


def expiry_reminders() -> None:
    """E-mail vendors about documents expiring in 30 and 7 days (spec §7, brief §2G)."""
    raise NotImplementedError("Implemented in phase 2G")


def stale_profile_scan() -> None:
    """Flag profiles whose newest observation is past its refresh window (spec §6.6)."""
    raise NotImplementedError("Implemented in phase 2G")


def adapter_pulls() -> None:
    """Run the configured ERP / registry adapters and write field observations."""
    raise NotImplementedError("Implemented in phase 2G")


def prequalification_expiry() -> None:
    """Move vendors out of ``prequalified`` when their 12-month validity lapses."""
    raise NotImplementedError("Implemented in phase 2G")


#: The schedule. Times are UTC; Baku is UTC+4, so 05:00 UTC is 09:00 local.
JOBS: tuple[JobSpec, ...] = (
    JobSpec(
        "expiry_reminders",
        "0 5 * * *",
        "Document expiry reminders (30/7 days)",
        expiry_reminders,
    ),
    JobSpec(
        "stale_profile_scan",
        "30 5 * * 1",
        "Weekly stale-profile scan",
        stale_profile_scan,
    ),
    JobSpec(
        "adapter_pulls",
        "0 2 * * 1",
        "Weekly ERP / registry adapter pulls",
        adapter_pulls,
    ),
    JobSpec(
        "prequalification_expiry",
        "0 6 * * *",
        "Expire 12-month prequalifications",
        prequalification_expiry,
    ),
)
