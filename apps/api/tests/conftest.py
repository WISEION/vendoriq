"""Test fixtures.

**Isolation strategy: one transaction per test, rolled back at the end.** The session is
bound to a connection with an open transaction and a SAVEPOINT under it, so a service that
commits (every mutating one does, through the unit of work) only releases the savepoint —
the outer transaction is never committed and the rollback at teardown takes everything with
it. No truncation, no ordering dependencies, and tests can run against a database that
already holds seed data.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine
from sqlalchemy.orm import Session, sessionmaker
from vendoriq_api.config import Settings, get_settings
from vendoriq_api.db import UnitOfWork, get_session
from vendoriq_api.main import create_app
from vendoriq_api.models import Category, User, Vendor
from vendoriq_api.models.enums import CategoryKind, UserRole, VendorType
from vendoriq_api.security import hashing
from vendoriq_api.security import totp as totp_module
from vendoriq_api.services import auth as auth_service
from vendoriq_api.storage import get_storage
from vendoriq_api.storage.local import LocalStorage

#: Passwords the staff fixtures log in with. Deliberately not the seeded ones — a test that
#: passes only because ``make seed`` ran is not a test.
PASSWORD = "Test!2026"


@pytest.fixture(scope="session")
def password() -> str:
    """Exposed as a fixture rather than imported: two test packages in this repo ship a
    ``conftest.py``, and ``from conftest import …`` binds to whichever one is first on
    ``sys.path`` when the whole suite runs."""
    return PASSWORD


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """Test-mode settings against ``vendoriq_test`` and a throwaway storage directory."""
    base = Settings(_env_file=None)  # type: ignore[call-arg]
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="development",
        auth_mode="test",
        database_url=base.test_database_url,
        session_secret="test-secret-not-used-anywhere-real",
        storage_backend="local",
        storage_local_dir=tmp_path_factory.mktemp("storage"),
    )


@pytest.fixture(scope="session")
def engine(settings: Settings) -> Iterator[Any]:
    created = create_engine(settings.database_url, future=True)
    yield created
    created.dispose()


@pytest.fixture
def connection(engine: Any) -> Iterator[Connection]:
    """One connection per test, inside a transaction that is always rolled back."""
    conn = engine.connect()
    transaction = conn.begin()
    try:
        yield conn
    finally:
        transaction.rollback()
        conn.close()


@pytest.fixture
def session(connection: Connection) -> Iterator[Session]:
    """A session whose commits land on a savepoint, not on the outer transaction.

    ``expire_on_commit=False`` matches the application's own sessionmaker, so a factory can
    keep using an object after committing it.
    """
    factory = sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    with factory() as db_session:
        yield db_session


@pytest.fixture
def uow(session: Session) -> UnitOfWork:
    return UnitOfWork(session)


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    """The OTP counters are process state; a leak makes the next test fail with 429."""
    auth_service.reset_rate_limits()
    yield
    auth_service.reset_rate_limits()


@pytest.fixture(scope="session")
def storage(settings: Settings) -> LocalStorage:
    """The backend the API hands out during tests — rooted in a temporary directory."""
    return LocalStorage(
        settings.storage_local_dir,
        secret=settings.session_secret,
        url_prefix=f"{settings.api_prefix}/storage",
    )


@pytest.fixture
def app(settings: Settings, session: Session, storage: LocalStorage) -> Iterator[Any]:
    """The real application, with the settings and session overridden onto the test ones."""
    get_settings.cache_clear()
    get_storage.cache_clear()
    application = create_app()
    application.dependency_overrides[get_settings] = lambda: settings
    application.dependency_overrides[get_session] = lambda: session
    # ``get_storage`` reads ``get_settings()`` itself rather than through the dependency
    # graph, so without this override the document tests would write into the repository's
    # own ``var/storage`` instead of the per-session temporary directory.
    application.dependency_overrides[get_storage] = lambda: storage
    yield application
    application.dependency_overrides.clear()
    get_settings.cache_clear()
    get_storage.cache_clear()


@pytest.fixture
def client(app: Any) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


# ── data factories ──────────────────────────────────────────────────────────
def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def make_vendor(session: Session) -> Any:
    counter = {"n": 0}

    def factory(**overrides: Any) -> Vendor:
        counter["n"] += 1
        # A ten-digit VÖEN that cannot collide with the seeded register.
        voen = overrides.pop("voen", f"9{counter['n']:09d}")
        vendor = Vendor(
            legal_name=overrides.pop("legal_name", _unique("Test Vendor")),
            voen=voen,
            type=overrides.pop("type", VendorType.SUB),
            **overrides,
        )
        session.add(vendor)
        session.commit()
        return vendor

    return factory


@pytest.fixture
def make_user(session: Session) -> Any:
    def factory(
        role: UserRole,
        *,
        vendor: Vendor | None = None,
        password: str | None = PASSWORD,
        with_totp: bool = True,
        is_active: bool = True,
    ) -> User:
        user = User(
            email=_unique(f"{role.value}") + "@vendoriq.test",
            full_name=f"Test {role.value}",
            role=role,
            vendor_id=vendor.id if vendor is not None else None,
            is_active=is_active,
            password_hash=(
                hashing.hash_password(password)
                if password and role is not UserRole.VENDOR
                else None
            ),
            totp_secret=(
                totp_module.generate_secret() if with_totp and role is not UserRole.VENDOR else None
            ),
        )
        session.add(user)
        session.commit()
        return user

    return factory


@pytest.fixture
def make_category(session: Session) -> Any:
    def factory(code: str | None = None, kind: CategoryKind = CategoryKind.WORK) -> Category:
        category = Category(
            code=code or _unique("cat"),
            name_az="Test kateqoriya",
            name_en="Test category",
            kind=kind,
        )
        session.add(category)
        session.commit()
        return category

    return factory


@pytest.fixture
def login(client: TestClient, settings: Settings) -> Any:
    """Log a user in and return the CSRF token the client must echo on mutations."""

    def _login(user: User) -> str:
        if user.role is UserRole.VENDOR:
            client.post("/api/auth/otp/request", json={"email": user.email})
            response = client.post(
                "/api/auth/otp/verify", json={"email": user.email, "code": "000000"}
            )
        else:
            first = client.post(
                "/api/auth/staff/login", json={"email": user.email, "password": PASSWORD}
            )
            assert first.status_code == 200, first.text
            response = client.post(
                "/api/auth/staff/totp/verify",
                json={"challenge_id": first.json()["challenge_id"], "code": "000000"},
            )
        assert response.status_code == 200, response.text
        token: str = response.json()["csrf_token"]
        client.headers["X-CSRF-Token"] = token
        return token

    return _login


@pytest.fixture
def logout(client: TestClient) -> Any:
    def _logout() -> None:
        client.post("/api/auth/logout")
        client.cookies.clear()
        client.headers.pop("X-CSRF-Token", None)

    return _logout
