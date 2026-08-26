"""API keys — the credential another product authenticates with (brief §2, spec §13).

Three properties make this a credential rather than a password field with extra steps:

1. **The plaintext exists once.** It is generated, hashed with
   :func:`~vendoriq_api.security.hashing.hash_token`, and returned in the creation response
   only. Nothing stores it, nothing can read it back, and no later endpoint returns it —
   ``ApiKey`` in the contract has no ``key`` property at all; only ``ApiKeyCreated`` does.
2. **Scopes are per module.** ``vendors:read``, ``projects:write`` … The scope a key needs
   for an operation is declared once, in ``security/permissions.py``, and the same table
   answers for people and for machines. A key can never exceed what its scopes name, and
   operations with ``scope = None`` — minting keys, creating users — are closed to every
   key by construction.
3. **Revocation is immediate.** ``revoke`` clears ``is_active`` and stamps ``revoked_at`` in
   the request's own transaction; ``security/deps.py`` checks both on *every* request, so the
   next call with that key is anonymous. There is no cache to wait on and no token lifetime
   to expire.

The key is never logged. The only place its plaintext appears is the response body of the
one request that created it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import UnitOfWork
from ..errors import ApiError
from ..models import ApiKey
from ..models.enums import Scope
from ..security.hashing import hash_token
from ..security.tokens import new_api_key
from . import audit


def list_keys(session: Session) -> list[ApiKey]:
    """Newest first, revoked ones included — a revoked key is part of the record."""
    return list(session.scalars(select(ApiKey).order_by(ApiKey.created_at.desc())))


def get(session: Session, api_key_id: uuid.UUID) -> ApiKey:
    row = session.get(ApiKey, api_key_id)
    if row is None:
        raise ApiError(404, "not_found", "No such API key.")
    return row


def create(
    uow: UnitOfWork,
    *,
    name: str,
    scopes: list[Scope],
    created_by: uuid.UUID | None = None,
) -> tuple[ApiKey, str]:
    """Mint a key. Returns ``(row, plaintext)`` — the plaintext is the caller's only copy.

    ``prefix`` (migration ``0004``) is the leading ``vq_XXXXXXXX`` of the key, stored so two
    keys are distinguishable in a list. It is a prefix of a 32-byte random body, so it
    identifies without weakening: knowing it leaves the remaining entropy untouched.
    """
    cleaned = name.strip()
    if not cleaned:
        raise ApiError(422, "validation_error", "An API key needs a name.")
    if not scopes:
        raise ApiError(
            422,
            "validation_error",
            "An API key needs at least one scope; a key that may do nothing is not a credential.",
        )
    plaintext, prefix = new_api_key()
    row = ApiKey(
        name=cleaned,
        hashed_key=hash_token(plaintext),
        prefix=prefix,
        scopes=[scope.value for scope in scopes],
        created_by=created_by,
        is_active=True,
    )
    uow.session.add(row)
    uow.flush()
    audit.record(
        uow,
        entity_type="api_key",
        entity_id=row.id,
        action="create",
        # The prefix, never the key: an audit trail is read by more people than the creator.
        after={"name": row.name, "scopes": list(row.scopes), "prefix": prefix},
    )
    return row, plaintext


def update(
    uow: UnitOfWork,
    api_key_id: uuid.UUID,
    *,
    name: str | None = None,
    scopes: list[Scope] | None = None,
    is_active: bool | None = None,
) -> ApiKey:
    """Rename, re-scope or reactivate. A revoked key is never reactivated — mint a new one."""
    row = get(uow.session, api_key_id)
    before = {"name": row.name, "scopes": list(row.scopes), "is_active": row.is_active}
    if name is not None:
        cleaned = name.strip()
        if not cleaned:
            raise ApiError(422, "validation_error", "An API key needs a name.")
        row.name = cleaned
    if scopes is not None:
        if not scopes:
            raise ApiError(422, "validation_error", "An API key needs at least one scope.")
        row.scopes = [scope.value for scope in scopes]
    if is_active is not None:
        if is_active and row.revoked_at is not None:
            raise ApiError(
                409,
                "conflict",
                "A revoked key cannot be reactivated; its plaintext is gone. Create a new key.",
            )
        row.is_active = is_active
    uow.flush()
    audit.record(
        uow,
        entity_type="api_key",
        entity_id=row.id,
        action="update",
        before=before,
        after={"name": row.name, "scopes": list(row.scopes), "is_active": row.is_active},
    )
    return row


def revoke(uow: UnitOfWork, api_key_id: uuid.UUID) -> None:
    """Refuse the key from the next request onward. The row stays, as evidence."""
    row = get(uow.session, api_key_id)
    before = {"is_active": row.is_active, "revoked_at": row.revoked_at}
    row.is_active = False
    row.revoked_at = row.revoked_at or datetime.now(UTC)
    uow.flush()
    audit.record(
        uow,
        entity_type="api_key",
        entity_id=row.id,
        action="revoke",
        before=before,
        after={"is_active": False, "revoked_at": row.revoked_at},
    )
