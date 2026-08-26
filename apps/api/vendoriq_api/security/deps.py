"""FastAPI dependencies: authentication, CSRF, the unit of work and ``require(...)``.

The order matters and is deliberate:

1. **Authenticate** — session cookie, else ``X-API-Key``, else anonymous.
2. **CSRF** — only for cookie-authenticated mutating requests. An API key is not sent by
   the browser automatically, so a double-submit check on it would be theatre.
3. **Authorise** — ``require("operationId")`` looks the operation up in the matrix.
4. **Scope to the vendor** — a ``vendor`` caller reaching another vendor's row gets 404,
   not 403: existence is itself information (spec §13).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import UnitOfWork, get_session
from ..errors import ApiError
from ..models import ApiKey, RevokedSession, User
from ..models.enums import UserRole
from .hashing import hash_token
from .permissions import permission_for
from .principal import Principal
from .tokens import TokenError, csrf_matches, unsign

#: Requests that change nothing skip the CSRF check.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

ANONYMOUS = Principal(kind="user", role=None)


def _unauthenticated() -> ApiError:
    return ApiError(401, "unauthenticated", "No valid session or API key.")


def _session_principal(request: Request, session: Session, settings: Settings) -> Principal | None:
    raw = request.cookies.get(settings.session_cookie)
    if not raw:
        return None
    try:
        payload = unsign(raw, settings.session_secret)
    except TokenError:
        return None
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (ValueError, TypeError):
        return None
    # Has this particular session been logged out? One primary-key lookup, and only for
    # sessions minted with a `jti` — the table holds a row per logout and only until that
    # token would have expired anyway, so a stateless session stays stateless to *establish*
    # and consults the database only to learn it has been withdrawn (3B, finding 3).
    jti = payload.get("jti")
    if jti is not None:
        try:
            revoked = session.get(RevokedSession, uuid.UUID(str(jti)))
        except (ValueError, TypeError):
            return None
        if revoked is not None:
            return None

    user = session.get(User, user_id)
    # Deactivating an account revokes every session the user has at once; logging out
    # revokes exactly the one above.
    if user is None or not user.is_active:
        return None
    return Principal(
        kind="user",
        user_id=user.id,
        email=user.email,
        role=user.role,
        vendor_id=user.vendor_id,
    )


def _api_key_principal(request: Request, session: Session) -> Principal | None:
    presented = request.headers.get("X-API-Key")
    if not presented:
        return None
    record = session.scalar(select(ApiKey).where(ApiKey.hashed_key == hash_token(presented)))
    if record is None or not record.is_active or record.revoked_at is not None:
        return None
    record.last_used_at = datetime.now(UTC)
    return Principal(
        kind="api_key",
        scopes=frozenset(str(scope) for scope in record.scopes),
        api_key_id=record.id,
        email=record.name,
    )


def get_principal(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Resolve the caller. Anonymous is a valid answer; ``require`` refuses it."""
    principal = _session_principal(request, session, settings) or _api_key_principal(
        request, session
    )
    if principal is None:
        return ANONYMOUS
    request.state.principal = principal
    return principal


def get_uow(
    session: Session = Depends(get_session),
    principal: Principal = Depends(get_principal),
) -> Iterator[UnitOfWork]:
    """One request, one transaction. Commits only when the handler returns cleanly."""
    uow = UnitOfWork(session, actor_id=principal.user_id)
    try:
        yield uow
        uow.commit()
    except Exception:
        uow.rollback()
        raise


def enforce_csrf(request: Request, settings: Settings, principal: Principal) -> None:
    """Double-submit check for cookie-authenticated mutations."""
    if request.method in SAFE_METHODS or principal.kind != "user":
        return
    if request.cookies.get(settings.session_cookie) is None:
        return
    cookie = request.cookies.get(settings.csrf_cookie)
    header = request.headers.get("X-CSRF-Token")
    if not csrf_matches(cookie, header):
        raise ApiError(403, "forbidden", "CSRF token missing or does not match the session.")


def require(operation_id: str) -> Callable[..., Principal]:
    """Dependency factory: authorise ``operation_id`` for the caller.

    Returns the principal so a handler can narrow its query without looking it up again.
    """
    permission = permission_for(operation_id)

    def dependency(
        request: Request,
        principal: Principal = Depends(get_principal),
        settings: Settings = Depends(get_settings),
    ) -> Principal:
        if principal.kind == "user" and principal.user_id is None:
            raise _unauthenticated()
        enforce_csrf(request, settings, principal)
        if not principal.may(permission):
            raise ApiError(
                403,
                "forbidden",
                f"The role or scope does not allow {operation_id}.",
                {"operation": operation_id},
            )
        request.state.operation_id = operation_id
        return principal

    return dependency


def scope_to_vendor(principal: Principal, vendor_id: uuid.UUID, operation_id: str) -> None:
    """A ``vendor`` caller may only touch its own record (spec §13, TEST_ACCOUNTS roles).

    404 rather than 403: a vendor must not be able to probe which VÖENs are in the register.
    """
    if not permission_for(operation_id).vendor_scoped:
        return
    if principal.role is UserRole.VENDOR and principal.vendor_id != vendor_id:
        raise ApiError(404, "not_found", "No such vendor, or it is outside the caller's scope.")
