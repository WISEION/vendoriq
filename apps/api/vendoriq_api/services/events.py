"""The domain event log and the webhook hand-off point (brief §2, phase 2E).

The audit log answers "who changed what"; the event log answers "what happened that another
system cares about". They are separate tables because they have different readers, different
retention and different shapes: an audit row carries a before/after image of *our* columns,
an event carries a stable public payload.

Webhook delivery is phase 2E. :func:`dispatch` is where it plugs in, and it is called on
every emit today so that adding delivery is a change to one function body rather than a hunt
through the services for the places that should have called it.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from ..db import UnitOfWork
from ..models import Event
from ..models.enums import EventType
from .audit import jsonable

logger = logging.getLogger("vendoriq.events")

#: Set by phase 2E to the real dispatcher. Signature: ``(event) -> None``.
_dispatcher: Callable[[Event], None] | None = None


def set_dispatcher(dispatcher: Callable[[Event], None] | None) -> None:
    """Install the webhook dispatcher. Phase 2E calls this at application start-up."""
    global _dispatcher
    _dispatcher = dispatcher


def dispatch(event: Event) -> None:
    """Hand an event to the subscribers.

    Until phase 2E installs a dispatcher this only logs, which is deliberate: an event that
    nobody delivers is still an event that happened, and the log line is how the absence of
    a subscriber is visible during development.
    """
    if _dispatcher is not None:
        _dispatcher(event)
        return
    logger.info(
        "event %s %s/%s (no webhook dispatcher installed)",
        event.type,
        event.entity_type,
        event.entity_id,
    )


def emit(
    uow: UnitOfWork,
    event_type: EventType,
    *,
    entity_type: str,
    entity_id: uuid.UUID | None,
    payload: dict[str, Any] | None = None,
) -> Event:
    """Write one domain event inside the caller's transaction, then offer it to webhooks."""
    event = Event(
        # Stamped in Python, not by the column's ``now()`` default: PostgreSQL's ``now()`` is
        # the *transaction* start, so every event a request emits would share one instant and
        # a poller using ``since=`` could not resume between two of them.
        created_at=datetime.now(UTC),
        type=event_type.value,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=jsonable(payload or {}),
    )
    uow.session.add(event)
    # Flush so the row has its id before a dispatcher sees it; the transaction is still open,
    # so a later failure in the same request rolls the event back with everything else.
    uow.flush()
    dispatch(event)
    return event
