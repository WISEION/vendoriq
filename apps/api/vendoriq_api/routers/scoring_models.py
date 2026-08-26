"""Scoring model versions and the editor.

Contract tag ``scoring-models``. Owned by phase-2 task 2D.

Operations this module must implement, from ``docs/openapi.yaml``:
listScoringModels, getScoringModel, createScoringModelDraft, patchScoringModelDraft, testRescore,
publishScoringModel.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..db import UnitOfWork
from ..models.enums import VendorType
from ..schemas.scoring_models import (
    CreateDraftInput,
    PublishInput,
    RescoreInput,
    RescoreReport,
    ScoringModel,
    ScoringModelPatch,
    ScoringModelSummary,
)
from ..security import Principal, get_uow, require
from ..services import scoring_models as scoring_models_service

router = APIRouter(tags=["scoring-models"])


@router.get("/scoring-models")
def list_scoring_models(
    vendor_type: VendorType | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("listScoringModels")),
) -> list[ScoringModelSummary]:
    rows = scoring_models_service.list_models(uow.session, vendor_type)
    return [
        ScoringModelSummary(**scoring_models_service.summary_payload(uow.session, row))
        for row in rows
    ]


@router.post("/scoring-models", status_code=201)
def create_scoring_model_draft(
    body: CreateDraftInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("createScoringModelDraft")),
) -> ScoringModel:
    draft = scoring_models_service.create_draft(
        uow,
        from_version=body.from_version,
        version=body.version,
        name_az=body.name_az,
        name_en=body.name_en,
        note=body.note,
    )
    return ScoringModel(**scoring_models_service.full_payload(uow.session, draft))


@router.get("/scoring-models/{version}")
def get_scoring_model(
    version: str,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getScoringModel")),
) -> ScoringModel:
    row = scoring_models_service.get(uow.session, version)
    return ScoringModel(**scoring_models_service.full_payload(uow.session, row))


@router.patch("/scoring-models/{version}")
def patch_scoring_model_draft(
    version: str,
    body: ScoringModelPatch,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("patchScoringModelDraft")),
) -> ScoringModel:
    row = scoring_models_service.get(uow.session, version)
    scoring_models_service.patch_draft(uow, row, body.model_dump(exclude_unset=True))
    return ScoringModel(**scoring_models_service.full_payload(uow.session, row))


@router.post("/scoring-models/{version}/test-rescore")
def test_rescore(
    version: str,
    body: RescoreInput,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("testRescore")),
) -> RescoreReport:
    candidate = scoring_models_service.get(uow.session, version)
    report = scoring_models_service.test_rescore(uow.session, candidate, body.cycle_id)
    return RescoreReport(**report)


@router.post("/scoring-models/{version}/publish")
def publish_scoring_model(
    version: str,
    body: PublishInput | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("publishScoringModel")),
) -> ScoringModel:
    row = scoring_models_service.get(uow.session, version)
    effective_from = body.effective_from if body is not None else None
    scoring_models_service.publish(uow, row, effective_from)
    return ScoringModel(**scoring_models_service.full_payload(uow.session, row))


__all__ = ["router"]
