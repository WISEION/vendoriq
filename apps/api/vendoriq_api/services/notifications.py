"""Bilingual e-mail notifications (brief §2G, spec §13).

Every user-facing string in this system exists in Azerbaijani and English (spec §13), and
that includes the mail the worker sends nobody watches. Each ``render_*`` function below
builds **both** bodies from the same call — the caller picks a language, the other branch of
the ``if`` is always there in the source — so a template can never ship AZ-only or EN-only.

Two rules the brief calls out are enforced here, not left to the caller's discipline:

**Nothing invented.** A reminder names a real document code, a real expiry date, a real
lapse date. Every ``render_*`` and ``notify_*`` function takes that data as a required
argument; there is no fallback string like "soon" for a date nobody supplied. A document with
no expiry (``Müddətsiz`` — brief §1.11) or an application never decided is not renderable —
:func:`notify_document_expiring` and :func:`notify_prequalification_lapsing` report that
outcome rather than guessing.

**The log fallback is not a failure.** ``services.mail.send`` returns ``False`` (and only
logs) when ``SMTP_HOST`` is empty — that is documented behaviour (brief §2), and the
``notify_*`` functions below treat it exactly like a real delivery: the reminder is recorded
as sent either way, so a job run under ``SMTP_HOST=""`` does not repeat the same log line
every day. What must never be swallowed is an actual failure to reach a *configured* host —
``mail.send`` raising is the one case that must **not** be recorded as sent, so the next run
retries instead of losing the message.

**Once-only, without a new column.** Nothing here needed a migration:

* Document reminders are recorded as ``EventType.DOCUMENT_EXPIRING`` domain events (the
  member already existed in the contract, unused, seemingly reserved for exactly this). The
  event's payload carries ``window_days`` and the ``expiry_date`` it was sent for, so a
  second run in the same window finds the matching event and sends nothing new, while a
  document whose expiry date genuinely changes (re-uploaded certificate) is treated as a new
  fact worth a new reminder. Reusing an existing, contract-visible event type also means a
  webhook subscriber can see these reminders fire, which a private bookkeeping table would
  not have given them for free.
* Prequalification-lapsing reminders have no equivalent contract event to reuse — adding one
  is an ``enums.py`` change, which is a contract change this task cannot make on its own
  (CONTRIBUTING.md). Recording it as an audit row instead
  (``AuditEvent.action == "notification.prequalification_lapsing"``) needs no schema change:
  ``AuditEvent.action`` is documented as free-form ("create | update | delete | decide |
  login | adapter action"), unlike ``EventType`` which the contract fixes. See the final
  report for the change request this leaves open.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..catalog import DOCUMENT_CATALOG
from ..config import Settings
from ..db import UnitOfWork
from ..models import AuditEvent, Contact, Document, Event, User, Vendor
from ..models.enums import DecisionKind, EventType, UserRole
from . import audit, events, mail, settings_store

logger = logging.getLogger("vendoriq.notifications")

Locale = Literal["az", "en"]

#: What a ``notify_*`` call reports, always — the brief: "a job that cannot do its work
#: reports it; it never silently does nothing".
#:
#: ``sent`` — delivered over SMTP. ``logged`` — SMTP_HOST is empty; the log fallback, not a
#: failure (brief §2). ``duplicate`` — this exact reminder was already recorded; nothing new
#: was due. ``no_recipient`` — the vendor has no e-mail on file; a fact worth counting, not a
#: silent skip. ``no_expiry`` — the document has no expiry date ("Müddətsiz") and cannot be
#: reminded about. ``failed`` — SMTP was configured and reachable-in-principle but the send
#: raised; the message is not lost because nothing was marked sent, so the next run retries.
NotifyOutcome = Literal["sent", "logged", "duplicate", "no_recipient", "no_expiry", "failed"]

_PREQUALIFICATION_LAPSING_ACTION = "notification.prequalification_lapsing"

_DECISION_LABEL: dict[DecisionKind, tuple[str, str]] = {
    DecisionKind.APPROVE: ("Təsdiqləndi", "Approved"),
    DecisionKind.REJECT: ("Rədd edildi", "Rejected"),
    DecisionKind.REQUEST_INFO: ("Əlavə məlumat tələb olunur", "Additional information requested"),
}


@dataclass(frozen=True, slots=True)
class RenderedEmail:
    """One rendered message in one language — what :func:`mail.send` is given."""

    subject: str
    body: str
    locale: Locale


# ── recipient resolution ─────────────────────────────────────────────────────
def resolve_recipient(session: Session, vendor: Vendor) -> tuple[str, Locale] | None:
    """The vendor's notification e-mail and language, or ``None`` when neither is on file.

    E-mail: the primary contact's address, falling back to any contact with one, falling
    back to the vendor's portal account. Language: the portal account's own preference
    (``User.locale``, spec §13) when one exists, otherwise the organisation default — never
    guessed per-vendor from nothing.
    """
    primary = session.scalars(
        select(Contact)
        .where(Contact.vendor_id == vendor.id, Contact.is_primary.is_(True))
        .order_by(Contact.created_at.asc())
    ).first()
    portal_user = session.scalars(
        select(User)
        .where(
            User.role == UserRole.VENDOR,
            User.vendor_id == vendor.id,
            User.is_active.is_(True),
        )
        .order_by(User.created_at.asc())
    ).first()

    email = primary.email if primary and primary.email else None
    if email is None and portal_user is not None:
        email = portal_user.email
    if email is None:
        any_contact = session.scalars(
            select(Contact)
            .where(Contact.vendor_id == vendor.id, Contact.email.is_not(None))
            .order_by(Contact.is_primary.desc(), Contact.created_at.asc())
        ).first()
        email = any_contact.email if any_contact else None
    if email is None:
        return None

    locale: Locale = "az"
    if portal_user is not None and portal_user.locale in ("az", "en"):
        locale = "en" if portal_user.locale == "en" else "az"
    else:
        org_locale = settings_store.group(session, "organisation").get("default_locale", "az")
        locale = "en" if org_locale == "en" else "az"
    return email, locale


# ── templates ─────────────────────────────────────────────────────────────────
def render_document_expiring(
    *,
    vendor_name: str,
    document_code: str,
    document_name_az: str,
    document_name_en: str,
    expiry_date: date,
    days_left: int,
    locale: Locale,
) -> RenderedEmail:
    """Spec §7: "expiring documents trigger reminders at 30 and 7 days"."""
    if locale == "az":
        subject = f"Sənədin etibarlılıq müddəti bitir: {document_code} — {vendor_name}"
        body = (
            f"Hörmətli {vendor_name},\n\n"
            f"{document_code} — {document_name_az} sənədinizin etibarlılıq müddəti "
            f"{expiry_date.strftime('%d.%m.%Y')} tarixində başa çatır "
            f"({days_left} gün qalıb).\n\n"
            "Zəhmət olmasa yenilənmiş sənədi VendorIQ portalında yükləyin — əks halda "
            "profiliniz köhnəlmiş sənəd sayıla bilər.\n\n"
            "Hörmətlə,\nVendorIQ"
        )
    else:
        subject = f"Document expiring soon: {document_code} — {vendor_name}"
        body = (
            f"Dear {vendor_name},\n\n"
            f"Your document {document_code} — {document_name_en} expires on "
            f"{expiry_date.strftime('%d %b %Y')} ({days_left} days remaining).\n\n"
            "Please upload a renewed document through the VendorIQ portal before it lapses, "
            "or your profile may be treated as out of date.\n\n"
            "Regards,\nVendorIQ"
        )
    return RenderedEmail(subject=subject, body=body, locale=locale)


def render_prequalification_lapsing(
    *, vendor_name: str, lapse_date: date, days_left: int, locale: Locale
) -> RenderedEmail:
    """Spec §9: prequalification is valid twelve months."""
    if locale == "az":
        subject = f"Prekvalifikasiya müddəti yaxınlaşır — {vendor_name}"
        body = (
            f"Hörmətli {vendor_name},\n\n"
            "VendorIQ reyestrindəki prekvalifikasiya statusunuzun 12 aylıq etibarlılıq "
            f"müddəti {lapse_date.strftime('%d.%m.%Y')} tarixində başa çatır "
            f"({days_left} gün qalıb).\n\n"
            "Statusunuzu qorumaq üçün profilinizi cari saxlayın və növbəti "
            "prekvalifikasiya dövrünə dəvəti gözləyin.\n\n"
            "Hörmətlə,\nVendorIQ"
        )
    else:
        subject = f"Prequalification expiring soon — {vendor_name}"
        body = (
            f"Dear {vendor_name},\n\n"
            "Your twelve-month prequalification status in the VendorIQ register expires on "
            f"{lapse_date.strftime('%d %b %Y')} ({days_left} days remaining).\n\n"
            "Please keep your profile current and watch for the next qualification cycle "
            "invitation to retain your status.\n\n"
            "Regards,\nVendorIQ"
        )
    return RenderedEmail(subject=subject, body=body, locale=locale)


def render_invitation(
    *,
    vendor_name: str,
    cycle_name: str,
    opens_at: datetime | None,
    closes_at: datetime | None,
    locale: Locale,
) -> RenderedEmail:
    """A vendor invited into a qualification cycle (spec §9, "Registered → Invited")."""
    if locale == "az":
        subject = f"Prekvalifikasiya dövrünə dəvət: {cycle_name}"
        lines = [
            f"Hörmətli {vendor_name},",
            "",
            f'"{cycle_name}" prekvalifikasiya dövrünə dəvət olunmusunuz.',
        ]
        if opens_at is not None:
            lines.append(f"Ərizə forması {opens_at.strftime('%d.%m.%Y')} tarixindən açıqdır.")
        if closes_at is not None:
            lines.append(f"Son müraciət tarixi: {closes_at.strftime('%d.%m.%Y')}.")
        lines += [
            "",
            "Zəhmət olmasa VendorIQ portalına daxil olub formanı doldurun və tələb olunan "
            "sənədləri yükləyin.",
            "",
            "Hörmətlə,\nVendorIQ",
        ]
        body = "\n".join(lines)
    else:
        subject = f"Invitation to a qualification cycle: {cycle_name}"
        lines = [
            f"Dear {vendor_name},",
            "",
            f'You are invited to participate in the "{cycle_name}" qualification cycle.',
        ]
        if opens_at is not None:
            lines.append(f"The application form opens on {opens_at.strftime('%d %b %Y')}.")
        if closes_at is not None:
            lines.append(f"Please submit by {closes_at.strftime('%d %b %Y')}.")
        lines += [
            "",
            "Please sign in to the VendorIQ portal to complete the form and upload the "
            "required documents.",
            "",
            "Regards,\nVendorIQ",
        ]
        body = "\n".join(lines)
    return RenderedEmail(subject=subject, body=body, locale=locale)


def render_information_requested(
    *, vendor_name: str, cycle_name: str, note: str | None, locale: Locale
) -> RenderedEmail:
    """Spec §9: "Information requested" — officer sends the application back to the vendor."""
    if locale == "az":
        subject = f"Əlavə məlumat tələb olunur — {cycle_name}"
        body = (
            f"Hörmətli {vendor_name},\n\n"
            f'"{cycle_name}" üzrə müraciətinizə dair əlavə məlumat və ya sənəd tələb olunur.'
            + (f"\n\nQeyd: {note.strip()}" if note and note.strip() else "")
            + "\n\nZəhmət olmasa VendorIQ portalında lazımi düzəlişləri edin ki, "
            "müraciətinizin baxılması davam etsin.\n\n"
            "Hörmətlə,\nVendorIQ"
        )
    else:
        subject = f"Additional information requested — {cycle_name}"
        body = (
            f"Dear {vendor_name},\n\n"
            f'Additional information or documents are needed on your "{cycle_name}" '
            "application."
            + (f"\n\nNote: {note.strip()}" if note and note.strip() else "")
            + "\n\nPlease make the requested changes in the VendorIQ portal so review can "
            "continue.\n\n"
            "Regards,\nVendorIQ"
        )
    return RenderedEmail(subject=subject, body=body, locale=locale)


def render_decision_recorded(
    *,
    vendor_name: str,
    cycle_name: str,
    decision: DecisionKind,
    cls: str | None,
    justification: str | None,
    locale: Locale,
) -> RenderedEmail:
    """A commission / manager decision on an application (spec §9, §10)."""
    label_az, label_en = _DECISION_LABEL[decision]
    if locale == "az":
        subject = f"Qərar qeydə alındı — {cycle_name}: {label_az}"
        lines = [f"Hörmətli {vendor_name},", "", f'"{cycle_name}" üzrə qərar: {label_az}.']
        if cls:
            lines.append(f"Nəticə sinfi: {cls}.")
        if justification and justification.strip():
            lines.append(f"Əsaslandırma: {justification.strip()}")
        lines += [
            "",
            "Ətraflı məlumat üçün VendorIQ portalına daxil olun.",
            "",
            "Hörmətlə,\nVendorIQ",
        ]
        body = "\n".join(lines)
    else:
        subject = f"Decision recorded — {cycle_name}: {label_en}"
        lines = [f"Dear {vendor_name},", "", f'Decision on "{cycle_name}": {label_en}.']
        if cls:
            lines.append(f"Result class: {cls}.")
        if justification and justification.strip():
            lines.append(f"Justification: {justification.strip()}")
        lines += ["", "Sign in to the VendorIQ portal for details.", "", "Regards,\nVendorIQ"]
        body = "\n".join(lines)
    return RenderedEmail(subject=subject, body=body, locale=locale)


# ── delivery ─────────────────────────────────────────────────────────────────
def _deliver(
    settings: Settings, to: str, rendered: RenderedEmail
) -> Literal["sent", "logged", "failed"]:
    """Send through the one seam (``services.mail``), never letting a transport error escape.

    The brief: "an unreachable SMTP host does not lose the message" — the caller must not
    record this reminder as sent when this returns ``failed``, so the next run retries it.
    A blind ``except Exception`` is deliberate here: ``smtplib`` raises from a wide and
    version-dependent family (``OSError`` subclasses, ``smtplib.SMTPException`` subclasses),
    and the one contract that matters is "a job must not crash" — not which exception it was.
    """
    try:
        delivered = mail.send(settings, to=to, subject=rendered.subject, body=rendered.body)
    except Exception as exc:
        logger.error("notification delivery to=%s subject=%r failed: %s", to, rendered.subject, exc)
        return "failed"
    return "sent" if delivered else "logged"


# ── once-only bookkeeping ────────────────────────────────────────────────────
def _document_reminder_already_sent(
    session: Session, document_id: uuid.UUID, window_days: int, expiry_date: date
) -> bool:
    expiry_iso = expiry_date.isoformat()
    rows = session.scalars(
        select(Event).where(
            Event.type == EventType.DOCUMENT_EXPIRING.value,
            Event.entity_type == "document",
            Event.entity_id == document_id,
        )
    )
    return any(
        row.payload.get("window_days") == window_days
        and row.payload.get("expiry_date") == expiry_iso
        for row in rows
    )


def _mark_document_reminder_sent(
    uow: UnitOfWork, vendor: Vendor, document: Document, window_days: int
) -> None:
    assert document.expiry_date is not None  # guarded by the caller
    events.emit(
        uow,
        EventType.DOCUMENT_EXPIRING,
        entity_type="document",
        entity_id=document.id,
        payload={
            "vendor_id": str(vendor.id),
            "code": document.code,
            "expiry_date": document.expiry_date.isoformat(),
            "window_days": window_days,
        },
    )


def _prequalification_reminder_already_sent(
    session: Session, vendor_id: uuid.UUID, window_days: int, lapse_date: date
) -> bool:
    lapse_iso = lapse_date.isoformat()
    rows = session.scalars(
        select(AuditEvent).where(
            AuditEvent.entity_type == "vendor",
            AuditEvent.entity_id == vendor_id,
            AuditEvent.action == _PREQUALIFICATION_LAPSING_ACTION,
        )
    )
    return any(
        (row.after or {}).get("window_days") == window_days
        and (row.after or {}).get("lapse_date") == lapse_iso
        for row in rows
    )


def _mark_prequalification_reminder_sent(
    uow: UnitOfWork, vendor: Vendor, window_days: int, lapse_date: date
) -> None:
    audit.record(
        uow,
        entity_type="vendor",
        entity_id=vendor.id,
        action=_PREQUALIFICATION_LAPSING_ACTION,
        after={"window_days": window_days, "lapse_date": lapse_date.isoformat()},
    )
    uow.flush()


# ── job-facing entry points ─────────────────────────────────────────────────
def notify_document_expiring(
    uow: UnitOfWork,
    settings: Settings,
    vendor: Vendor,
    document: Document,
    *,
    window_days: int,
    today: date | None = None,
) -> NotifyOutcome:
    """Send (or log) one document-expiry reminder, at most once per document per window.

    Called by the worker's ``expiry_reminders`` job once per document per matching window
    (spec §7: reminders at 30 and 7 days).
    """
    if document.expiry_date is None:
        return "no_expiry"
    reference = today or datetime.now(UTC).date()
    if _document_reminder_already_sent(uow.session, document.id, window_days, document.expiry_date):
        return "duplicate"
    recipient = resolve_recipient(uow.session, vendor)
    if recipient is None:
        return "no_recipient"
    to_email, locale = recipient
    definition = DOCUMENT_CATALOG.get(document.code)
    days_left = (document.expiry_date - reference).days
    rendered = render_document_expiring(
        vendor_name=vendor.legal_name,
        document_code=document.code,
        document_name_az=definition.name_az if definition else document.code,
        document_name_en=definition.name_en if definition else document.code,
        expiry_date=document.expiry_date,
        days_left=days_left,
        locale=locale,
    )
    outcome = _deliver(settings, to_email, rendered)
    if outcome == "failed":
        return "failed"
    _mark_document_reminder_sent(uow, vendor, document, window_days)
    return outcome


def notify_prequalification_lapsing(
    uow: UnitOfWork,
    settings: Settings,
    vendor: Vendor,
    *,
    lapse_date: date,
    window_days: int,
    today: date | None = None,
) -> NotifyOutcome:
    """Warn a vendor before its 12-month prequalification validity lapses (spec §9).

    Called by the worker's ``prequalification_expiry`` job. ``lapse_date`` is computed by
    the caller from the real approval decision (``Application.decided_at``) plus the
    validity in force for that application — never guessed here.
    """
    reference = today or datetime.now(UTC).date()
    if _prequalification_reminder_already_sent(uow.session, vendor.id, window_days, lapse_date):
        return "duplicate"
    recipient = resolve_recipient(uow.session, vendor)
    if recipient is None:
        return "no_recipient"
    to_email, locale = recipient
    days_left = (lapse_date - reference).days
    rendered = render_prequalification_lapsing(
        vendor_name=vendor.legal_name, lapse_date=lapse_date, days_left=days_left, locale=locale
    )
    outcome = _deliver(settings, to_email, rendered)
    if outcome == "failed":
        return "failed"
    _mark_prequalification_reminder_sent(uow, vendor, window_days, lapse_date)
    return outcome


# ── not yet wired to a trigger (see the phase 2G report) ────────────────────
# The three functions below render and send correctly (tested with fixture data) but
# nothing calls them yet: the moments they fire at — a vendor invited into a cycle, an
# officer requesting information, a commission decision recorded — happen inside
# services/cycles.py and services/applications.py, which belong to other phase 2 tasks
# (2B/2C) and are outside this task's write scope. Wiring them in is a one-line call to
# ``send_invitation`` / ``send_information_requested`` / ``send_decision_recorded`` at the
# point each state change already commits.
def send_invitation(
    settings: Settings,
    *,
    to: str,
    locale: Locale,
    vendor_name: str,
    cycle_name: str,
    opens_at: datetime | None,
    closes_at: datetime | None,
) -> Literal["sent", "logged", "failed"]:
    rendered = render_invitation(
        vendor_name=vendor_name,
        cycle_name=cycle_name,
        opens_at=opens_at,
        closes_at=closes_at,
        locale=locale,
    )
    return _deliver(settings, to, rendered)


def send_information_requested(
    settings: Settings,
    *,
    to: str,
    locale: Locale,
    vendor_name: str,
    cycle_name: str,
    note: str | None,
) -> Literal["sent", "logged", "failed"]:
    rendered = render_information_requested(
        vendor_name=vendor_name, cycle_name=cycle_name, note=note, locale=locale
    )
    return _deliver(settings, to, rendered)


def send_decision_recorded(
    settings: Settings,
    *,
    to: str,
    locale: Locale,
    vendor_name: str,
    cycle_name: str,
    decision: DecisionKind,
    cls: str | None,
    justification: str | None,
) -> Literal["sent", "logged", "failed"]:
    rendered = render_decision_recorded(
        vendor_name=vendor_name,
        cycle_name=cycle_name,
        decision=decision,
        cls=cls,
        justification=justification,
        locale=locale,
    )
    return _deliver(settings, to, rendered)
