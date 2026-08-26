"""Contact people. One of them owns the portal account (spec §5)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Contact, User
from . import audit

FIELDS = ("name", "position", "phone", "email", "is_primary")


def list_for(session: Session, vendor_id: uuid.UUID) -> list[Contact]:
    return list(
        session.scalars(
            select(Contact)
            .where(Contact.vendor_id == vendor_id)
            .order_by(Contact.is_primary.desc(), Contact.name.asc())
        )
    )


def get(session: Session, vendor_id: uuid.UUID, contact_id: uuid.UUID) -> Contact:
    contact = session.get(Contact, contact_id)
    if contact is None or contact.vendor_id != vendor_id:
        raise ApiError(404, "not_found", "No such contact for this vendor.")
    return contact


def has_portal_account(session: Session, contact: Contact) -> bool:
    """True when a user account authenticates as this contact's e-mail address."""
    if not contact.email:
        return False
    return (
        session.scalar(
            select(User.id).where(
                User.email == contact.email.lower(), User.vendor_id == contact.vendor_id
            )
        )
        is not None
    )


def _demote_others(session: Session, vendor_id: uuid.UUID, keep: uuid.UUID | None) -> None:
    for other in list_for(session, vendor_id):
        if other.id != keep and other.is_primary:
            other.is_primary = False


def create(uow: UnitOfWork, vendor_id: uuid.UUID, data: dict[str, Any]) -> Contact:
    contact = Contact(
        vendor_id=vendor_id,
        name=str(data["name"]).strip(),
        position=data.get("position"),
        phone=data.get("phone"),
        email=(data.get("email") or "").lower() or None,
        is_primary=bool(data.get("is_primary", False)),
    )
    uow.session.add(contact)
    uow.flush()
    if contact.is_primary:
        _demote_others(uow.session, vendor_id, contact.id)
    audit.record(
        uow,
        entity_type="contact",
        entity_id=contact.id,
        action="create",
        after=audit.snapshot(contact, FIELDS),
    )
    return contact


def patch(uow: UnitOfWork, contact: Contact, data: dict[str, Any]) -> Contact:
    before = audit.snapshot(contact, FIELDS)
    for key in FIELDS:
        if key not in data or data[key] is None:
            continue
        value = data[key]
        if key == "email":
            value = str(value).lower()
        setattr(contact, key, value)
    uow.flush()
    if contact.is_primary:
        _demote_others(uow.session, contact.vendor_id, contact.id)
    after = audit.snapshot(contact, FIELDS)
    audit.record(
        uow,
        entity_type="contact",
        entity_id=contact.id,
        action="update",
        before={key: before[key] for key in audit.diff(before, after)},
        after=audit.diff(before, after),
    )
    return contact


def delete(uow: UnitOfWork, contact: Contact) -> None:
    """The primary contact cannot go while it owns the portal account (contract)."""
    if contact.is_primary and has_portal_account(uow.session, contact):
        raise ApiError(
            409,
            "conflict",
            "The primary contact owns the portal account; transfer it before deleting.",
            {"contact_id": str(contact.id)},
        )
    before = audit.snapshot(contact, FIELDS)
    audit.record(
        uow,
        entity_type="contact",
        entity_id=contact.id,
        action="delete",
        before=before,
    )
    uow.session.delete(contact)
    uow.flush()
