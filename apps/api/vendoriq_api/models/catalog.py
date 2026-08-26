"""Category taxonomy and the vendor↔category assignment (spec §5)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, pg_enum, uuid_pk
from .enums import CategoryKind

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .vendor import Vendor


class Category(Base, TimestampMixin):
    """Work package or material group; a two-level tree via ``parent_id``."""

    __tablename__ = "category"

    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name_az: Mapped[str] = mapped_column(String(255), nullable=False)
    name_en: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[CategoryKind] = mapped_column(
        pg_enum(CategoryKind, "category_kind"), nullable=False, index=True
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("category.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    parent: Mapped[Category | None] = relationship(remote_side="Category.id")


class VendorCategory(Base, TimestampMixin):
    """Vendor selects, officer confirms (``confirmed``)."""

    __tablename__ = "vendor_category"
    __table_args__ = (UniqueConstraint("vendor_id", "category_id"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("category.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Only confirmed categories are candidates in project matching (spec §11.1).
    confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    vendor: Mapped[Vendor] = relationship(back_populates="categories")
    category: Mapped[Category] = relationship()
