"""Vendor document package — checklist codes A-01 … H-02 (spec §5, Appendix B)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, pg_enum, uuid_pk
from .enums import DocumentStatus

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .auth import User
    from .vendor import Vendor


class Document(Base, TimestampMixin):
    """One checklist slot for one vendor; ``file_key`` points into the storage backend."""

    __tablename__ = "document"
    __table_args__ = (Index("ix_document_expiry", "expiry_date"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Checklist code, e.g. ``A-05`` (tax clearance, always expires issue date + 3 months).
    code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    #: Object key in the storage backend (``local`` filesystem or ``s3``/MinIO).
    file_key: Mapped[str | None] = mapped_column(String(512))
    filename: Mapped[str | None] = mapped_column(String(255))
    issue_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[DocumentStatus] = mapped_column(
        pg_enum(DocumentStatus, "document_status"),
        nullable=False,
        default=DocumentStatus.MISSING,
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_demo: Mapped[bool] = mapped_column(nullable=False, default=False)

    vendor: Mapped[Vendor] = relationship(back_populates="documents")
    verifier: Mapped[User | None] = relationship()
