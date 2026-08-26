"""Fixtures for the worker's job tests.

Every job talks to the database through ``vendoriq_api.db.session_scope`` — the same
sessionmaker the worker process itself uses, not a dependency the tests can override through
FastAPI. So the isolation trick is the one ``apps/api/tests/conftest.py`` documents (one
connection, one outer transaction, a SAVEPOINT per session), with one extra step: pointing
``vendoriq_api.db.get_sessionmaker`` at a factory bound to *this test's* connection, so a job
opening "its own" session by calling ``session_scope()`` lands inside the same transaction
the test fixtures wrote to — and every write, the test's and the job's alike, rolls back at
teardown.

Point ``DATABASE_URL`` at your own database before running this suite (see the task's
environment notes) — several agents share ``vendoriq_test`` and this repo's ``vendoriq``, and
concurrent runs against either deadlock on ``uq_vendor_voen``.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Connection, create_engine
from sqlalchemy.orm import Session, sessionmaker
from vendoriq_api import db as db_module
from vendoriq_api.config import Settings, get_settings
from vendoriq_api.models import (
    Application,
    Contact,
    Document,
    QualificationCycle,
    ScoringModel,
    Vendor,
)
from vendoriq_api.models.enums import (
    ApplicationStatus,
    CycleKind,
    CycleStatus,
    DecisionKind,
    DocumentStatus,
    VendorStatus,
    VendorType,
)


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Whatever ``DATABASE_URL`` the run set — the task's own database, not a shared one."""
    return Settings(_env_file=None, app_env="development", auth_mode="test")  # type: ignore[call-arg]


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
    factory = sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    with factory() as db_session:
        yield db_session


@pytest.fixture(autouse=True)
def _jobs_use_this_transaction(
    connection: Connection, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Every ``session_scope()`` a job opens lands in this test's transaction, not a new one."""
    factory = sessionmaker(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    )
    monkeypatch.setattr(db_module, "get_sessionmaker", lambda: factory)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def make_vendor(session: Session) -> Any:
    counter = {"n": 0}

    def factory(**overrides: Any) -> Vendor:
        counter["n"] += 1
        # A ten-digit VÖEN in a range the seed and the other suites do not use.
        voen = overrides.pop("voen", f"7{counter['n']:09d}")
        vendor = Vendor(
            legal_name=overrides.pop("legal_name", _unique("Worker Test Vendor")),
            voen=voen,
            type=overrides.pop("type", VendorType.SUB),
            status=overrides.pop("status", VendorStatus.REGISTERED),
            **overrides,
        )
        session.add(vendor)
        session.commit()
        return vendor

    return factory


@pytest.fixture
def make_contact(session: Session) -> Any:
    def factory(vendor: Vendor, **overrides: Any) -> Contact:
        contact = Contact(
            vendor_id=vendor.id,
            name=overrides.pop("name", "Test Contact"),
            email=overrides.pop("email", f"{_unique('contact')}@example.test"),
            is_primary=overrides.pop("is_primary", True),
            **overrides,
        )
        session.add(contact)
        session.commit()
        return contact

    return factory


@pytest.fixture
def make_document(session: Session) -> Any:
    def factory(vendor: Vendor, **overrides: Any) -> Document:
        document = Document(
            vendor_id=vendor.id,
            code=overrides.pop("code", "A-04"),
            status=overrides.pop("status", DocumentStatus.UPLOADED),
            expiry_date=overrides.pop("expiry_date", None),
            filename=overrides.pop("filename", "certificate.pdf"),
            file_key=overrides.pop("file_key", f"{vendor.id}/doc.pdf"),
            **overrides,
        )
        session.add(document)
        session.commit()
        return document

    return factory


@pytest.fixture
def make_scoring_model(session: Session) -> Any:
    def factory(version: str = "sub-4", **overrides: Any) -> ScoringModel:
        existing = session.get(ScoringModel, version)
        if existing is not None:
            return existing
        model = ScoringModel(
            version=version,
            vendor_type=overrides.pop("vendor_type", VendorType.SUB),
            name_az=overrides.pop("name_az", "Test modeli"),
            name_en=overrides.pop("name_en", "Test model"),
            groups=overrides.pop("groups", []),
            criteria=overrides.pop("criteria", []),
            classes=overrides.pop(
                "classes", [{"cls": "C", "min": 70, "label_az": "C", "label_en": "C"}]
            ),
            **overrides,
        )
        session.add(model)
        session.commit()
        return model

    return factory


@pytest.fixture
def make_cycle(session: Session, make_scoring_model: Any) -> Any:
    def factory(**overrides: Any) -> QualificationCycle:
        version = overrides.pop("scoring_model_version", "sub-4")
        make_scoring_model(version=version)
        cycle = QualificationCycle(
            name=overrides.pop("name", _unique("Cycle")),
            kind=overrides.pop("kind", CycleKind.PERIODIC),
            scoring_model_version=version,
            status=overrides.pop("status", CycleStatus.OPEN),
            **overrides,
        )
        session.add(cycle)
        session.commit()
        return cycle

    return factory


@pytest.fixture
def make_application(session: Session, make_cycle: Any) -> Any:
    def factory(
        vendor: Vendor, cycle: QualificationCycle | None = None, **overrides: Any
    ) -> Application:
        application = Application(
            vendor_id=vendor.id,
            cycle_id=(cycle or make_cycle()).id,
            status=overrides.pop("status", ApplicationStatus.PREQUALIFIED),
            decision=overrides.pop("decision", DecisionKind.APPROVE),
            **overrides,
        )
        session.add(application)
        session.commit()
        return application

    return factory
