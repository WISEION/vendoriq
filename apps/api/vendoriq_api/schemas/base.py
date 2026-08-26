"""Shared base: the strict ``Model``, page metadata and the e-mail constraint.

The package this module heads is described in ``__init__.py``. Original note, still true:
shapes are transcribed from ``docs/openapi.yaml``.

These models do **not** generate the published schema (ADR-006 — the hand-written contract
is served verbatim). They exist so the handlers parse and serialise exactly what the
contract declares, and ``tests/test_contract_shapes.py`` checks the two against each other.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

#: ``format: email`` from the contract. ``email-validator`` is a PyPI-only dependency and
#: PyPI is blocked on the build host (ADR-005), so the shape is enforced by pattern instead:
#: one ``@``, a dot in the domain, no whitespace. Addresses are lower-cased on the way in so
#: ``Habib@wesa.az`` and ``habib@wesa.az`` are one account.
EmailStr = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),
]


class Model(BaseModel):
    """Base: reject unknown keys, so a client typo is a 422 rather than a silent no-op."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class PageMeta(Model):
    total: int
    page: int
    page_size: int
