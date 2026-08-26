"""Auth endpoints (contract paths ``/auth/*``, ADR-003).

The TOTP challenge is split between two carriers on purpose: the contract's
``challenge_id`` is a UUID in the body, and the signed token it stands for rides in a
short-lived httpOnly cookie. A bearer credential in a JSON body ends up in a browser
history, a proxy log or a screenshot; the id does not.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response, status

from ..config import Settings, get_settings
from ..db import UnitOfWork
from ..errors import ApiError
from ..models import User as UserRow
from ..models.enums import Scope, UserRole
from ..schemas import (
    Me,
    OtpChallenge,
    OtpRequest,
    OtpVerification,
    Session,
    StaffLogin,
    TotpChallenge,
    TotpVerification,
    User,
    VendorRegistration,
)
from ..security import Principal, get_principal, get_uow
from ..services import auth as auth_service
from ..services import users as users_service

#: Stand-in id for an API-key identity, which has no ``app_user`` row.
_ZERO_UUID = uuid.UUID(int=0)

router = APIRouter(tags=["auth"])

#: Carries the signed TOTP challenge between the two staff-login calls.
CHALLENGE_COOKIE = "vendoriq_totp_challenge"


def user_payload(uow_session: object, user: UserRow, vendor_name: str | None = None) -> User:
    return User(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        vendor_id=user.vendor_id,
        vendor_name=vendor_name,
        locale="en" if user.locale == "en" else "az",
        is_active=user.is_active,
        has_totp=bool(user.totp_secret),
        last_login_at=user.last_login_at,
    )


def _set_session_cookies(
    response: Response, settings: Settings, issued: auth_service.SessionIssue
) -> None:
    max_age = settings.access_token_ttl_minutes * 60
    secure = settings.app_env != "development"
    response.set_cookie(
        settings.session_cookie,
        issued.token,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )
    # Deliberately readable: the script has to copy it into X-CSRF-Token for the
    # double-submit check to mean anything.
    response.set_cookie(
        settings.csrf_cookie,
        issued.csrf_token,
        max_age=max_age,
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
    )
    response.delete_cookie(CHALLENGE_COOKIE, path="/")


@router.post("/auth/vendor/register", status_code=status.HTTP_201_CREATED)
def register_vendor(
    body: VendorRegistration,
    uow: UnitOfWork = Depends(get_uow),
    settings: Settings = Depends(get_settings),
) -> OtpChallenge:
    """Self-registration: vendor, primary contact, portal account, first code."""
    _, _, issue = auth_service.register_vendor(
        uow,
        settings,
        legal_name=body.legal_name,
        voen=body.voen,
        type=body.type,
        contact_name=body.contact_name,
        email=body.email,
        position=body.position,
        phone=body.phone,
        locale=body.locale,
    )
    return OtpChallenge(email=issue.email, expires_at=issue.expires_at, debug_code=issue.debug_code)


@router.post("/auth/otp/request", status_code=status.HTTP_202_ACCEPTED)
def request_otp(
    body: OtpRequest,
    uow: UnitOfWork = Depends(get_uow),
    settings: Settings = Depends(get_settings),
) -> OtpChallenge:
    """Always 202, whether or not the address exists — no enumeration oracle."""
    issue = auth_service.issue_otp(uow, settings, email=body.email)
    return OtpChallenge(email=issue.email, expires_at=issue.expires_at, debug_code=issue.debug_code)


@router.post("/auth/otp/verify")
def verify_otp(
    body: OtpVerification,
    response: Response,
    uow: UnitOfWork = Depends(get_uow),
    settings: Settings = Depends(get_settings),
) -> Session:
    user = auth_service.verify_otp(uow, settings, email=body.email, code=body.code)
    issued = auth_service.issue_session(settings, user)
    _set_session_cookies(response, settings, issued)
    return Session(
        user=user_payload(uow.session, user, users_service.vendor_name(uow.session, user)),
        expires_at=issued.expires_at,
        csrf_token=issued.csrf_token,
    )


@router.post("/auth/staff/login")
def staff_login(
    body: StaffLogin,
    response: Response,
    uow: UnitOfWork = Depends(get_uow),
    settings: Settings = Depends(get_settings),
) -> TotpChallenge:
    """Password accepted → second factor required. No session yet (contract)."""
    challenge, user, debug_code = auth_service.staff_login(
        uow, settings, email=body.email, password=body.password
    )
    response.set_cookie(
        CHALLENGE_COOKIE,
        challenge,
        max_age=settings.totp_challenge_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.app_env != "development",
        path="/",
    )
    # Development convenience: the current code, in a header the dev banner reads. Gated on
    # APP_ENV=development *and* AUTH_MODE=test, so staging never emits it.
    dev_code = auth_service.dev_totp_code(settings, user)
    if dev_code is not None:
        response.headers["X-Dev-TOTP"] = dev_code
    return TotpChallenge(
        challenge_id=auth_service.challenge_id(challenge),
        totp_required=True,
        debug_code=debug_code,
    )


@router.post("/auth/staff/totp/verify")
def verify_totp(
    body: TotpVerification,
    request: Request,
    response: Response,
    uow: UnitOfWork = Depends(get_uow),
    settings: Settings = Depends(get_settings),
) -> Session:
    challenge = request.cookies.get(CHALLENGE_COOKIE)
    if not challenge:
        raise ApiError(
            401, "unauthenticated", "No pending login challenge; start with /auth/staff/login."
        )
    if auth_service.challenge_id(challenge) != body.challenge_id:
        raise ApiError(401, "unauthenticated", "The challenge does not match this session.")
    user = auth_service.verify_totp(uow, settings, challenge_token=challenge, code=body.code)
    issued = auth_service.issue_session(settings, user)
    _set_session_cookies(response, settings, issued)
    return Session(
        user=user_payload(uow.session, user, users_service.vendor_name(uow.session, user)),
        expires_at=issued.expires_at,
        csrf_token=issued.csrf_token,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    uow: UnitOfWork = Depends(get_uow),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Withdraw this session, then clear the cookies.

    Clearing cookies used to be the whole of it, on the reasoning that the session carries no
    server state. It does not — but the *token* does not stop existing when the browser
    forgets it, and one captured beforehand kept authenticating for the rest of its eight
    hours (3B, finding 3). `revoke_session` records this token's `jti`; `_session_principal`
    refuses it from the next request on.

    No authentication is required to reach this endpoint, and that is deliberate: the caller
    can only revoke a session they already hold the cookie for, and an expired or malformed
    cookie revokes nothing. Logging out must not be able to fail.
    """
    auth_service.revoke_session(uow, settings, request.cookies.get(settings.session_cookie))
    response.delete_cookie(settings.session_cookie, path="/")
    response.delete_cookie(settings.csrf_cookie, path="/")
    response.delete_cookie(CHALLENGE_COOKIE, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/auth/me")
def get_me(
    uow: UnitOfWork = Depends(get_uow),
    principal: Principal = Depends(get_principal),
    settings: Settings = Depends(get_settings),
) -> Me:
    """Identity plus the operation ids it may call — the frontend hides, the server enforces."""
    if principal.kind == "api_key":
        # A machine has no account row; it still deserves a truthful answer about itself.
        return Me(
            id=principal.api_key_id or _ZERO_UUID,
            email=principal.email or "api-key",
            full_name=principal.email,
            role=UserRole.ADMIN if Scope.ADMIN_WRITE in principal.scopes else UserRole.OFFICER,
            is_active=True,
            permissions=principal.permitted_operations(),
            auth_mode=settings.auth_mode,
        )
    if principal.user_id is None:
        raise ApiError(401, "unauthenticated", "No valid session or API key.")
    user = users_service.get(uow.session, principal.user_id)
    payload = user_payload(uow.session, user, users_service.vendor_name(uow.session, user))
    return Me(
        **payload.model_dump(),
        permissions=principal.permitted_operations(),
        auth_mode=settings.auth_mode,
    )
