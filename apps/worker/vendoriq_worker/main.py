"""Worker entry point: an APScheduler blocking scheduler over ``jobs.JOBS``."""

from __future__ import annotations

import logging
import signal
import sys
from types import FrameType

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from vendoriq_api.config import get_settings

from .jobs import JOBS

logger = logging.getLogger("vendoriq.worker")


def build_scheduler() -> BlockingScheduler:
    """Register every job from the registry. Importable, so tests can assert the schedule."""
    scheduler = BlockingScheduler(timezone="UTC")
    for job in JOBS:
        scheduler.add_job(
            job.run,
            trigger=CronTrigger.from_crontab(job.cron, timezone="UTC"),
            id=job.key,
            name=job.description,
            replace_existing=True,
            misfire_grace_time=3600,
        )
    return scheduler


def main() -> int:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    scheduler = build_scheduler()

    def _stop(signum: int, _frame: FrameType | None) -> None:
        logger.info("signal %s received, shutting down", signum)
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    logger.info("worker starting with %d job(s), env=%s", len(JOBS), settings.app_env)
    scheduler.start()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
