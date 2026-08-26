"""The seeded test accounts (docs/TEST_ACCOUNTS.md, brief §6)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_api.config import Settings
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import User, Vendor
from vendoriq_api.models.enums import UserRole
from vendoriq_api.services import accounts


def test_create_test_accounts_seeds_every_documented_row(
    uow: UnitOfWork, settings: Settings, session: Session
) -> None:
    """docs/TEST_ACCOUNTS.md is the specification; this asserts the code matches it."""
    created = accounts.create_test_accounts(uow, settings)
    emails = {user.email for user, _ in created}
    assert emails == {
        "admin@vendoriq.test",
        "manager@vendoriq.test",
        "commission@vendoriq.test",
        "officer@vendoriq.test",
        "habib.atakisiyev@wesa.az",
        "a.tabit@shield.az",
        "vendor.new@vendoriq.test",
    }
    by_email = {user.email: user for user, _ in created}
    assert by_email["admin@vendoriq.test"].role is UserRole.ADMIN
    assert by_email["manager@vendoriq.test"].role is UserRole.MANAGER
    assert by_email["commission@vendoriq.test"].role is UserRole.COMMISSION
    assert by_email["officer@vendoriq.test"].role is UserRole.OFFICER
    assert by_email["habib.atakisiyev@wesa.az"].role is UserRole.VENDOR


def test_staff_accounts_get_a_password_and_a_totp_secret(
    uow: UnitOfWork, settings: Settings
) -> None:
    created = {
        user.email: (user, uri) for user, uri in accounts.create_test_accounts(uow, settings)
    }
    for email in (
        "admin@vendoriq.test",
        "manager@vendoriq.test",
        "commission@vendoriq.test",
        "officer@vendoriq.test",
    ):
        user, uri = created[email]
        assert user.password_hash
        assert user.totp_secret
        assert uri is not None and uri.startswith("otpauth://totp/")


def test_vendor_accounts_have_no_password(uow: UnitOfWork, settings: Settings) -> None:
    """Vendors authenticate with a one-time code only (brief §2)."""
    created = {user.email: user for user, _ in accounts.create_test_accounts(uow, settings)}
    for email in ("habib.atakisiyev@wesa.az", "a.tabit@shield.az", "vendor.new@vendoriq.test"):
        user = created[email]
        assert user.password_hash is None
        assert user.totp_secret is None


def test_a_real_vendor_account_is_left_unattached_until_the_register_is_loaded(
    uow: UnitOfWork, settings: Settings
) -> None:
    """The account must not fabricate a stand-in that would steal the real VÖEN.

    ``make seed`` loads the 13 real vendors and then seeds the accounts; running the seed in
    the other order used to leave a placeholder holding ``1003915341``, and the real Wesa row
    then failed the unique constraint. The account waits instead.
    """
    created = {user.email: user for user, _ in accounts.create_test_accounts(uow, settings)}
    assert created["habib.atakisiyev@wesa.az"].vendor_id is None
    # …and the one account with no real counterpart does get a demo vendor of its own.
    assert created["vendor.new@vendoriq.test"].vendor_id is not None


def test_re_seeding_links_the_account_once_the_vendor_exists(
    uow: UnitOfWork, settings: Settings, make_vendor: Any
) -> None:
    first = {user.email: user for user, _ in accounts.create_test_accounts(uow, settings)}
    assert first["a.tabit@shield.az"].vendor_id is None

    shield = make_vendor(legal_name="Shield", voen="2002138471")
    second = {user.email: user for user, _ in accounts.create_test_accounts(uow, settings)}
    assert second["a.tabit@shield.az"].vendor_id == shield.id


def test_the_seed_attaches_to_the_real_vendor_when_it_is_already_loaded(
    uow: UnitOfWork, settings: Settings, make_vendor: Any
) -> None:
    """`make seed` loads the 13 real vendors first; Wesa's account must find Wesa."""
    wesa = make_vendor(legal_name="VVESA MMC (Wesa)", voen="1003915341")
    created = {user.email: user for user, _ in accounts.create_test_accounts(uow, settings)}
    assert created["habib.atakisiyev@wesa.az"].vendor_id == wesa.id


def test_the_placeholder_vendor_is_flagged_demo(uow: UnitOfWork, settings: Settings) -> None:
    """ "A new, empty vendor" has no real counterpart, so `make purge-demo` takes it."""
    created = {user.email: user for user, _ in accounts.create_test_accounts(uow, settings)}
    vendor = uow.session.get(Vendor, created["vendor.new@vendoriq.test"].vendor_id)
    assert vendor is not None and vendor.is_demo is True


def test_seeding_twice_is_idempotent(uow: UnitOfWork, settings: Settings, session: Session) -> None:
    """`make seed` is run repeatedly; a second run must not duplicate or re-enrol."""
    first = accounts.create_test_accounts(uow, settings)
    secrets_before = {user.email: user.totp_secret for user, _ in first}
    hashes_before = {user.email: user.password_hash for user, _ in first}

    second = accounts.create_test_accounts(uow, settings)
    assert {user.id for user, _ in first} == {user.id for user, _ in second}
    for user, _ in second:
        # Re-seeding must not invalidate an authenticator app that is already enrolled.
        assert user.totp_secret == secrets_before[user.email]
        assert user.password_hash == hashes_before[user.email]

    total = len(list(session.scalars(select(User).where(User.email == "admin@vendoriq.test"))))
    assert total == 1


def test_seeding_is_refused_outside_test_mode(uow: UnitOfWork, settings: Settings) -> None:
    """ADR-003: these accounts exist only while AUTH_MODE=test."""
    live = Settings(  # type: ignore[call-arg]
        _env_file=None,
        app_env="development",
        auth_mode="live",
        database_url=settings.database_url,
        session_secret=settings.session_secret,
    )
    with pytest.raises(accounts.TestModeRequiredError):
        accounts.create_test_accounts(uow, live)


def test_the_seeded_accounts_can_actually_log_in(
    uow: UnitOfWork, settings: Settings, client: TestClient
) -> None:
    """The point of the whole exercise: the owner clicks through without an e-mail server."""
    accounts.create_test_accounts(uow, settings)
    uow.commit()

    staff = client.post(
        "/api/auth/staff/login",
        json={"email": "manager@vendoriq.test", "password": "Manager!2026"},
    )
    assert staff.status_code == 200, staff.text
    session_response = client.post(
        "/api/auth/staff/totp/verify",
        json={"challenge_id": staff.json()["challenge_id"], "code": "000000"},
    )
    assert session_response.status_code == 200
    assert session_response.json()["user"]["role"] == "manager"

    client.post("/api/auth/logout")
    client.cookies.clear()

    vendor = client.post(
        "/api/auth/otp/verify",
        json={"email": "habib.atakisiyev@wesa.az", "code": "000000"},
    )
    assert vendor.status_code == 200
    assert vendor.json()["user"]["role"] == "vendor"


def test_purge_removes_them_again(uow: UnitOfWork, settings: Settings, session: Session) -> None:
    accounts.create_test_accounts(uow, settings)
    removed = accounts.purge_test_accounts(uow)
    assert removed == len(accounts.TEST_ACCOUNTS)
    assert session.scalar(select(User).where(User.email == "admin@vendoriq.test")) is None
