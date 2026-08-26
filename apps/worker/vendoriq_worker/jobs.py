"""Job registry.

Each entry declares *when* a job runs and *what* it is for. Jobs share the API's code — they
import ``vendoriq_api`` rather than reimplementing rules (CONTRIBUTING, "never duplicates
its rules"), which is why the stale-profile scan below is four lines of loop around
``services.observations`` and not its own query.

Phase 1C ships the scheduler and one real body: the stale-profile scan, which reports counts.
The three notifying jobs stay no-ops with a log line until phase 2G gives them e-mail
templates and adapter configuration to work with — a job that silently does nothing is worse
than one that says so on every run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select
from vendoriq_api.catalog import DEFAULT_EXPIRING_WINDOW_DAYS
from vendoriq_api.db import session_scope
from vendoriq_api.models import Vendor
from vendoriq_api.services import documents, observations, settings_store

logger = logging.getLogger("vendoriq.worker")


@dataclass(frozen=True, slots=True)
class JobSpec:
    """One scheduled job. ``cron`` is a 5-field crontab expression, evaluated in UTC."""

    key: str
    cron: str
    description: str
    run: Callable[[], None]


def expiry_reminders() -> None:
    """E-mail vendors about documents expiring in 30 and 7 days (spec §7, brief §2G).

    The *selection* is real already — it is the same query the intelligence screen uses —
    but nothing is sent: the AZ/EN templates are phase 2G. The count is logged so that the
    absence of e-mail is visible rather than assumed.
    """
    with session_scope() as session:
        window = int(
            settings_store.group(session, "notifications").get(
                "expiring_window_days", DEFAULT_EXPIRING_WINDOW_DAYS
            )
        )
        due = documents.expiring(session, within_days=window)
    logger.info(
        "expiry_reminders: %d document(s) expiring within %d days; delivery lands in phase 2G",
        len(due),
        window,
    )


def stale_profile_scan() -> None:
    """Count profiles whose newest observation is past its refresh window (spec §6.6).

    This is what makes the market-intelligence screens honest about their own accuracy: the
    stale count sits beside the numbers it qualifies. The scan writes nothing — it reports.
    """
    with session_scope() as session:
        windows = settings_store.freshness_windows(session)
        vendors = list(session.scalars(select(Vendor)))
        stale_vendors = 0
        stale_fields = 0
        for vendor in vendors:
            codes = observations.stale_field_codes(session, vendor.id, windows=windows)
            if codes:
                stale_vendors += 1
                stale_fields += len(codes)
                logger.debug("stale profile %s: %s", vendor.legal_name, ", ".join(codes))
    logger.info(
        "stale_profile_scan: %d/%d vendor(s) stale, %d field(s) past their window %s",
        stale_vendors,
        len(vendors),
        stale_fields,
        windows,
    )


def adapter_pulls() -> None:
    """Run the configured ERP / registry adapters and write field observations.

    The adapter interface and its implementations are phase 2E; there is nothing to call
    yet, so the job logs that it ran and did nothing.
    """
    logger.info("adapter_pulls: no adapters registered; the adapter layer lands in phase 2E")


def prequalification_expiry() -> None:
    """Move vendors out of ``prequalified`` when their 12-month validity lapses (spec §9).

    Needs the decision records phase 2B writes; until then there is nothing to expire.
    """
    logger.info("prequalification_expiry: no decided applications yet; lands in phase 2B")


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

JOBS_BY_KEY: dict[str, JobSpec] = {job.key: job for job in JOBS}
