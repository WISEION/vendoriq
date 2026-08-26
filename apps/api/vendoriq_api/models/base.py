"""Declarative base, shared column types and mixins."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, ClassVar

from sqlalchemy import DateTime, MetaData, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

#: Deterministic constraint names so Alembic autogenerate produces stable diffs.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

#: JSONB payloads are declared as ``Mapped[dict[str, Any]]`` / ``Mapped[list[Any]]``.
JsonDict = dict[str, Any]
JsonList = list[Any]


class Base(DeclarativeBase):
    """Base class of every VendorIQ table."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map: ClassVar[dict[Any, Any]] = {
        JsonDict: JSONB,
        JsonList: JSONB,
        datetime: DateTime(timezone=True),
        uuid.UUID: Uuid(as_uuid=True),
    }


def uuid_pk() -> Mapped[uuid.UUID]:
    """Primary key column: application-generated UUID v4 (stable cross-system id)."""
    return mapped_column(primary_key=True, default=uuid.uuid4)


def pg_enum(enum_cls: type, name: str) -> SAEnum:
    """Native PostgreSQL enum type that stores the *value* of a ``StrEnum``."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
        validate_strings=True,
    )


class TimestampMixin:
    """``created_at`` / ``updated_at`` maintained by the database clock."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
