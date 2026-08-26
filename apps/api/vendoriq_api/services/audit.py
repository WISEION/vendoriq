"""The audit trail (spec §13: immutable log of every status change, score edit, decision).

Every mutating service call ends in :func:`record`. It is a plain function rather than an
ORM event hook on purpose: a hook fires on flush and knows the row diff but not the *reason*
or the operation the user invoked, and half the interesting mutations ("suspended, because
tax debt") are exactly the ones a diff cannot explain.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from ..db import UnitOfWork
from ..models import AuditEvent
from ..models.base import Base


def jsonable(value: Any) -> Any:
    """Coerce a before/after image into something JSONB accepts, losing nothing readable."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [jsonable(item) for item in value]
    return str(value)


def snapshot(instance: Base, fields: tuple[str, ...]) -> dict[str, Any]:
    """A before/after image of the named columns. Keep it small — this is read by humans."""
    return {name: jsonable(getattr(instance, name, None)) for name in fields}


def record(
    uow: UnitOfWork,
    *,
    entity_type: str,
    entity_id: uuid.UUID | None,
    action: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    actor_id: uuid.UUID | None = None,
) -> AuditEvent:
    """Append one audit row inside the caller's transaction.

    The row and the change it describes commit together, so an audit entry can never
    describe a mutation that was rolled back, nor a mutation escape unlogged.
    """
    event = AuditEvent(
        # Same reason as the domain event log: ``now()`` is per transaction, and an audit
        # trail whose rows all share one timestamp cannot be read in the order it happened.
        created_at=datetime.now(UTC),
        actor_id=actor_id if actor_id is not None else _actor(uow),
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=jsonable(before) if before is not None else None,
        after=jsonable(after) if after is not None else None,
    )
    uow.session.add(event)
    return event


def _actor(uow: UnitOfWork) -> uuid.UUID | None:
    actor = uow.actor_id
    return actor if isinstance(actor, uuid.UUID) else None


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Only the keys that actually changed — an audit log full of no-ops is unreadable."""
    return {key: value for key, value in after.items() if before.get(key) != value}


def count_for(session: Session, entity_type: str, entity_id: uuid.UUID) -> int:
    """Test and admin helper: how many audit rows one entity carries."""
    return (
        session.query(AuditEvent)
        .filter(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
        .count()
    )
