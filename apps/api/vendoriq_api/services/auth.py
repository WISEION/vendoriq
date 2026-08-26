"""Authentication: vendor one-time codes, staff password + TOTP, sessions (ADR-003).

``AUTH_MODE`` is the axis everything here turns on:

* ``test`` — the code is written to the server log **and** returned in ``debug_code``, and
  the vendor code ``000000`` is accepted unconditionally so the owner can click through both
  journeys without an e-mail server. A real, freshly requested code still works.
* ``live`` — SMTP delivery, ``debug_code`` always ``null``, ``000000`` is just a wrong code.

The mode is bolted shut against production in ``config.Settings`` (brief §6): the process
refuses to open a port rather than trusting anybody to notice.
"""

from __future__ import annotations

import logging
import secrets
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..db import UnitOfWork
from ..errors import ApiError
from ..models import Contact, OtpCode, User, Vendor
from ..models.enums import EventType, UserRole, VendorStatus, VendorType
from ..security import hashing
from ..security import totp as totp_module
from ..security.tokens import TokenError, new_csrf_token, sign, unsign
from . import audit, contacts, events, mail, vendors

logger = logging.getLogger("vendoriq.auth")

#: Accepted in ``AUTH_MODE=test`` for both factors, always (brief §6, ADR-003).
TEST_CODE = "000000"


@dataclass(frozen=True, slots=True)
class OtpIssue:
    """What ``/auth/otp/request`` reports back. ``debug_code`` is None in live mode."""

    email: str
    expires_at: datetime
    debug_code: str | None


@dataclass(frozen=True, slots=True)
class SessionIssue:
    """A minted session: the cookie value, the CSRF partner and when both die."""

    user: User
    token: str
    csrf_token: str
    expires_at: datetime


# ── rate limiting ───────────────────────────────────────────────────────────
# In-process, per-worker. Enough for the single-node deployment this ships to (brief §2);
# a multi-node deployment moves the counter into Postgres or Redis without changing callers.
_attempts: dict[str, list[float]] = defaultdict(list)


def _rate_limit(bucket: str, *, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    hits = [moment for moment in _attempts[bucket] if now - moment < window_seconds]
    if len(hits) >= limit:
        retry_after = int(window_seconds - (now - hits[0])) + 1
        _attempts[bucket] = hits
        raise ApiError(
            429,
            "rate_limited",
            "Too many attempts. Wait before trying again.",
            {"retry_after": retry_after},
        )
    hits.append(now)
    _attempts[bucket] = hits


def reset_rate_limits() -> None:
    """Test hook — the counters are process state, and tests must not leak into each other."""
    _attempts.clear()


# ── lookups ─────────────────────────────────────────────────────────────────
def user_by_email(session: Session, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email.strip().lower()))


# ── vendor registration ─────────────────────────────────────────────────────
def register_vendor(
    uow: UnitOfWork,
    settings: Settings,
    *,
    legal_name: str,
    voen: str,
    type: VendorType,
    contact_name: str,
    email: str,
    position: str | None = None,
    phone: str | None = None,
    locale: str = "az",
) -> tuple[Vendor, User, OtpIssue]:
    """Create the vendor, its primary contact and its portal account, then send a code."""
    address = email.strip().lower()
    if user_by_email(uow.session, address) is not None:
        raise ApiError(409, "conflict", "An account with this e-mail already exists.")

    vendor = vendors.create(
        uow,
        legal_name=legal_name,
        type=type,
        voen=voen,
        status=VendorStatus.REGISTERED,
    )
    contacts.create(
        uow,
        vendor.id,
        {
            "name": contact_name,
            "position": position,
            "phone": phone,
            "email": address,
            "is_primary": True,
        },
    )
    user = User(
        email=address,
        full_name=contact_name,
        role=UserRole.VENDOR,
        vendor_id=vendor.id,
        locale=locale if locale in {"az", "en"} else "az",
        is_active=True,
    )
    uow.session.add(user)
    uow.flush()
    audit.record(
        uow,
        entity_type="app_user",
        entity_id=user.id,
        action="create",
        after={"email": address, "role": UserRole.VENDOR.value, "vendor_id": str(vendor.id)},
    )
    return vendor, user, issue_otp(uow, settings, email=address)


# ── one-time codes ──────────────────────────────────────────────────────────
def issue_otp(uow: UnitOfWork, settings: Settings, *, email: str) -> OtpIssue:
    """Mint, hash and store a 6-digit code; log it and reveal it in test mode.

    The response is identical whether or not the address belongs to an account — the
    contract's 202 says "a code was sent *if* the address belongs to a vendor account", and
    that is the only way the endpoint stops being an account-enumeration oracle.
    """
    address = email.strip().lower()
    _rate_limit(
        f"otp:{address}",
        limit=settings.otp_rate_limit,
        window_seconds=settings.otp_rate_limit_window_seconds,
    )
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.otp_ttl_minutes)
    code = f"{secrets.randbelow(1_000_000):06d}"

    if user_by_email(uow.session, address) is not None:
        uow.session.add(
            OtpCode(email=address, code_hash=hashing.hash_token(code), expires_at=expires_at)
        )
        uow.flush()
        if settings.auth_mode == "test":
            logger.info("OTP for %s is %s (AUTH_MODE=test)", address, code)
        else:
            mail.send(
                settings,
                to=address,
                subject="VendorIQ — birdəfəlik kod / one-time code",
                body=(
                    f"Kod / code: {code}\n"
                    f"Etibarlıdır / valid for {settings.otp_ttl_minutes} minutes."
                ),
            )
    return OtpIssue(
        email=address,
        expires_at=expires_at,
        debug_code=code if settings.auth_mode == "test" else None,
    )


def verify_otp(uow: UnitOfWork, settings: Settings, *, email: str, code: str) -> User:
    """Burn a code and return its owner. Raises 401 for every failure mode alike."""
    address = email.strip().lower()
    _rate_limit(
        f"otp-verify:{address}",
        limit=settings.otp_rate_limit * 3,
        window_seconds=settings.otp_rate_limit_window_seconds,
    )
    user = user_by_email(uow.session, address)
    invalid = ApiError(401, "unauthenticated", "The code is wrong or has expired.")
    if user is None or not user.is_active:
        raise invalid

    now = datetime.now(UTC)
    candidates = list(
        uow.session.scalars(
            select(OtpCode)
            .where(
                OtpCode.email == address,
                OtpCode.consumed_at.is_(None),
                OtpCode.expires_at > now,
            )
            .order_by(OtpCode.created_at.desc())
        )
    )

    matched: OtpCode | None = None
    for candidate in candidates:
        if candidate.attempts >= settings.otp_max_attempts:
            continue
        if hashing.tokens_match(code, candidate.code_hash):
            matched = candidate
            break
        candidate.attempts += 1

    # Test mode accepts 000000 *in addition to* a real code — the owner clicks through
    # without an e-mail server, and a real code still behaves exactly as in live mode.
    if matched is None and not (settings.auth_mode == "test" and code == TEST_CODE):
        uow.flush()
        raise invalid

    if matched is not None:
        matched.consumed_at = now
    user.last_login_at = now
    uow.flush()
    audit.record(
        uow,
        entity_type="app_user",
        entity_id=user.id,
        action="login",
        after={"method": "otp", "test_code": matched is None},
        actor_id=user.id,
    )
    return user


# ── staff password + TOTP ───────────────────────────────────────────────────
def staff_login(
    uow: UnitOfWork, settings: Settings, *, email: str, password: str
) -> tuple[str, User, str | None]:
    """Check the password and mint a TOTP challenge. No session is issued yet.

    Returns ``(challenge_token, user, debug_code)``. The challenge is a signed token rather
    than a database row: it lives five minutes, carries nothing but the user id, and a
    stateless one cannot be replayed after the signature expires.
    """
    address = email.strip().lower()
    _rate_limit(
        f"login:{address}",
        limit=settings.login_rate_limit,
        window_seconds=settings.otp_rate_limit_window_seconds,
    )
    user = user_by_email(uow.session, address)
    invalid = ApiError(401, "unauthenticated", "E-mail or password is wrong.")
    if user is None or not user.is_active or user.role is UserRole.VENDOR:
        raise invalid
    if not hashing.verify_password(password, user.password_hash):
        raise invalid

    challenge = sign(
        {"sub": str(user.id), "kind": "totp"},
        settings.session_secret,
        ttl_seconds=settings.totp_challenge_ttl_seconds,
    )
    debug_code: str | None = None
    if user.totp_secret and settings.auth_mode == "test":
        debug_code = totp_module.totp(user.totp_secret, step=settings.totp_step_seconds)
        logger.info("TOTP for %s is %s (AUTH_MODE=test)", address, debug_code)
    return challenge, user, debug_code


def challenge_id(token: str) -> uuid.UUID:
    """A stable UUID for a challenge token, so the contract's ``challenge_id`` is a UUID.

    The client sends the id back; the API keeps the signed token in a short-lived,
    httpOnly cookie. That keeps the wire shape the contract declares without putting a
    bearer credential in a JSON body that a log might capture.
    """
    return uuid.uuid5(uuid.NAMESPACE_OID, token)


def verify_totp(uow: UnitOfWork, settings: Settings, *, challenge_token: str, code: str) -> User:
    """Second factor. In test mode the current code **or** ``000000`` is accepted."""
    invalid = ApiError(401, "unauthenticated", "The code is wrong or the challenge has expired.")
    try:
        payload = unsign(challenge_token, settings.session_secret)
    except TokenError as exc:
        raise invalid from exc
    if payload.get("kind") != "totp":
        raise invalid
    try:
        user = uow.session.get(User, uuid.UUID(str(payload["sub"])))
    except (ValueError, KeyError, TypeError) as exc:
        raise invalid from exc
    if user is None or not user.is_active:
        raise invalid

    accepted = False
    if user.totp_secret:
        accepted = totp_module.verify(
            user.totp_secret,
            code,
            step=settings.totp_step_seconds,
            window=settings.totp_window,
        )
    if not accepted and settings.auth_mode == "test" and code == TEST_CODE:
        accepted = True
    # An account with no enrolled secret cannot pass a second factor in live mode; in test
    # mode the seeded accounts always have one, so this is a real refusal, not a loophole.
    if not accepted:
        raise invalid

    user.last_login_at = datetime.now(UTC)
    uow.flush()
    audit.record(
        uow,
        entity_type="app_user",
        entity_id=user.id,
        action="login",
        after={"method": "password+totp"},
        actor_id=user.id,
    )
    return user


def dev_totp_code(settings: Settings, user: User) -> str | None:
    """The code for the ``X-Dev-TOTP`` header — development *and* test mode only.

    Two conditions, not one: a staging box left in test mode still refuses to print codes in
    a response header, because a header is easier to leak into a proxy log than a body.
    """
    if settings.app_env != "development" or settings.auth_mode != "test":
        return None
    if not user.totp_secret:
        return None
    return totp_module.totp(user.totp_secret, step=settings.totp_step_seconds)


# ── sessions ────────────────────────────────────────────────────────────────
def issue_session(settings: Settings, user: User) -> SessionIssue:
    """Mint the httpOnly session cookie and its readable CSRF partner."""
    ttl = settings.access_token_ttl_minutes * 60
    token = sign(
        {"sub": str(user.id), "role": user.role.value},
        settings.session_secret,
        ttl_seconds=ttl,
    )
    return SessionIssue(
        user=user,
        token=token,
        csrf_token=new_csrf_token(),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl),
    )


def notify_invitation(
    uow: UnitOfWork,
    settings: Settings,
    vendor: Vendor,
    *,
    message_az: str | None,
    message_en: str | None,
) -> None:
    """Tell the primary contact it has been invited (spec §9).

    The event is emitted whether or not there is an address to write to: the invitation
    happened, and a subscriber that only hears about the ones we could e-mail would have a
    quietly incomplete picture. A vendor imported from Excel with no contact e-mail is
    exactly the case that matters.
    """
    contact = uow.session.scalar(
        select(Contact).where(Contact.vendor_id == vendor.id, Contact.is_primary.is_(True))
    )
    address = contact.email if contact is not None else None
    events.emit(
        uow,
        EventType.VENDOR_INVITED,
        entity_type="vendor",
        entity_id=vendor.id,
        payload={"legal_name": vendor.legal_name, "email": address},
    )
    if not address:
        logger.info("vendor %s invited but has no contact e-mail; nothing sent", vendor.id)
        return
    body = "\n\n".join(part for part in (message_az, message_en) if part) or (
        "Prekvalifikasiya müraciətinə dəvət olunmusunuz. / "
        "You have been invited to a prequalification cycle."
    )
    mail.send(settings, to=address, subject="VendorIQ — dəvət / invitation", body=body)
