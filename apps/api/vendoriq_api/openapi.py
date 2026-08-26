"""Serve the hand-written contract instead of FastAPI's generated schema.

``docs/openapi.yaml`` is the source of truth for every endpoint (CONTRIBUTING.md:
no contract change without the orchestrator). Phase 1+ route handlers are validated
against it, they do not generate it.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .config import REPO_ROOT

OPENAPI_PATH: Path = REPO_ROOT / "docs" / "openapi.yaml"


@lru_cache
def load_contract() -> dict[str, Any]:
    """Parse ``docs/openapi.yaml`` once per process."""
    with OPENAPI_PATH.open("r", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):  # pragma: no cover - corrupt file
        raise RuntimeError(f"{OPENAPI_PATH} did not parse to a mapping")
    return document


def contract_yaml() -> str:
    """Raw YAML text, served verbatim at ``/api/openapi.yaml``."""
    return OPENAPI_PATH.read_text(encoding="utf-8")
