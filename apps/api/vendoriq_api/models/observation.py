"""Append-only field observations — the provenance layer (spec §4, §6.6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Computed,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, JsonDict, pg_enum, uuid_pk
from .enums import ObservationSource

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .auth import User
    from .vendor import Vendor

#: SQL mirror of ``enums.SOURCE_TRUST_RANK``; used for the generated ``trust_rank`` column.
#: Compared enum-to-enum rather than through ``::text`` — a cast to text is only STABLE,
#: and PostgreSQL requires an IMMUTABLE expression in a generated column.
_TRUST_RANK_SQL = (
    "CASE source "
    "WHEN 'registry'::observation_source THEN 1 "
    "WHEN 'api'::observation_source THEN 2 "
    "WHEN 'document'::observation_source THEN 3 "
    "WHEN 'portal'::observation_source THEN 4 "
    "WHEN 'excel'::observation_source THEN 4 "
    "WHEN 'manual'::observation_source THEN 5 "
    "ELSE 9 END"
)


class FieldObservation(Base):
    """One recorded value for one field code.

    Rows are never updated or deleted: the current value of a field is the observation
    with the lowest ``trust_rank`` and, within that, the newest ``observed_at``.
    """

    __tablename__ = "field_observation"
    __table_args__ = (
        Index(
            "ix_field_observation_current",
            "vendor_id",
            "field_code",
            "trust_rank",
            "observed_at",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Application field catalogue code — ``A.1`` … ``G.7``, or a table code such as ``C.t1``.
    field_code: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Scalar values are wrapped as ``{"value": …}``; tables are stored as JSON arrays.
    value: Mapped[JsonDict] = mapped_column(nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[ObservationSource] = mapped_column(
        pg_enum(ObservationSource, "observation_source"), nullable=False
    )
    #: File key, API call id, import run id — whatever identifies the origin.
    source_ref: Mapped[str | None] = mapped_column(String(255))
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    entered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    #: Derived from ``source`` by the database (1 = most trusted).
    trust_rank: Mapped[int] = mapped_column(
        SmallInteger, Computed(_TRUST_RANK_SQL, persisted=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    vendor: Mapped[Vendor] = relationship(back_populates="observations")
    author: Mapped[User | None] = relationship()
