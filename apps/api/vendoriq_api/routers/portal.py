"""The vendor's own application: reading it, saving answers, submitting it.

Contract tag ``applications``. Owned by phase-2 task 2A.

Operations implemented here, from ``docs/openapi.yaml``:
listApplications, getApplication, patchAnswers, submitApplication.

Same shape as ``routers/vendors.py``: authorise the operation, narrow to what the caller may
see, call a service. No SQL and no scoring/completeness logic lives here.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..db import UnitOfWork
from ..models import Application as ApplicationRow
from ..models import Vendor as VendorRow
from ..models.enums import ApplicationStatus
from ..schemas.applications import (
    AnswerPatch,
    AnswerState,
    ApplicationDetail,
    ApplicationPage,
    DeclarationInput,
)
from ..security import Principal, get_uow, require, scope_to_vendor
from ..services import answers as answers_service
from ..services import applications as applications_service
from ..services import observations as observations_service
from ..services import submission as submission_service
from ..services import vendors as vendors_service

router = APIRouter(tags=["applications"])


def _load(
    uow: UnitOfWork, principal: Principal, application_id: uuid.UUID, operation: str
) -> ApplicationRow:
    """Fetch the application, then confine a vendor caller to its own (404, not 403)."""
    application = applications_service.get(uow.session, application_id)
    scope_to_vendor(principal, application.vendor_id, operation)
    return application


@router.get("/applications")
def list_applications(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    cycle_id: uuid.UUID | None = None,
    status: Annotated[list[ApplicationStatus] | None, Query()] = None,
    vendor_id: uuid.UUID | None = None,
    q: str | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listApplications")),
) -> ApplicationPage:
    """The evaluation queue for staff; a vendor sees exactly its own applications."""
    rows, total = submission_service.list_page(
        uow.session,
        principal_vendor_id=principal.vendor_id if principal.is_vendor else None,
        cycle_id=cycle_id,
        statuses=status,
        vendor_id=vendor_id,
        q=q,
        page=page,
        page_size=page_size,
    )
    return ApplicationPage(
        items=[
            submission_service.summary_payload(uow.session, row, principal_role=principal.role)
            for row in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/applications/{application_id}")
def get_application(
    application_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getApplication")),
) -> ApplicationDetail:
    """Answers, raw indicators, rubric and computed score — the score gated for vendors."""
    application = _load(uow, principal, application_id, "getApplication")
    return submission_service.detail_payload(
        uow.session, application, principal_role=principal.role
    )


@router.patch("/applications/{application_id}/answers")
def patch_answers(
    application_id: uuid.UUID,
    body: AnswerPatch,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchAnswers")),
) -> AnswerState:
    """Autosave: each present field becomes a ``portal`` observation (spec §6.2, §7)."""
    application = _load(uow, principal, application_id, "patchAnswers")
    vendor = vendors_service.get(uow.session, application.vendor_id)
    answers_service.patch(uow, application, vendor, body.answers, role=principal.role)
    return _answer_state(uow, vendor)


def _answer_state(uow: UnitOfWork, vendor: VendorRow) -> AnswerState:
    profile = observations_service.current_profile(uow.session, vendor.id)
    return AnswerState(
        completion_pct=answers_service.completion_pct(profile),
        checks=submission_service.checks(uow.session, vendor),
        computed_fields=answers_service.computed_fields(profile, vendor.type.value),
    )


@router.post("/applications/{application_id}/submit")
def submit_application(
    application_id: uuid.UUID,
    body: DeclarationInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("submitApplication")),
) -> ApplicationDetail:
    """Sign the declaration and submit; a failed pre-submission check is a ``409`` (spec §7)."""
    application = _load(uow, principal, application_id, "submitApplication")
    vendor = vendors_service.get(uow.session, application.vendor_id)
    submission_service.submit(uow, application, vendor, body, role=principal.role)
    return submission_service.detail_payload(
        uow.session, application, principal_role=principal.role
    )


__all__ = ["router"]
