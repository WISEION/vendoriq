"""Seeded test accounts (docs/TEST_ACCOUNTS.md, brief §6).

``create_test_accounts`` is idempotent and is called by the seed CLI (phase 1E). It refuses
to run outside ``AUTH_MODE=test``: the whole point of the mode is that these accounts exist
only while it is on, and a live system that quietly grew an ``admin@vendoriq.test`` with a
published password would be the worst possible outcome of a convenience feature.

The vendor accounts are attached to existing vendors by e-mail — the seed loads the real
13 vendors first, so ``habib.atakisiyev@wesa.az`` finds Wesa. When the vendor is not there
yet, the account is created without one and the seed's second pass links it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select

from ..config import Settings
from ..db import UnitOfWork
from ..models import Contact, User, Vendor
from ..models.enums import UserRole, VendorStatus, VendorType
from ..security import hashing
from ..security import totp as totp_module
from . import audit

logger = logging.getLogger("vendoriq.seed")


@dataclass(frozen=True, slots=True)
class TestAccount:
    """One row of ``docs/TEST_ACCOUNTS.md``."""

    email: str
    role: UserRole
    full_name: str
    password: str | None = None
    #: Legal name of the vendor a portal account belongs to, when it has to be created.
    vendor_legal_name: str | None = None
    vendor_voen: str | None = None


STAFF_ACCOUNTS: tuple[TestAccount, ...] = (
    TestAccount("admin@vendoriq.test", UserRole.ADMIN, "VendorIQ Admin", "Admin!2026"),
    TestAccount("manager@vendoriq.test", UserRole.MANAGER, "VendorIQ Manager", "Manager!2026"),
    TestAccount(
        "commission@vendoriq.test", UserRole.COMMISSION, "VendorIQ Commission", "Commission!2026"
    ),
    TestAccount("officer@vendoriq.test", UserRole.OFFICER, "VendorIQ Officer", "Officer!2026"),
)

VENDOR_ACCOUNTS: tuple[TestAccount, ...] = (
    TestAccount(
        "habib.atakisiyev@wesa.az",
        UserRole.VENDOR,
        "Həbib Atakişiyev",
        vendor_legal_name="VVESA MMC (Wesa)",
        vendor_voen="1003915341",
    ),
    TestAccount(
        "a.tabit@shield.az",
        UserRole.VENDOR,
        "A. Tabit",
        vendor_legal_name="Shield",
        vendor_voen="2002138471",
    ),
    TestAccount(
        "vendor.new@vendoriq.test",
        UserRole.VENDOR,
        "Yeni Təchizatçı",
        vendor_legal_name="Yeni Vendor MMC",
        vendor_voen=None,
    ),
)

TEST_ACCOUNTS: tuple[TestAccount, ...] = STAFF_ACCOUNTS + VENDOR_ACCOUNTS


class TestModeRequiredError(RuntimeError):
    """Raised when the seed is asked to create test accounts outside ``AUTH_MODE=test``."""


def _find_vendor(uow: UnitOfWork, account: TestAccount) -> Vendor | None:
    if account.vendor_voen:
        found = uow.session.scalar(select(Vendor).where(Vendor.voen == account.vendor_voen))
        if found is not None:
            return found
    if account.vendor_legal_name:
        return uow.session.scalar(
            select(Vendor).where(Vendor.legal_name == account.vendor_legal_name)
        )
    return None


def _ensure_vendor(uow: UnitOfWork, account: TestAccount) -> Vendor | None:
    """Find the seeded vendor, or create the one account that has no real counterpart.

    An account that names a **real** vendor (Wesa, Shield) is never given a fabricated
    stand-in: its VÖEN belongs to a row `make seed` is about to load, and inventing a
    placeholder here would take that VÖEN and make the real load fail on the unique
    constraint. Such an account is created unattached, and re-running the seed after the
    register is loaded links it. Only `vendor.new@vendoriq.test` — which the documentation
    describes as "a new, empty vendor" and which has no VÖEN — gets a row of its own.
    """
    existing = _find_vendor(uow, account)
    if existing is not None:
        return existing
    if account.vendor_legal_name is None or account.vendor_voen is not None:
        return None
    vendor = Vendor(
        legal_name=account.vendor_legal_name,
        voen=account.vendor_voen,
        type=VendorType.SUB,
        status=VendorStatus.REGISTERED,
        is_demo=True,
    )
    uow.session.add(vendor)
    uow.flush()
    uow.session.add(
        Contact(
            vendor_id=vendor.id,
            name=account.full_name,
            email=account.email,
            is_primary=True,
            is_demo=True,
        )
    )
    uow.flush()
    return vendor


def create_test_accounts(uow: UnitOfWork, settings: Settings) -> list[tuple[User, str | None]]:
    """Create or refresh the accounts of ``docs/TEST_ACCOUNTS.md``.

    Returns ``[(user, otpauth_uri | None)]``. The TOTP URI is printed once by the seed CLI —
    the secret is not retrievable afterwards through any endpoint.

    Idempotent: an existing account has its password, role and TOTP secret left alone unless
    they are missing, so re-running ``make seed`` does not invalidate an enrolled
    authenticator app.
    """
    if settings.auth_mode != "test":
        raise TestModeRequiredError(
            "Test accounts exist only while AUTH_MODE=test (docs/TEST_ACCOUNTS.md)."
        )

    created: list[tuple[User, str | None]] = []
    for account in TEST_ACCOUNTS:
        user = uow.session.scalar(select(User).where(User.email == account.email))
        vendor = _ensure_vendor(uow, account) if account.role is UserRole.VENDOR else None
        is_new = user is None

        if user is None:
            user = User(
                email=account.email,
                full_name=account.full_name,
                role=account.role,
                is_demo=True,
            )
            uow.session.add(user)

        user.role = account.role
        user.is_active = True
        user.vendor_id = vendor.id if vendor is not None else None
        if account.password and not user.password_hash:
            user.password_hash = hashing.hash_password(account.password)
        if account.role is not UserRole.VENDOR and not user.totp_secret:
            user.totp_secret = totp_module.generate_secret()
        uow.flush()

        uri = (
            totp_module.provisioning_uri(user.totp_secret, user.email) if user.totp_secret else None
        )
        if is_new:
            audit.record(
                uow,
                entity_type="app_user",
                entity_id=user.id,
                action="seed",
                after={"email": user.email, "role": user.role.value},
            )
            logger.info("seeded %s account %s", user.role.value, user.email)
        created.append((user, uri))
    return created


def purge_test_accounts(uow: UnitOfWork) -> int:
    """Remove the seeded accounts — what switching to ``AUTH_MODE=live`` implies."""
    removed = 0
    for account in TEST_ACCOUNTS:
        user = uow.session.scalar(select(User).where(User.email == account.email))
        if user is None:
            continue
        uow.session.delete(user)
        removed += 1
    uow.flush()
    return removed
