"""Job registry.

Each entry declares *when* a job runs and *what* it is for. Jobs share the API's code — they
import ``vendoriq_api`` rather than reimplementing rules (CONTRIBUTING, "never duplicates
its rules"): selection queries come from ``services.documents`` / ``services.observations``,
composing and sending mail comes from ``services.notifications``, and adapter execution comes
from ``adapters.runner``. What lives here is the schedule, the "what is due today" arithmetic
against real calendar facts (an expiry date, a decision date), and one honest log line per run
that says what happened — a job that silently does nothing is worse than one that says so.

Phase 2G gives the three previously-deferred jobs real bodies:

* **expiry_reminders** — document expiry reminders at 30 and 7 days (spec §7).
* **adapter_pulls** — runs each enabled, due ``AdapterConfig`` (task 2E's adapter layer).
* **prequalification_expiry** — warns before the 12-month prequalification validity lapses
  (spec §9). It only warns: ``services/state_machine.py`` has no transition out of
  ``prequalified`` — re-qualification is a new application in a new cycle by design — so
  there is no status this job could move a vendor to even if it wanted to.

``stale_profile_scan`` is unchanged from phase 1C; it already does exactly what spec §6.6 and
§12 ask of it.
"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from vendoriq_api.adapters import CONFIGURABLE, AdapterError, config_store
from vendoriq_api.adapters.runner import run_sync
from vendoriq_api.catalog import _add_months as add_calendar_months
from vendoriq_api.config import get_settings
from vendoriq_api.db import UnitOfWork, session_scope
from vendoriq_api.models import Application, SyncLog, Vendor
from vendoriq_api.models.enums import AdapterKey, ApplicationStatus, DecisionKind, VendorStatus
from vendoriq_api.services import documents, notifications, observations, settings_store

logger = logging.getLogger("vendoriq.worker")

#: Earlier than any real ``SyncLog`` row — stands in for "this adapter has never run against
#: this vendor" so the same cron-arithmetic path handles "never run" and "ran a while ago".
_NEVER = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class JobSpec:
    """One scheduled job. ``cron`` is a 5-field crontab expression, evaluated in UTC."""

    key: str
    cron: str
    description: str
    run: Callable[[], None]


def _reminder_windows(session: Session) -> list[int]:
    """``notifications.expiry_reminder_days`` (spec §7: "30 and 7 days") — a setting, not a
    constant (brief §2F), so the commission can change the cadence without a deployment."""
    raw = settings_store.group(session, "notifications").get("expiry_reminder_days", [30, 7])
    windows = sorted({int(value) for value in raw if int(value) > 0}, reverse=True)
    return windows or [30, 7]


def expiry_reminders(*, today: date | None = None) -> None:
    """E-mail vendors about documents expiring in 30 and 7 days (spec §7, brief §2G).

    ``today`` exists for tests — a fake clock, not ``sleep`` — and defaults to the real date
    for the scheduled run. Selection reuses ``services.documents.expiring`` (the same query
    the intelligence screen uses); sending and once-only bookkeeping are
    ``services.notifications.notify_document_expiring``.
    """
    with session_scope() as session:
        settings = get_settings()
        if not settings_store.group(session, "notifications").get("email_enabled", True):
            logger.info("expiry_reminders: notifications.email_enabled is False; skipping")
            return
        windows = _reminder_windows(session)
        uow = UnitOfWork(session)
        candidates = documents.expiring(session, within_days=max(windows), today=today)
        reference = today or datetime.now(UTC).date()
        outcomes: Counter[str] = Counter()
        due = 0
        for document in candidates:
            if document.expiry_date is None:
                continue
            days_left = (document.expiry_date - reference).days
            if days_left not in windows:
                continue
            vendor = session.get(Vendor, document.vendor_id)
            if vendor is None:
                outcomes["no_vendor"] += 1
                continue
            due += 1
            outcome = notifications.notify_document_expiring(
                uow, settings, vendor, document, window_days=days_left, today=reference
            )
            outcomes[outcome] += 1
    logger.info(
        "expiry_reminders: %d candidate(s) within %s day window(s), %d due today: %s",
        len(candidates),
        windows,
        due,
        dict(outcomes) if outcomes else "nothing due",
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


def _adapter_due(cron: str, last_run: datetime | None, now: datetime) -> bool:
    """Whether a scheduled instant of ``cron`` falls between ``last_run`` and ``now``.

    ``CronTrigger.get_next_fire_time(previous, now)`` returns the first occurrence strictly
    after ``previous`` — it does not clamp to ``now``, so passing the real last run (or
    ``_NEVER`` when there is none) and comparing the result to ``now`` is exactly "has this
    adapter missed a scheduled pull", including recovering a run the worker was down for.
    """
    try:
        trigger = CronTrigger.from_crontab(cron, timezone="UTC")
    except ValueError:
        return False
    next_fire = trigger.get_next_fire_time(last_run or _NEVER, now)
    return next_fire is not None and next_fire <= now


def _last_sync(session: Session, adapter: AdapterKey, vendor_id: uuid.UUID) -> datetime | None:
    return session.scalar(
        select(func.max(SyncLog.started_at)).where(
            SyncLog.adapter == adapter.value, SyncLog.vendor_id == vendor_id
        )
    )


def adapter_pulls(*, now: datetime | None = None) -> None:
    """Run every enabled, due ``AdapterConfig`` (task 2E's adapter layer, brief §2G).

    "Due" is evaluated per adapter *and per vendor* against that config's own
    ``schedule_cron`` and that vendor's own last ``SyncLog`` row — not against this job's own
    cron, which only bounds how often the check itself runs. A vendor with no
    ``schedule_cron`` set is enabled but never scheduled: nothing invented, nothing assumed.

    ``run_sync`` already isolates one vendor's failure into a ``FAILED`` ``SyncLog`` row
    without raising; the ``try/except`` here exists for the one path that *does* raise
    (``AdapterNotConfiguredError``, when a vendor turns out unconfigured despite the
    ``is_enabled`` flag) so that one mis-set vendor cannot stop the rest of the run.
    """
    reference = now or datetime.now(UTC)
    with session_scope() as session:
        uow = UnitOfWork(session)
        ran = 0
        not_due = 0
        skipped_unscheduled = 0
        failed = 0
        for key in sorted(CONFIGURABLE, key=lambda item: item.value):
            for config in config_store.enabled_configs(session, key):
                if config.vendor_id is None:
                    continue
                if not config.schedule_cron:
                    skipped_unscheduled += 1
                    continue
                last_run = _last_sync(session, key, config.vendor_id)
                if not _adapter_due(config.schedule_cron, last_run, reference):
                    not_due += 1
                    continue
                try:
                    run_sync(uow, key, vendor_id=config.vendor_id)
                    ran += 1
                except AdapterError as exc:
                    # The one case run_sync cannot log as a SyncLog row itself: nothing was
                    # even attempted for this vendor. Counted and reported, never re-raised —
                    # the next vendor's pull must still run.
                    failed += 1
                    logger.error(
                        "adapter_pulls: %s vendor=%s did not run: %s",
                        key.value,
                        config.vendor_id,
                        exc,
                    )
    logger.info(
        "adapter_pulls: ran=%d not_due=%d unscheduled=%d failed=%d",
        ran,
        not_due,
        skipped_unscheduled,
        failed,
    )


def _prequalification_validity_months(application: Application, default_months: int) -> int:
    """Real validity for *this* application: the officer's override at approval time
    (``application.declaration["valid_months"]``, set in ``services/evaluation.decide``) when
    one was recorded, otherwise the organisation default — never a guess in between."""
    declared = application.declaration.get("valid_months") if application.declaration else None
    if isinstance(declared, int) and declared > 0:
        return declared
    return default_months


def prequalification_expiry(*, today: date | None = None) -> None:
    """Warn before a vendor's 12-month prequalification validity lapses (spec §9).

    There is no state transition to make: ``prequalified`` is terminal in
    ``services/state_machine.py`` by design ("re-qualification is a new application in a new
    cycle"), so this job's whole job is the warning. Only a vendor whose status is still
    ``prequalified`` is warned — one a manager has since suspended is not, since the warning
    would be about a status that no longer describes the vendor.
    """
    with session_scope() as session:
        settings = get_settings()
        if not settings_store.group(session, "notifications").get("email_enabled", True):
            logger.info("prequalification_expiry: notifications.email_enabled is False; skipping")
            return
        windows = _reminder_windows(session)
        default_validity_months = int(
            settings_store.group(session, "qualification").get("validity_months", 12)
        )
        uow = UnitOfWork(session)
        reference = today or datetime.now(UTC).date()

        approved = list(
            session.scalars(
                select(Application).where(
                    Application.status == ApplicationStatus.PREQUALIFIED,
                    Application.decision == DecisionKind.APPROVE,
                    Application.decided_at.is_not(None),
                )
            )
        )
        # A vendor can carry more than one ``prequalified`` application across cycles — the
        # state machine never loops back out of it, so an old one stays on the books. Only
        # the newest decision is what "when does this vendor's status lapse" means.
        latest_by_vendor: dict[uuid.UUID, Application] = {}
        for application in approved:
            assert application.decided_at is not None
            current = latest_by_vendor.get(application.vendor_id)
            if current is None or application.decided_at > current.decided_at:  # type: ignore[operator]
                latest_by_vendor[application.vendor_id] = application

        outcomes: Counter[str] = Counter()
        due = 0
        for application in latest_by_vendor.values():
            vendor = session.get(Vendor, application.vendor_id)
            if vendor is None or vendor.status is not VendorStatus.PREQUALIFIED:
                continue
            assert application.decided_at is not None
            valid_months = _prequalification_validity_months(application, default_validity_months)
            lapse_date = add_calendar_months(application.decided_at.date(), valid_months)
            days_left = (lapse_date - reference).days
            if days_left not in windows:
                continue
            due += 1
            outcome = notifications.notify_prequalification_lapsing(
                uow,
                settings,
                vendor,
                lapse_date=lapse_date,
                window_days=days_left,
                today=reference,
            )
            outcomes[outcome] += 1
    logger.info(
        "prequalification_expiry: %d prequalified vendor(s) checked, %d due today: %s",
        len(latest_by_vendor),
        due,
        dict(outcomes) if outcomes else "nothing due",
    )


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
        "0 2 * * *",
        "ERP / registry adapter pulls (each config's own schedule decides what actually runs)",
        adapter_pulls,
    ),
    JobSpec(
        "prequalification_expiry",
        "0 6 * * *",
        "Warn before 12-month prequalifications lapse",
        prequalification_expiry,
    ),
)

JOBS_BY_KEY: dict[str, JobSpec] = {job.key: job for job in JOBS}
