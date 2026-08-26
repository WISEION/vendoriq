"""The market-intelligence views.

Contract tag ``intel``. Owned by phase-2 task 2D.

Every handler here is a thin adapter: ``services/intel.py`` does the counting, this module
only shapes the result into the contract's response schema. No threshold, share or gap label
is computed in this file (CONTRIBUTING: business logic lives in the service layer, never the
router — and never the frontend).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..db import UnitOfWork
from ..models.enums import CategoryKind, VendorType
from ..schemas.intel import (
    AttentionItem,
    CapacityRow,
    ClassDistributionRow,
    CoverageRow,
    ExpiringDocumentPage,
    IntelOverview,
    MarketGap,
    PenetrationRow,
    SourceMix,
)
from ..security import Principal, get_uow, require
from ..services import intel as intel_service

router = APIRouter(tags=["intel"])


@router.get("/intel/overview")
def get_intel_overview(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getIntelOverview")),
) -> IntelOverview:
    return IntelOverview(**intel_service.overview(uow.session))


@router.get("/intel/coverage")
def get_intel_coverage(
    kind: CategoryKind | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getIntelCoverage")),
) -> list[CoverageRow]:
    return [CoverageRow(**row) for row in intel_service.coverage(uow.session, kind)]


@router.get("/intel/class-distribution")
def get_class_distribution(
    vendor_type: VendorType | None = None,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getClassDistribution")),
) -> list[ClassDistributionRow]:
    return [
        ClassDistributionRow(**row)
        for row in intel_service.class_distribution(uow.session, vendor_type)
    ]


@router.get("/intel/capacity")
def get_intel_capacity(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getIntelCapacity")),
) -> list[CapacityRow]:
    return [CapacityRow(**row) for row in intel_service.capacity(uow.session)]


@router.get("/intel/certification")
def get_intel_certification(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getIntelCertification")),
) -> list[PenetrationRow]:
    return [PenetrationRow(**row) for row in intel_service.certification(uow.session)]


@router.get("/intel/sources")
def get_intel_sources(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getIntelSources")),
) -> SourceMix:
    return SourceMix(**intel_service.sources(uow.session))


@router.get("/intel/expiring-documents")
def get_expiring_documents(
    within_days: Annotated[int, Query(ge=0)] = 60,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 25,
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getExpiringDocuments")),
) -> ExpiringDocumentPage:
    return ExpiringDocumentPage(
        **intel_service.expiring_documents(
            uow.session, within_days=within_days, page=page, page_size=page_size
        )
    )


@router.get("/intel/gaps")
def get_market_gaps(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getMarketGaps")),
) -> list[MarketGap]:
    return [MarketGap(**row) for row in intel_service.gaps(uow.session)]


@router.get("/intel/attention")
def get_attention_list(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(require("getAttentionList")),
) -> list[AttentionItem]:
    return [AttentionItem(**row) for row in intel_service.attention(uow.session)]


__all__ = ["router"]
