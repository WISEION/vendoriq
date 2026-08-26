"""Officer evaluation, the commission decision and the summary exports.

Contract tag ``applications``. Owned by phase-2 task 2B.

Operations this module must implement, from ``docs/openapi.yaml``:
getEvaluation, putEvaluation, computeScore, decideApplication, putSecondEvaluation,
exportCommissionSummaryXlsx, exportCommissionSummaryPdf.

The module and its mount exist before the handlers do so that no phase-2 worker has to edit
``main.py`` or ``routers/__init__.py`` — seven tasks editing one registration list in a shared
working tree is how a mount gets silently dropped. An empty router mounts cleanly and serves
nothing, so this is inert until its owner fills it in.
"""

from __future__ import annotations

import io
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import QualificationCycle
from ..schemas.evaluations import (
    ApplicationDetail,
    ComputeRequest,
    DecisionInput,
    Evaluation,
    RubricInput,
    ScoreResult,
    SecondEvaluation,
)
from ..security import Principal, get_uow, require
from ..services import evaluation as evaluation_service
from ..services import exports as exports_service

router = APIRouter(tags=["applications"])

Locale = Literal["az", "en"]


def _cycle_or_404(uow: UnitOfWork, cycle_id: uuid.UUID) -> QualificationCycle:
    cycle = uow.session.get(QualificationCycle, cycle_id)
    if cycle is None:
        raise ApiError(404, "not_found", "No such qualification cycle.")
    return cycle


# ── evaluation sheet ─────────────────────────────────────────────────────────
@router.get("/applications/{application_id}/evaluation")
def get_evaluation(
    application_id: uuid.UUID,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getEvaluation")),
) -> Evaluation:
    application = evaluation_service.get(uow.session, application_id)
    return evaluation_service.get_evaluation(uow.session, application)


@router.put("/applications/{application_id}/evaluation")
def put_evaluation(
    application_id: uuid.UUID,
    body: RubricInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("putEvaluation")),
) -> Evaluation:
    application = evaluation_service.get(uow.session, application_id)
    return evaluation_service.save_evaluation(uow, application, principal, body)


@router.post("/applications/{application_id}/compute")
def compute_score(
    application_id: uuid.UUID,
    body: ComputeRequest,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("computeScore")),
) -> ScoreResult:
    """Live scoring for the evaluation screen. Persists nothing (brief §2)."""
    application = evaluation_service.get(uow.session, application_id)
    return evaluation_service.compute(uow.session, application, body)


@router.post("/applications/{application_id}/decide")
def decide_application(
    application_id: uuid.UUID,
    body: DecisionInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("decideApplication")),
) -> ApplicationDetail:
    application = evaluation_service.get(uow.session, application_id)
    return evaluation_service.decide(uow, application, principal, body)


@router.put("/applications/{application_id}/second-evaluator")
def put_second_evaluation(
    application_id: uuid.UUID,
    body: RubricInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("putSecondEvaluation")),
) -> SecondEvaluation:
    application = evaluation_service.get(uow.session, application_id)
    return evaluation_service.save_second_evaluation(uow, application, principal, body)


# ── commission summary exports ──────────────────────────────────────────────
@router.get("/cycles/{cycle_id}/export-summary.xlsx")
def export_commission_summary_xlsx(
    cycle_id: uuid.UUID,
    locale: Locale = Query(default="az"),
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("exportCommissionSummaryXlsx")),
) -> Response:
    """The layout of workbook sheet "5. Nəticə Xülasəsi", for this cycle's applications."""
    cycle = _cycle_or_404(uow, cycle_id)
    workbook = exports_service.build_commission_summary_workbook(uow.session, cycle, locale=locale)
    buffer = io.BytesIO()
    workbook.save(buffer)
    filename = f"{cycle.name.replace(' ', '_')}-commission-summary.xlsx"
    return Response(
        content=buffer.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/cycles/{cycle_id}/export-summary.pdf")
def export_commission_summary_pdf(
    cycle_id: uuid.UUID,
    locale: Locale = Query(default="az"),
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("exportCommissionSummaryPdf")),
) -> Response:
    cycle = _cycle_or_404(uow, cycle_id)
    content = exports_service.build_commission_summary_pdf(uow.session, cycle, locale=locale)
    filename = f"{cycle.name.replace(' ', '_')}-commission-summary.pdf"
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


__all__ = ["router"]
