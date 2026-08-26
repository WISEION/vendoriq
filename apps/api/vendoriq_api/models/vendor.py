"""Vendor and contact records (spec §5)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, pg_enum, uuid_pk
from .enums import VendorStatus, VendorType

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .catalog import VendorCategory
    from .document import Document
    from .observation import FieldObservation
    from .qualification import Application


class Vendor(Base, TimestampMixin):
    """One record per legal entity, regardless of how many cycles it took part in."""

    __tablename__ = "vendor"
    __table_args__ = (
        CheckConstraint("voen ~ '^[0-9]{10}$'", name="voen_ten_digits"),
        Index("ix_vendor_status_type", "status", "type"),
        Index("ix_vendor_legal_name_lower", text("lower(legal_name)")),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: Azerbaijani tax id — exactly ten digits, unique across the register.
    voen: Mapped[str | None] = mapped_column(String(10), unique=True, nullable=True)
    type: Mapped[VendorType] = mapped_column(
        pg_enum(VendorType, "vendor_type"), nullable=False, default=VendorType.SUB
    )
    legal_form: Mapped[str | None] = mapped_column(String(64))
    registration_year: Mapped[int | None] = mapped_column(Integer)
    address: Mapped[str | None] = mapped_column(String(512))
    region: Mapped[str | None] = mapped_column(String(128))
    website: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[VendorStatus] = mapped_column(
        pg_enum(VendorStatus, "vendor_status"),
        nullable=False,
        default=VendorStatus.REGISTERED,
        index=True,
    )
    #: Stable id of this vendor in a foreign system (ERP, other product).
    external_ref: Mapped[str | None] = mapped_column(String(128), index=True)
    #: Demo rows are removable with ``make purge-demo``.
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    contacts: Mapped[list[Contact]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )
    categories: Mapped[list[VendorCategory]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )
    observations: Mapped[list[FieldObservation]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(back_populates="vendor")


class Contact(Base, TimestampMixin):
    """Contact person at a vendor; one of them owns the portal account."""

    __tablename__ = "contact"

    id: Mapped[uuid.UUID] = uuid_pk()
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[str | None] = mapped_column(String(128))
    phone: Mapped[str | None] = mapped_column(String(64))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    vendor: Mapped[Vendor] = relationship(back_populates="contacts")
