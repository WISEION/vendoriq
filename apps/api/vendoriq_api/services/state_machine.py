"""The qualification workflow as an explicit state machine (spec §9, brief §1.6).

Two things are enforced here and nowhere else:

* **which transitions exist** — `submitted` never goes straight to `prequalified`, an
  officer never approves, a vendor never rejects itself;
* **who may make them** — the "Entered by" column of spec §9 is data, not prose.

Vendor status is *derived* from the application, not maintained in parallel. The one
exception is ``suspended``, which a manager sets on the vendor directly and which outranks
whatever the application says: a suspended vendor whose old application still reads
``prequalified`` must stay suspended until the manager lifts it (spec §9).
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ApiError
from ..models.enums import ApplicationStatus, UserRole, VendorStatus

S = ApplicationStatus
R = UserRole

#: Every role that can act on someone else's application.
_STAFF = frozenset({R.OFFICER, R.COMMISSION, R.MANAGER, R.ADMIN})


@dataclass(frozen=True, slots=True)
class Transition:
    """One edge of the machine: who may take it and why it exists."""

    source: ApplicationStatus
    target: ApplicationStatus
    roles: frozenset[UserRole]
    #: Short reason, quoted back in the 409 body so the UI can explain the refusal.
    note: str


def _t(
    source: ApplicationStatus,
    target: ApplicationStatus,
    roles: frozenset[UserRole] | set[UserRole],
    note: str,
) -> Transition:
    return Transition(source, target, frozenset(roles), note)


TRANSITIONS: tuple[Transition, ...] = (
    # The vendor opening the form is what starts it; an officer typing on the vendor's
    # behalf (an Excel intake) is the same move.
    _t(S.INVITED, S.IN_PROGRESS, {R.VENDOR, R.OFFICER}, "Vendor opens the application."),
    _t(S.INVITED, S.WITHDRAWN, {R.VENDOR} | _STAFF, "Withdrawn before it was started."),
    _t(S.IN_PROGRESS, S.SUBMITTED, {R.VENDOR, R.OFFICER}, "Declaration signed and submitted."),
    _t(
        S.IN_PROGRESS,
        S.WITHDRAWN,
        {R.VENDOR, R.OFFICER, R.MANAGER, R.ADMIN},
        "Withdrawn, or marked incomplete after the deadline (spec §9).",
    ),
    _t(S.SUBMITTED, S.UNDER_REVIEW, _STAFF, "Officer starts the review."),
    _t(
        S.SUBMITTED,
        S.INFORMATION_REQUESTED,
        {R.OFFICER, R.MANAGER, R.ADMIN},
        "Officer sends it back before opening the rubric.",
    ),
    _t(
        S.UNDER_REVIEW,
        S.INFORMATION_REQUESTED,
        {R.OFFICER, R.COMMISSION, R.MANAGER, R.ADMIN},
        "Missing information requested from the vendor.",
    ),
    # Approval is the manager's, per spec §9 — the commission records a decision, the
    # manager grants prequalification.
    _t(S.UNDER_REVIEW, S.PREQUALIFIED, {R.MANAGER, R.ADMIN}, "Manager approves (spec §9)."),
    _t(
        S.UNDER_REVIEW,
        S.REJECTED,
        {R.COMMISSION, R.MANAGER, R.ADMIN},
        "Commission decision: rejected (D / F / KO).",
    ),
    _t(
        S.INFORMATION_REQUESTED,
        S.UNDER_REVIEW,
        {R.VENDOR, R.OFFICER, R.MANAGER, R.ADMIN},
        "Vendor supplied the missing data; review resumes.",
    ),
    _t(
        S.INFORMATION_REQUESTED,
        S.WITHDRAWN,
        {R.VENDOR, R.OFFICER, R.MANAGER, R.ADMIN},
        "Vendor gave up, or the deadline passed.",
    ),
)

_BY_EDGE: dict[tuple[ApplicationStatus, ApplicationStatus], Transition] = {
    (t.source, t.target): t for t in TRANSITIONS
}

#: Statuses nothing leaves. Re-qualification is a *new* application in a new cycle
#: (spec §9), which is why ``prequalified`` is terminal rather than looping back.
TERMINAL: frozenset[ApplicationStatus] = frozenset({S.PREQUALIFIED, S.REJECTED, S.WITHDRAWN})


def allowed_targets(source: ApplicationStatus, role: UserRole | None) -> list[ApplicationStatus]:
    """Where this role can move an application in this state — powers the UI's buttons."""
    return sorted(
        (t.target for t in TRANSITIONS if t.source is source and (role is None or role in t.roles)),
        key=lambda status: status.value,
    )


def can_transition(
    source: ApplicationStatus, target: ApplicationStatus, role: UserRole | None
) -> bool:
    transition = _BY_EDGE.get((source, target))
    return transition is not None and (role is None or role in transition.roles)


def assert_transition(
    source: ApplicationStatus, target: ApplicationStatus, role: UserRole | None
) -> Transition:
    """Raise the contract's error for the two distinct failures.

    A move that does not exist is ``409 conflict`` — the state is wrong. A move that exists
    but is not this role's is ``403 forbidden`` — the state is fine, the caller is not.
    """
    transition = _BY_EDGE.get((source, target))
    if transition is None:
        raise ApiError(
            409,
            "conflict",
            f"An application cannot move from {source.value} to {target.value}.",
            {
                "from": source.value,
                "to": target.value,
                "allowed": [status.value for status in allowed_targets(source, None)],
            },
        )
    if role is not None and role not in transition.roles:
        raise ApiError(
            403,
            "forbidden",
            f"Role {role.value} may not move an application from {source.value} to {target.value}.",
            {
                "from": source.value,
                "to": target.value,
                "roles": sorted(r.value for r in transition.roles),
            },
        )
    return transition


#: How an application status shows up on the vendor record (spec §5, §9).
VENDOR_STATUS_FOR_APPLICATION: dict[ApplicationStatus, VendorStatus] = {
    S.INVITED: VendorStatus.INVITED,
    S.IN_PROGRESS: VendorStatus.IN_PROGRESS,
    S.SUBMITTED: VendorStatus.SUBMITTED,
    S.UNDER_REVIEW: VendorStatus.UNDER_REVIEW,
    S.INFORMATION_REQUESTED: VendorStatus.INFORMATION_REQUESTED,
    S.PREQUALIFIED: VendorStatus.PREQUALIFIED,
    S.REJECTED: VendorStatus.REJECTED,
    # A withdrawn application leaves the vendor where it started: on the register, with
    # nothing in flight. It is not a rejection and must not read as one.
    S.WITHDRAWN: VendorStatus.REGISTERED,
}


def derive_vendor_status(
    application_status: ApplicationStatus, *, current: VendorStatus
) -> VendorStatus:
    """The vendor status an application outcome implies.

    ``suspended`` is sticky: it is a manager's decision about the vendor, not about any one
    application, and only :func:`vendors.suspend` clears it.
    """
    if current is VendorStatus.SUSPENDED:
        return VendorStatus.SUSPENDED
    return VENDOR_STATUS_FOR_APPLICATION[application_status]
