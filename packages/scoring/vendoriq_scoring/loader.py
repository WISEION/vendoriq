"""Loading a model version from the JSON that ships with the package.

The JSON is a contract (CONTRIBUTING): weights, thresholds and KO flags are changed by
creating a *new version* through the model editor, never by editing a published file.
Versions created that way live in the database and are built with ``ScoringModel(**row)``
instead of going through this loader.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast

from .types import ClassBand, Criterion, GroupDef, ModelStatusName, ScoringModel, VendorTypeName

__all__ = ["BUILTIN_MODEL_VERSIONS", "MODELS_DIR", "load_model", "model_from_dict"]

MODELS_DIR = Path(__file__).parent / "models"

#: Versions shipped with the system. New versions are created through the model editor.
BUILTIN_MODEL_VERSIONS = ("sub-4", "sup-1")


def model_from_dict(document: dict[str, object]) -> ScoringModel:
    """Build a :class:`ScoringModel` from a plain mapping (JSON file or database row)."""
    return ScoringModel(
        version=cast(str, document["version"]),
        vendor_type=cast(VendorTypeName, document["vendor_type"]),
        name_az=cast(str, document["name_az"]),
        name_en=cast(str, document["name_en"]),
        status=cast(ModelStatusName, document["status"]),
        pass_mark=cast(float, document["pass_mark"]),
        validity_months=cast(int, document["validity_months"]),
        currency=cast(str, document["currency"]),
        total_max=cast(float, document["total_max"]),
        groups=cast(list[GroupDef], document["groups"]),
        criteria=cast(list[Criterion], document["criteria"]),
        classes=cast(list[ClassBand], document["classes"]),
        source=cast(str, document.get("source", "")),
    )


@lru_cache
def load_model(version: str) -> ScoringModel:
    """Load a built-in model version from ``vendoriq_scoring/models/<version>.json``.

    Raises ``FileNotFoundError`` for an unknown version.
    """
    path = MODELS_DIR / f"{version}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return model_from_dict(document)
