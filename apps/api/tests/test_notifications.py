"""Bilingual notifications: templates, recipient resolution and once-only delivery.

Brief §2G. Boundaries are pinned against a fixed calendar date (the house style — see
``test_documents.py``'s ``TODAY``), never ``sleep``.
"""

from __future__ import annotations

import smtplib
from datetime import date
from types import TracebackType
from typing import Any, ClassVar

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from vendoriq_api.config import Settings
from vendoriq_api.db import UnitOfWork
from vendoriq_api.models import AuditEvent, Contact, Document, Event, User, Vendor
from vendoriq_api.models.enums import DecisionKind, DocumentStatus, EventType, UserRole
from vendoriq_api.services import notifications

TODAY = date(2026, 8, 26)


def _settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, app_env="development", auth_mode="test", **overrides)  # type: ignore[call-arg]


def _contact(session: Session, vendor: Vendor, *, email: str = "buyer@vendor.test") -> Contact:
    contact = Contact(vendor_id=vendor.id, name="Test Contact", email=email, is_primary=True)
    session.add(contact)
    session.commit()
    return contact


def _document(
    session: Session, vendor: Vendor, *, code: str = "A-04", expiry_date: date | None
) -> Document:
    document = Document(
        vendor_id=vendor.id,
        code=code,
        status=DocumentStatus.UPLOADED,
        expiry_date=expiry_date,
        filename="certificate.pdf",
        file_key=f"{vendor.id}/{code}.pdf",
    )
    session.add(document)
    session.commit()
    return document


# ── templates render both languages with real data ─────────────────────────
def test_document_expiring_renders_both_languages_with_the_real_facts() -> None:
    az = notifications.render_document_expiring(
        vendor_name="VVESA MMC",
        document_code="A-05",
        document_name_az="Vergi borcu olmaması haqqında arayış",
        document_name_en="Tax clearance certificate",
        expiry_date=date(2026, 9, 25),
        days_left=30,
        locale="az",
    )
    en = notifications.render_document_expiring(
        vendor_name="VVESA MMC",
        document_code="A-05",
        document_name_az="Vergi borcu olmaması haqqında arayış",
        document_name_en="Tax clearance certificate",
        expiry_date=date(2026, 9, 25),
        days_left=30,
        locale="en",
    )
    for rendered, code in ((az, "az"), (en, "en")):
        assert rendered.locale == code
        assert "A-05" in rendered.subject
        assert "VVESA MMC" in rendered.body
        assert "A-05" in rendered.body
        assert "30" in rendered.body
        # Nothing invented: the real date is in the body, in some form, and no template
        # placeholder ("{...}") survived an unfilled f-string.
        assert "{" not in rendered.body and "}" not in rendered.body
    assert "Vergi borcu" in az.body
    assert "Tax clearance" in en.body
    assert az.body != en.body
    assert az.subject != en.subject


@pytest.mark.parametrize(
    "renderer",
    [
        lambda locale: notifications.render_prequalification_lapsing(
            vendor_name="Shield MMC", lapse_date=date(2026, 12, 1), days_left=7, locale=locale
        ),
        lambda locale: notifications.render_invitation(
            vendor_name="Shield MMC",
            cycle_name="TQS-2026-006",
            opens_at=None,
            closes_at=None,
            locale=locale,
        ),
        lambda locale: notifications.render_information_requested(
            vendor_name="Shield MMC", cycle_name="TQS-2026-006", note=None, locale=locale
        ),
        lambda locale: notifications.render_decision_recorded(
            vendor_name="Shield MMC",
            cycle_name="TQS-2026-006",
            decision=DecisionKind.APPROVE,
            cls="B",
            justification=None,
            locale=locale,
        ),
    ],
    ids=["prequalification_lapsing", "invitation", "information_requested", "decision_recorded"],
)
def test_every_template_carries_both_languages(renderer: Any) -> None:
    """Spec §13: "every template carries both, like everything else user-facing"."""
    az = renderer("az")
    en = renderer("en")
    assert az.locale == "az" and en.locale == "en"
    assert az.subject and en.subject
    assert az.body and en.body
    assert az.body != en.body
    assert "{" not in az.body and "}" not in az.body
    assert "{" not in en.body and "}" not in en.body
    assert "Shield MMC" in az.body
    assert "Shield MMC" in en.body


def test_information_requested_includes_the_real_note_when_there_is_one() -> None:
    """Nothing invented: a note that exists is shown; one that does not is not fabricated."""
    with_note = notifications.render_information_requested(
        vendor_name="Shield MMC",
        cycle_name="TQS-2026-006",
        note="Zəhmət olmasa A-05 sənədini yeniləyin.",
        locale="az",
    )
    assert "A-05" in with_note.body

    without_note = notifications.render_information_requested(
        vendor_name="Shield MMC", cycle_name="TQS-2026-006", note=None, locale="az"
    )
    assert "Qeyd:" not in without_note.body


# ── recipient resolution ────────────────────────────────────────────────────
def test_resolve_recipient_prefers_the_primary_contacts_email(
    session: Session, make_vendor: Any
) -> None:
    vendor = make_vendor()
    session.add(Contact(vendor_id=vendor.id, name="Other", email="other@x.test", is_primary=False))
    session.add(
        Contact(vendor_id=vendor.id, name="Primary", email="primary@x.test", is_primary=True)
    )
    session.commit()
    recipient = notifications.resolve_recipient(session, vendor)
    assert recipient is not None
    assert recipient[0] == "primary@x.test"


def test_resolve_recipient_uses_the_portal_accounts_locale(
    session: Session, make_vendor: Any
) -> None:
    vendor = make_vendor()
    _contact(session, vendor, email="buyer@vendor.test")
    user = User(
        email="buyer@vendor.test",
        role=UserRole.VENDOR,
        vendor_id=vendor.id,
        locale="en",
    )
    session.add(user)
    session.commit()
    recipient = notifications.resolve_recipient(session, vendor)
    assert recipient == ("buyer@vendor.test", "en")


def test_resolve_recipient_falls_back_to_the_organisation_default_locale(
    session: Session, make_vendor: Any
) -> None:
    vendor = make_vendor()
    _contact(session, vendor, email="buyer@vendor.test")
    recipient = notifications.resolve_recipient(session, vendor)
    assert recipient == ("buyer@vendor.test", "az")


def test_resolve_recipient_is_none_with_no_contact_and_no_account(
    session: Session, make_vendor: Any
) -> None:
    vendor = make_vendor()
    assert notifications.resolve_recipient(session, vendor) is None


# ── notify_document_expiring: once-only, log fallback, unreachable SMTP ────
def test_notify_document_expiring_reports_no_expiry_without_inventing_one(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    vendor = make_vendor()
    _contact(session, vendor)
    document = _document(session, vendor, expiry_date=None)  # "Müddətsiz"
    outcome = notifications.notify_document_expiring(
        uow, _settings(smtp_host=None), vendor, document, window_days=30, today=TODAY
    )
    assert outcome == "no_expiry"


def test_notify_document_expiring_reports_no_recipient(uow: UnitOfWork, make_vendor: Any) -> None:
    vendor = make_vendor()
    document = _document(uow.session, vendor, expiry_date=date(2026, 9, 25))
    outcome = notifications.notify_document_expiring(
        uow, _settings(smtp_host=None), vendor, document, window_days=30, today=TODAY
    )
    assert outcome == "no_recipient"


def test_notify_document_expiring_logs_when_smtp_is_unset_and_records_it_as_sent(
    uow: UnitOfWork, make_vendor: Any, session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """Brief §2: the log fallback is documented behaviour, not a failure — it counts."""
    vendor = make_vendor()
    _contact(session, vendor)
    document = _document(session, vendor, code="A-05", expiry_date=date(2026, 9, 25))
    with caplog.at_level("INFO", logger="vendoriq.mail"):
        outcome = notifications.notify_document_expiring(
            uow, _settings(smtp_host=None), vendor, document, window_days=30, today=TODAY
        )
    assert outcome == "logged"
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "buyer@vendor.test" in logged

    event = session.scalars(
        select(Event).where(Event.type == EventType.DOCUMENT_EXPIRING.value)
    ).one()
    assert event.entity_id == document.id
    assert event.payload["window_days"] == 30
    assert event.payload["expiry_date"] == "2026-09-25"


def test_a_second_run_in_the_same_window_sends_nothing_new(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    vendor = make_vendor()
    _contact(session, vendor)
    document = _document(session, vendor, expiry_date=date(2026, 9, 25))
    settings = _settings(smtp_host=None)

    first = notifications.notify_document_expiring(
        uow, settings, vendor, document, window_days=30, today=TODAY
    )
    second = notifications.notify_document_expiring(
        uow, settings, vendor, document, window_days=30, today=TODAY
    )
    assert first == "logged"
    assert second == "duplicate"
    # Exactly one event, not one per run.
    events = list(
        session.scalars(select(Event).where(Event.type == EventType.DOCUMENT_EXPIRING.value))
    )
    assert len(events) == 1


def test_a_different_window_for_the_same_document_still_sends(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    """The 7-day reminder is a distinct fact from the 30-day one for the same document."""
    vendor = make_vendor()
    _contact(session, vendor)
    document = _document(session, vendor, expiry_date=date(2026, 9, 25))
    settings = _settings(smtp_host=None)

    at_30 = notifications.notify_document_expiring(
        uow, settings, vendor, document, window_days=30, today=TODAY
    )
    at_7 = notifications.notify_document_expiring(
        uow, settings, vendor, document, window_days=7, today=TODAY
    )
    assert at_30 == "logged"
    assert at_7 == "logged"


def test_a_changed_expiry_date_is_a_new_fact_worth_a_new_reminder(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    vendor = make_vendor()
    _contact(session, vendor)
    document = _document(session, vendor, expiry_date=date(2026, 9, 25))
    settings = _settings(smtp_host=None)
    notifications.notify_document_expiring(
        uow, settings, vendor, document, window_days=30, today=TODAY
    )
    # The vendor re-uploaded the certificate with a later expiry.
    document.expiry_date = date(2026, 10, 25)
    session.commit()
    outcome = notifications.notify_document_expiring(
        uow, settings, vendor, document, window_days=30, today=TODAY
    )
    assert outcome == "logged"


class _RefusingSMTP:
    """Stands in for an SMTP host that is configured but cannot be reached."""

    instances: ClassVar[list[_RefusingSMTP]] = []

    def __init__(self, host: str, port: int) -> None:
        _RefusingSMTP.instances.append(self)
        raise ConnectionRefusedError("connection refused")

    def __enter__(self) -> _RefusingSMTP:  # pragma: no cover - never reached
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:  # pragma: no cover - never reached
        return None


def test_an_unreachable_smtp_host_does_not_lose_the_message(
    uow: UnitOfWork,
    make_vendor: Any,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The brief, verbatim: "an unreachable SMTP host does not lose the message"."""
    monkeypatch.setattr(smtplib, "SMTP", _RefusingSMTP)
    vendor = make_vendor()
    _contact(session, vendor)
    document = _document(session, vendor, expiry_date=date(2026, 9, 25))
    configured = _settings(smtp_host="mail.example.invalid")

    outcome = notifications.notify_document_expiring(
        uow, configured, vendor, document, window_days=30, today=TODAY
    )
    assert outcome == "failed"
    # Not marked as sent: no event, so the reminder is still due.
    pending = session.scalars(
        select(Event).where(Event.type == EventType.DOCUMENT_EXPIRING.value)
    ).first()
    assert pending is None

    # The host comes back; the retry on the next run delivers and only then is it recorded.
    monkeypatch.undo()
    outcome_retry = notifications.notify_document_expiring(
        uow, _settings(smtp_host=None), vendor, document, window_days=30, today=TODAY
    )
    assert outcome_retry == "logged"


# ── notify_prequalification_lapsing: once-only via the audit log ───────────
def test_notify_prequalification_lapsing_records_a_dedup_marker_in_the_audit_log(
    uow: UnitOfWork, make_vendor: Any, session: Session
) -> None:
    vendor = make_vendor()
    _contact(session, vendor)
    settings = _settings(smtp_host=None)
    lapse_date = date(2026, 12, 1)

    first = notifications.notify_prequalification_lapsing(
        uow, settings, vendor, lapse_date=lapse_date, window_days=30, today=TODAY
    )
    second = notifications.notify_prequalification_lapsing(
        uow, settings, vendor, lapse_date=lapse_date, window_days=30, today=TODAY
    )
    assert first == "logged"
    assert second == "duplicate"

    rows = list(
        session.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_type == "vendor",
                AuditEvent.entity_id == vendor.id,
                AuditEvent.action == "notification.prequalification_lapsing",
            )
        )
    )
    assert len(rows) == 1
    assert rows[0].after == {"window_days": 30, "lapse_date": "2026-12-01"}


def test_notify_prequalification_lapsing_no_recipient_is_reported_not_swallowed(
    uow: UnitOfWork, make_vendor: Any
) -> None:
    vendor = make_vendor()
    outcome = notifications.notify_prequalification_lapsing(
        uow,
        _settings(smtp_host=None),
        vendor,
        lapse_date=date(2026, 12, 1),
        window_days=30,
        today=TODAY,
    )
    assert outcome == "no_recipient"
