"""The data model is a contract: every entity of spec §5 exists with the agreed columns."""

from __future__ import annotations

import pytest
from sqlalchemy import UniqueConstraint
from vendoriq_api.models import SOURCE_TRUST_RANK, Base, ObservationSource

EXPECTED_TABLES = {
    "adapter_config",
    "api_key",
    "app_user",
    "application",
    "audit_event",
    "category",
    "contact",
    "document",
    "evaluation",
    "event",
    "field_observation",
    "import_preview",
    "match_run",
    "otp_code",
    "performance_record",
    "project",
    "qualification_cycle",
    "scoring_model",
    "setting",
    "sync_log",
    "vendor",
    "vendor_category",
    "webhook",
    "work_package",
}


def test_every_spec_entity_has_a_table() -> None:
    """Equality, not containment: a table nobody declared is as wrong as a missing one.

    `adapter_config` and `import_preview` are not in spec §5's entity table. They were added
    by migration 0004 because the integration layer needed somewhere real to keep per-vendor
    connector settings and a parsed workbook awaiting confirmation — see ADR-014's sibling
    reasoning and the migration's own docstring. Listing them here is the deliberate act this
    assertion exists to force.
    """
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_vendor_columns() -> None:
    columns = Base.metadata.tables["vendor"].columns
    for name in (
        "id",
        "legal_name",
        "voen",
        "type",
        "legal_form",
        "registration_year",
        "address",
        "region",
        "website",
        "status",
        "external_ref",
        "is_demo",
        "created_at",
        "updated_at",
    ):
        assert name in columns, name
    assert columns["voen"].unique is True


def test_voen_is_constrained_to_ten_digits() -> None:
    constraints = {c.name for c in Base.metadata.tables["vendor"].constraints}
    assert "ck_vendor_voen_ten_digits" in constraints


def test_application_carries_snapshot_and_computed_scores() -> None:
    columns = Base.metadata.tables["application"].columns
    for name in (
        "raw_snapshot",
        "rubric_scores",
        "computed",
        "declaration",
        "decision",
        "justification",
        "decided_by",
        "decided_at",
    ):
        assert name in columns, name


def test_the_second_evaluator_is_a_row_not_a_column() -> None:
    """Migration 0002: ``application.second_rubric`` became the ``evaluation`` table.

    A column could hold exactly one extra opinion and could not say whose it was. The table
    holds any number, names the evaluator, and marks which set the decision was taken from
    (spec §10.3).
    """
    assert "second_rubric" not in Base.metadata.tables["application"].columns
    evaluation = Base.metadata.tables["evaluation"].columns
    for name in (
        "application_id",
        "evaluator_id",
        "rubric",
        "computed",
        "is_primary",
        "created_at",
    ):
        assert name in evaluation, name
    unique = {
        tuple(sorted(column.name for column in constraint.columns))
        for constraint in Base.metadata.tables["evaluation"].constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("application_id", "evaluator_id") in unique


def test_observation_trust_rank_is_generated_by_the_database() -> None:
    column = Base.metadata.tables["field_observation"].columns["trust_rank"]
    assert column.computed is not None
    assert column.computed.persisted is True


@pytest.mark.parametrize("source", list(ObservationSource))
def test_every_source_has_a_trust_rank(source: ObservationSource) -> None:
    assert SOURCE_TRUST_RANK[source] in {1, 2, 3, 4, 5}


def test_scoring_model_is_keyed_by_version() -> None:
    table = Base.metadata.tables["scoring_model"]
    assert [c.name for c in table.primary_key.columns] == ["version"]
    assert "is_locked" in table.columns
