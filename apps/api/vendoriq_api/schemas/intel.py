"""The market-intelligence views (contract tag ``intel``, spec §12).

Shapes are transcribed from ``docs/openapi.yaml`` — see ``schemas/base.py``'s docstring for
why these do not generate the contract. Every number here is computed by ``services/intel.py``
from current observations (ADR-004); nothing in this module derives a value.
"""

from __future__ import annotations

from ..models.enums import CategoryKind, ObservationSource, ScoreClass
from .base import Model, PageMeta
from .vendors import Document


class IntelOverview(Model):
    vendors_total: int
    vendors_sub: int = 0
    vendors_sup: int = 0
    prequalified: int
    prequalified_ab: int = 0
    awaiting_review: int
    incomplete: int = 0
    documents_expiring_60d: int
    category_gaps: int = 0


class CoverageRow(Model):
    category_code: str
    name_az: str = ""
    name_en: str = ""
    kind: CategoryKind
    #: Vendor count per class, e.g. ``{"A": 2, "B": 1}`` — only classes that occur, so an
    #: absent key is a true zero rather than a fabricated one.
    counts: dict[str, int]
    total: int = 0
    #: Share of class A/B among scored vendors in this category, or ``None`` when nobody in
    #: the category has been scored yet — an unknown is never rendered as a zero.
    ab_share: float | None = None


class ClassDistributionRow(Model):
    cls: ScoreClass
    count: int


class CapacityRow(Model):
    category_code: str
    name_az: str = ""
    name_en: str = ""
    vendor_count: int
    total_turnover: float = 0
    engineers: int = 0
    ongoing_projects: int = 0


class PenetrationRow(Model):
    key: str
    share: float
    count: int
    total: int


class SourceCount(Model):
    source: ObservationSource
    count: int
    share: float


class SourceMix(Model):
    total_observations: int
    by_source: list[SourceCount]
    stale_profiles: int
    diverging_vendors: int = 0


class ExpiringDocument(Document):
    vendor_name: str


class ExpiringDocumentPage(PageMeta):
    items: list[ExpiringDocument]


class MarketGap(Model):
    category_code: str
    name_az: str
    name_en: str
    kind: CategoryKind
    registered_vendors: int = 0


class AttentionItem(Model):
    key: str
    count: int
    severity: str = "info"
    link: str | None = None


__all__ = [
    "AttentionItem",
    "CapacityRow",
    "ClassDistributionRow",
    "CoverageRow",
    "ExpiringDocument",
    "ExpiringDocumentPage",
    "IntelOverview",
    "MarketGap",
    "PenetrationRow",
    "SourceCount",
    "SourceMix",
]
