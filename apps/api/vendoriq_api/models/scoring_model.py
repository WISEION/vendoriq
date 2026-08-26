"""Versioned scoring models (spec §10.3).

The ``criteria`` payload is the same JSON shape that
``packages/scoring/vendoriq_scoring/models/*.json`` ships — that file is the contract.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, JsonDict, JsonList, TimestampMixin, pg_enum
from .enums import ScoringModelStatus, VendorType


class ScoringModel(Base, TimestampMixin):
    """A frozen criteria set. ``version`` is the natural key, e.g. ``sub-4``, ``sup-1``."""

    __tablename__ = "scoring_model"

    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    vendor_type: Mapped[VendorType] = mapped_column(
        pg_enum(VendorType, "vendor_type"), nullable=False
    )
    #: Bilingual, because the model name is user-facing and spec §13 requires AZ and EN for
    #: every user-facing string. A single ``name`` column could not serve the contract's
    #: ``ScoringModelSummary``, which requires both.
    name_az: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Editorial state — the commission's judgement. See ``ScoringModelStatus`` for how this
    #: differs from ``is_locked``.
    status: Mapped[ScoringModelStatus] = mapped_column(
        pg_enum(ScoringModelStatus, "scoring_model_status"),
        nullable=False,
        default=ScoringModelStatus.ACTIVE,
    )
    #: ``[{group, name_az, name_en, max}]`` — the group headings the evaluation screen totals
    #: under. Required by the contract's ``ScoringModel``.
    groups: Mapped[JsonList] = mapped_column(nullable=False, default=list)
    #: ``[{code, group, max, kind, spec, ko}]`` — see packages/scoring/README.md.
    criteria: Mapped[JsonList] = mapped_column(nullable=False)
    #: ``[{cls, min, label_az, label_en}]`` class bands, highest first.
    classes: Mapped[JsonList] = mapped_column(nullable=False)
    pass_mark: Mapped[float] = mapped_column(Numeric(5, 1), nullable=False, default=70)
    validity_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    effective_from: Mapped[date | None] = mapped_column(Date)
    #: True once an application has been scored with it — the row becomes immutable.
    is_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    #: Free-form note explaining what changed against the previous version.
    #:
    #: ``currency`` and ``total_max`` from the JSON file are deliberately **not** columns.
    #: ADR-007 fixes the currency at AZN with no conversion anywhere, and a column whose only
    #: legal value is AZN invites the illusion that another one would work. ``total_max`` is
    #: the sum of the criteria maxima — stored separately it can disagree with them, and then
    #: two numbers claim to be the total.
    notes: Mapped[JsonDict | None] = mapped_column(nullable=True)
