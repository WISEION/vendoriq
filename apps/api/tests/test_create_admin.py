"""The first user of a production stack.

`AUTH_MODE=live` seeds nothing, which is right — `create_test_accounts` refuses to run
outside test mode precisely so that a live system never grows an `admin@vendoriq.test` whose
password is published in this repository. The consequence is a freshly deployed stack with
no user at all, and no screen that could create one, because every screen is behind a
sign-in. `python -m vendoriq_api.seed create-admin` is the way out, run once by whoever
deployed, and these are the properties an operator is relying on when they do.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import User
from vendoriq_api.models.enums import UserRole
from vendoriq_api.security import hashing, totp
from vendoriq_api.services import accounts as accounts_service


def _create(uow: UnitOfWork, **overrides: object) -> tuple[User, str]:
    arguments: dict[str, object] = {
        "email": "ops@uniko.az",
        "full_name": "Uni Ko Operations",
        "role": UserRole.ADMIN,
        "password": "a-real-password",
    }
    arguments.update(overrides)
    return accounts_service.create_staff_account(uow, **arguments)  # type: ignore[arg-type]


def test_the_account_can_actually_sign_in(uow: UnitOfWork) -> None:
    """Both factors, verified against the stored values rather than the return value."""
    user, _uri = _create(uow)
    stored = uow.session.scalar(select(User).where(User.email == "ops@uniko.az"))
    assert stored is not None
    assert stored.password_hash is not None
    assert hashing.verify_password("a-real-password", stored.password_hash)
    assert stored.totp_secret is not None
    assert totp.verify(stored.totp_secret, totp.totp(stored.totp_secret))
    assert stored.id == user.id


def test_it_is_real_data_not_demo_data(uow: UnitOfWork) -> None:
    """`make purge-demo` must not delete the administrator."""
    user, _uri = _create(uow)
    assert user.is_demo is False
    assert user.is_active is True


def test_the_provisioning_uri_carries_the_secret_that_was_stored(uow: UnitOfWork) -> None:
    user, uri = _create(uow)
    assert user.totp_secret is not None
    assert user.totp_secret in uri
    assert "ops@uniko.az" in uri.replace("%40", "@")


def test_a_second_account_on_the_same_address_is_refused(uow: UnitOfWork) -> None:
    """Not "reset the password of" — that would be a takeover tool for anyone with a shell."""
    _create(uow)
    with pytest.raises(accounts_service.AccountExistsError):
        _create(uow, password="a-different-password")

    stored = uow.session.scalar(select(User).where(User.email == "ops@uniko.az"))
    assert stored is not None and stored.password_hash is not None
    assert hashing.verify_password("a-real-password", stored.password_hash)


def test_the_address_is_normalised(uow: UnitOfWork) -> None:
    """Sign-in looks the address up in lower case; storing it as typed locks the user out."""
    user, _uri = _create(uow, email="  OPS@Uniko.AZ  ")
    assert user.email == "ops@uniko.az"


def test_a_short_password_is_refused(uow: UnitOfWork) -> None:
    with pytest.raises(ValueError, match="at least"):
        _create(uow, password="short")
    assert uow.session.scalar(select(User).where(User.email == "ops@uniko.az")) is None


def test_a_vendor_account_cannot_be_created_this_way(uow: UnitOfWork) -> None:
    """Vendor accounts sign in with a one-time code and belong to a vendor row."""
    with pytest.raises(ValueError, match="one-time code"):
        _create(uow, role=UserRole.VENDOR)


@pytest.mark.parametrize("role", [UserRole.MANAGER, UserRole.COMMISSION, UserRole.OFFICER])
def test_the_other_staff_roles_are_available_too(uow: UnitOfWork, role: UserRole) -> None:
    """Deploying is not only about administrators; the commission has to get in as well."""
    user, _uri = _create(uow, email=f"{role.value}@uniko.az", role=role)
    assert user.role is role
