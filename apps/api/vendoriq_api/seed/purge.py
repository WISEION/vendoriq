"""``purge-demo`` — deletes every ``is_demo=True`` row the demo layer added.

**Scope.** Every table the real/demo classification (brief §1.10, seed/README.md) actually
marks: ``Vendor`` (the 4 demo suppliers), ``Contact``, ``Category``, ``VendorCategory``
(the 13 real vendors' demo category assignments), ``Document`` (demo expiry rows),
``Project``/``WorkPackage`` (the demo project and both projects' package breakdown),
``QualificationCycle``, ``Application`` and ``PerformanceRecord``.

``User`` also carries an ``is_demo`` column, and is deliberately **not** in this list.
That flag marks a *test account* — gated by ``AUTH_MODE`` and owned by
``services.accounts.purge_test_accounts`` (the function switching to ``AUTH_MODE=live``
calls) — a different axis from the seed's real/demo data, with its own lifecycle. Folding
it in here would make ``make seed`` → ``make seed-demo`` → ``make purge-demo`` delete the
very staff logins ``make seed`` just created in the same run.

**The one exception, and why it needs one.** ``services/accounts.py`` gives
``vendor.new@vendoriq.test`` — the one seeded account with no real vendor behind it — a
placeholder ``Vendor`` of its own, flagged ``is_demo=True`` because it genuinely has no
real counterpart. Deleting that row is correct by the letter of "every ``is_demo`` row",
but ``User.vendor_id`` is ``ON DELETE CASCADE`` (``models/auth.py``), so it would silently
take the login with it — the seven accounts ``docs/TEST_ACCOUNTS.md`` promises would become
six, with no error and no message, until someone tried to sign in as ``vendor.new`` and
found a 401. A demo-data command is not where an account's lifecycle should be decided, so
the ``Vendor`` delete alone excludes whatever vendor an ``app_user`` still points at
(``_LOGGED_IN_VENDOR_IDS``) — in practice, today, exactly this one placeholder; the two
real vendor accounts were already safe, being ``is_demo=False``. Removing ``vendor.new``
for good means ``AUTH_MODE=live`` and ``services.accounts.purge_test_accounts``, which is
what that switch already implies.

The guard sits on ``Vendor`` and ``Contact`` only, not on the rest of the demo children.
`ON DELETE CASCADE` from `vendor` reaches `app_user` (through `User.vendor_id`); nothing
else does, so a demo `Document` or `VendorCategory` row cannot take a login down no matter
whose vendor it belongs to — including Wesa's and Shield's, the two vendors the real
accounts `habib.atakisiyev@wesa.az` and `a.tabit@shield.az` link to. Their demo
document-expiry and category-assignment rows are still exactly what `seed/README.md` calls
them (demo), and guarding *those* tables by vendor too was tried and was a bug: it silently
kept Wesa's and Shield's demo rows alongside `vendor.new`'s, because all three are "a
vendor an `app_user` points at". `Contact` is the one child worth guarding anyway — a real
vendor's own contact is never seeded `is_demo=True` (`real.py`), so the guard there can
never repeat that bug, and without it `vendor.new` would keep its login but lose its one
contact, a placeholder with nobody's name on it.

Deletion is a bulk ``DELETE ... WHERE is_demo`` per table — not ``session.delete`` per row
— so it does not depend on the ORM's cascade being loaded; the database's own
``ON DELETE CASCADE`` on every child foreign key still fires underneath it. Children are
still listed before their usual parents so a demo row hanging off a *real* parent (a demo
``Document`` on a real vendor, a demo ``WorkPackage`` on the real project) is removed even
though that parent is not going anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

from sqlalchemy import Delete, delete, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from ..db import UnitOfWork
from ..models import (
    Application,
    Category,
    Contact,
    Document,
    PerformanceRecord,
    Project,
    QualificationCycle,
    User,
    Vendor,
    VendorCategory,
    WorkPackage,
)
from ..services import audit


@dataclass(slots=True)
class PurgeSummary:
    removed: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.removed.values())


def _delete_demo(session: Session, statement: Delete) -> int:
    """``rowcount`` typed properly. A Core ``DELETE`` with no ``RETURNING`` clause always
    comes back as a ``CursorResult`` at runtime; it just does not match
    ``Session.execute``'s ``TypedReturnsRows`` overload, so the general ``Result[Any]`` the
    stubs infer is cast rather than waved off with an ignore comment."""
    result = cast(CursorResult[Any], session.execute(statement))
    return result.rowcount or 0


#: Vendors a live account still logs in through. Purging the demo layer must never take a
#: login with it (Gate 1) — see the module docstring's "the one exception" paragraph.
_LOGGED_IN_VENDOR_IDS = select(User.vendor_id).where(User.vendor_id.is_not(None))


def purge_demo(uow: UnitOfWork) -> PurgeSummary:
    session = uow.session
    removed = {
        "work_package": _delete_demo(
            session, delete(WorkPackage).where(WorkPackage.is_demo.is_(True))
        ),
        "document": _delete_demo(session, delete(Document).where(Document.is_demo.is_(True))),
        "vendor_category": _delete_demo(
            session, delete(VendorCategory).where(VendorCategory.is_demo.is_(True))
        ),
        "application": _delete_demo(
            session, delete(Application).where(Application.is_demo.is_(True))
        ),
        "contact": _delete_demo(
            session,
            delete(Contact).where(
                Contact.is_demo.is_(True), Contact.vendor_id.not_in(_LOGGED_IN_VENDOR_IDS)
            ),
        ),
        "performance_record": _delete_demo(
            session, delete(PerformanceRecord).where(PerformanceRecord.is_demo.is_(True))
        ),
        "qualification_cycle": _delete_demo(
            session, delete(QualificationCycle).where(QualificationCycle.is_demo.is_(True))
        ),
        "project": _delete_demo(session, delete(Project).where(Project.is_demo.is_(True))),
        "vendor": _delete_demo(
            session,
            delete(Vendor).where(Vendor.is_demo.is_(True), Vendor.id.not_in(_LOGGED_IN_VENDOR_IDS)),
        ),
        "category": _delete_demo(session, delete(Category).where(Category.is_demo.is_(True))),
    }
    uow.flush()
    audit.record(
        uow,
        entity_type="seed",
        entity_id=None,
        action="purge_demo",
        after={"removed": removed},
    )
    return PurgeSummary(removed=removed)
