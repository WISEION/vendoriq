"""The qualification state machine (spec §9).

Two failure modes are tested apart because they mean different things to a client:
a transition that does not exist is ``409`` (wrong state), one this role may not take is
``403`` (wrong caller).
"""

from __future__ import annotations

from typing import Any

import pytest
from vendoriq_api.errors import ApiError
from vendoriq_api.models.enums import ApplicationStatus as S
from vendoriq_api.models.enums import UserRole as R
from vendoriq_api.models.enums import VendorStatus
from vendoriq_api.services import state_machine

ALLOWED = [
    (S.INVITED, S.IN_PROGRESS, R.VENDOR),
    (S.INVITED, S.IN_PROGRESS, R.OFFICER),
    (S.INVITED, S.WITHDRAWN, R.VENDOR),
    (S.IN_PROGRESS, S.SUBMITTED, R.VENDOR),
    (S.IN_PROGRESS, S.SUBMITTED, R.OFFICER),
    (S.IN_PROGRESS, S.WITHDRAWN, R.OFFICER),
    (S.SUBMITTED, S.UNDER_REVIEW, R.OFFICER),
    (S.SUBMITTED, S.INFORMATION_REQUESTED, R.OFFICER),
    (S.UNDER_REVIEW, S.INFORMATION_REQUESTED, R.OFFICER),
    (S.UNDER_REVIEW, S.PREQUALIFIED, R.MANAGER),
    (S.UNDER_REVIEW, S.PREQUALIFIED, R.ADMIN),
    (S.UNDER_REVIEW, S.REJECTED, R.COMMISSION),
    (S.UNDER_REVIEW, S.REJECTED, R.MANAGER),
    (S.INFORMATION_REQUESTED, S.UNDER_REVIEW, R.VENDOR),
    (S.INFORMATION_REQUESTED, S.WITHDRAWN, R.VENDOR),
]

#: Edges that do not exist at all — the state is wrong, whoever asks.
NON_EXISTENT = [
    (S.INVITED, S.SUBMITTED),
    (S.INVITED, S.PREQUALIFIED),
    (S.IN_PROGRESS, S.UNDER_REVIEW),
    (S.SUBMITTED, S.PREQUALIFIED),
    (S.SUBMITTED, S.REJECTED),
    (S.PREQUALIFIED, S.UNDER_REVIEW),
    (S.PREQUALIFIED, S.IN_PROGRESS),
    (S.REJECTED, S.PREQUALIFIED),
    (S.WITHDRAWN, S.IN_PROGRESS),
    (S.UNDER_REVIEW, S.SUBMITTED),
]

#: Edges that exist but are closed to this role — the caller is wrong.
WRONG_ROLE = [
    (S.UNDER_REVIEW, S.PREQUALIFIED, R.OFFICER),
    (S.UNDER_REVIEW, S.PREQUALIFIED, R.COMMISSION),
    (S.UNDER_REVIEW, S.PREQUALIFIED, R.VENDOR),
    (S.UNDER_REVIEW, S.REJECTED, R.VENDOR),
    (S.UNDER_REVIEW, S.REJECTED, R.OFFICER),
    (S.SUBMITTED, S.UNDER_REVIEW, R.VENDOR),
    (S.IN_PROGRESS, S.SUBMITTED, R.COMMISSION),
    (S.SUBMITTED, S.INFORMATION_REQUESTED, R.VENDOR),
]


@pytest.mark.parametrize(("source", "target", "role"), ALLOWED)
def test_allowed_transitions(source: S, target: S, role: R) -> None:
    assert state_machine.can_transition(source, target, role)
    assert state_machine.assert_transition(source, target, role).note


@pytest.mark.parametrize(("source", "target"), NON_EXISTENT)
def test_a_transition_that_does_not_exist_is_a_conflict(source: S, target: S) -> None:
    """409 with the list of what *is* allowed, so the UI can say what to do instead."""
    with pytest.raises(ApiError) as raised:
        state_machine.assert_transition(source, target, R.ADMIN)
    assert raised.value.status_code == 409
    assert raised.value.code == "conflict"
    assert "allowed" in raised.value.details


@pytest.mark.parametrize(("source", "target", "role"), WRONG_ROLE)
def test_a_transition_closed_to_the_role_is_forbidden(source: S, target: S, role: R) -> None:
    """403, with the roles that may take it — the state was fine, the caller was not."""
    with pytest.raises(ApiError) as raised:
        state_machine.assert_transition(source, target, role)
    assert raised.value.status_code == 403
    assert raised.value.code == "forbidden"
    assert role.value not in raised.value.details["roles"]


def test_an_officer_cannot_approve_but_a_manager_can() -> None:
    """Spec §9: the commission records a decision, the manager grants prequalification."""
    assert not state_machine.can_transition(S.UNDER_REVIEW, S.PREQUALIFIED, R.OFFICER)
    assert state_machine.can_transition(S.UNDER_REVIEW, S.PREQUALIFIED, R.MANAGER)


def test_a_vendor_cannot_reject_or_prequalify_itself() -> None:
    for target in (S.PREQUALIFIED, S.REJECTED):
        assert not state_machine.can_transition(S.UNDER_REVIEW, target, R.VENDOR)


def test_terminal_states_have_no_outgoing_edges() -> None:
    """Re-qualification is a new application in a new cycle, not a loop (spec §9)."""
    for terminal in state_machine.TERMINAL:
        assert state_machine.allowed_targets(terminal, None) == []


def test_the_information_loop_goes_both_ways() -> None:
    """under_review ⇄ information_requested is the loop spec §9 draws."""
    assert state_machine.can_transition(S.UNDER_REVIEW, S.INFORMATION_REQUESTED, R.OFFICER)
    assert state_machine.can_transition(S.INFORMATION_REQUESTED, S.UNDER_REVIEW, R.VENDOR)


def test_allowed_targets_narrows_with_the_role() -> None:
    everyone = state_machine.allowed_targets(S.UNDER_REVIEW, None)
    officer = state_machine.allowed_targets(S.UNDER_REVIEW, R.OFFICER)
    assert set(officer) < set(everyone)
    assert S.PREQUALIFIED in everyone and S.PREQUALIFIED not in officer


# ── vendor status derivation ────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("application_status", "expected"),
    [
        (S.INVITED, VendorStatus.INVITED),
        (S.IN_PROGRESS, VendorStatus.IN_PROGRESS),
        (S.SUBMITTED, VendorStatus.SUBMITTED),
        (S.UNDER_REVIEW, VendorStatus.UNDER_REVIEW),
        (S.INFORMATION_REQUESTED, VendorStatus.INFORMATION_REQUESTED),
        (S.PREQUALIFIED, VendorStatus.PREQUALIFIED),
        (S.REJECTED, VendorStatus.REJECTED),
        # A withdrawal is not a rejection and must not read as one.
        (S.WITHDRAWN, VendorStatus.REGISTERED),
    ],
)
def test_vendor_status_is_derived_from_the_application(
    application_status: S, expected: VendorStatus
) -> None:
    derived = state_machine.derive_vendor_status(
        application_status, current=VendorStatus.REGISTERED
    )
    assert derived is expected


def test_suspension_outranks_the_application(monkeypatch: Any) -> None:
    """A suspended vendor stays suspended until a manager lifts it (spec §9)."""
    for application_status in S:
        derived = state_machine.derive_vendor_status(
            application_status, current=VendorStatus.SUSPENDED
        )
        assert derived is VendorStatus.SUSPENDED


def test_every_application_status_maps_to_a_vendor_status() -> None:
    """A new status added without a mapping would raise KeyError at runtime instead."""
    assert set(state_machine.VENDOR_STATUS_FOR_APPLICATION) == set(S)
