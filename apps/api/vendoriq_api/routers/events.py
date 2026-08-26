"""The domain event log (contract ``GET /events``).

The same stream webhooks deliver. A future product polls this with an API key instead of
subscribing, which is why the operation is scoped ``integrations:read`` rather than tied to
a person's role (brief §2, "API-first").
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from ..db import UnitOfWork
from ..models import Event as EventRow
from ..models.enums import EventType
from ..schemas import Event, EventPage
from ..security import Principal, get_uow, require

router = APIRouter(tags=["events"])


@router.get("/events")
def list_events(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    type: Annotated[list[EventType] | None, Query()] = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    since: datetime | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listEvents")),
) -> EventPage:
    """Newest first. ``since`` is what a poller passes to resume where it stopped."""
    query = select(EventRow)
    if type:
        query = query.where(EventRow.type.in_([item.value for item in type]))
    if entity_type:
        query = query.where(EventRow.entity_type == entity_type)
    if entity_id is not None:
        query = query.where(EventRow.entity_id == entity_id)
    if since is not None:
        query = query.where(EventRow.created_at > since)

    total = uow.session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = uow.session.scalars(
        query.order_by(EventRow.created_at.desc(), EventRow.id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    return EventPage(
        items=[
            Event(
                id=row.id,
                type=row.type,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                payload=row.payload,
                created_at=row.created_at,
            )
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
