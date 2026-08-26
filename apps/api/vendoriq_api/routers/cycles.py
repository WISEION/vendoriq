"""Qualification cycles and their invitations (contract tag ``cycles``, spec §9, §11).

Screen 21 (`docs/SCREENS.md`). Every handler: authorise, load, call a service — no SQL and
no business rule lives here (CONTRIBUTING, "repositories own the queries").
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from ..config import Settings, get_settings
from ..db import UnitOfWork
from ..models import QualificationCycle as CycleRow
from ..models.enums import CycleKind, CycleStatus
from ..schemas.cycles import (
    Cycle,
    CycleDetail,
    CycleInput,
    CycleInviteInput,
    CycleInviteResult,
    CycleInviteSkip,
    CyclePage,
)
from ..security import Principal, get_uow, require
from ..services import applications as applications_service
from ..services import cycles as cycles_service

router = APIRouter(tags=["cycles"])


def cycle_payload(uow: UnitOfWork, cycle: CycleRow) -> Cycle:
    return Cycle(
        id=cycle.id,
        name=cycle.name,
        kind=cycle.kind,
        scoring_model_version=cycle.scoring_model_version,
        opens_at=cycle.opens_at,
        closes_at=cycle.closes_at,
        project_id=cycle.project_id,
        status=cycle.status,
        application_count=cycles_service.application_count(uow.session, cycle.id),
        is_demo=cycle.is_demo,
    )


@router.get("/cycles")
def list_cycles(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    status_filter: Annotated[list[CycleStatus] | None, Query(alias="status")] = None,
    kind: CycleKind | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listCycles")),
) -> CyclePage:
    filters = cycles_service.CycleFilters(
        statuses=status_filter or (), kind=kind.value if kind else None
    )
    rows, total = cycles_service.list_page(uow.session, filters, page=page, page_size=page_size)
    return CyclePage(
        items=[cycle_payload(uow, row) for row in rows], total=total, page=page, page_size=page_size
    )


@router.post("/cycles", status_code=status.HTTP_201_CREATED)
def create_cycle(
    body: CycleInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createCycle")),
) -> Cycle:
    cycle = cycles_service.create(uow, body.model_dump(exclude_unset=True))
    return cycle_payload(uow, cycle)


@router.get("/cycles/{cycle_id}")
def get_cycle(
    cycle_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getCycle")),
) -> CycleDetail:
    cycle = cycles_service.get(uow.session, cycle_id)
    return CycleDetail(
        **cycle_payload(uow, cycle).model_dump(),
        counts_by_status=cycles_service.counts_by_status(uow.session, cycle_id),
        committee=[],
    )


@router.patch("/cycles/{cycle_id}")
def patch_cycle(
    cycle_id: uuid.UUID,
    body: CycleInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchCycle")),
) -> Cycle:
    cycle = cycles_service.get(uow.session, cycle_id)
    cycles_service.patch(uow, cycle, body.model_dump(exclude_unset=True))
    return cycle_payload(uow, cycle)


@router.delete("/cycles/{cycle_id}", status_code=204)
def delete_cycle(
    cycle_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("deleteCycle")),
) -> None:
    cycle = cycles_service.get(uow.session, cycle_id)
    cycles_service.delete(uow, cycle)


@router.post("/cycles/{cycle_id}/invite")
def invite_to_cycle(
    cycle_id: uuid.UUID,
    body: CycleInviteInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("inviteToCycle")),
    settings: Settings = Depends(get_settings),
) -> CycleInviteResult:
    """Bulk invitation for a TQS: each vendor's application moves to ``invited`` (spec §9)."""
    cycle = cycles_service.get(uow.session, cycle_id)
    outcome = cycles_service.invite_bulk(
        uow,
        cycle,
        body.vendor_ids,
        settings=settings,
        message_az=body.message_az,
        message_en=body.message_en,
    )
    return CycleInviteResult(
        invited=[applications_service.payload(uow.session, app) for app in outcome.invited],
        skipped=[
            CycleInviteSkip(vendor_id=vendor_id, reason=reason)
            for vendor_id, reason in outcome.skipped
        ],
    )


__all__ = ["router"]
