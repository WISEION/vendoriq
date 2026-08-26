"""Every enum value the contract can put on screen has a string in both dictionaries.

Brief §7.5 requires "no untranslated keys". The failure this guards against is specific and
has already happened once: the matching engine emits a `gap` and per-candidate `reasons`, the
web app renders them through `t(key)`, and only two of the eleven values had a dictionary
entry — so a real matching result would have rendered raw identifiers like
`no_vendor_in_category` to a manager.

The check is keyed off `docs/openapi.yaml` rather than off the engine's constants because the
contract is what both sides already agree on: the engine may not emit a value the contract
does not declare, and the web app may not receive one. Adding a value to an enum without a
translation now fails here instead of on screen.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from vendoriq_api.openapi import load_contract

REPO_ROOT = Path(__file__).resolve().parents[3]
I18N = REPO_ROOT / "apps" / "web" / "src" / "i18n"
LANGUAGES = ("az", "en")

#: Enums whose values reach the screen as i18n keys, as `(schema, property)`. A value that is
#: rendered as itself — an id, a code, a class letter — does not belong here.
TRANSLATED_ENUMS: tuple[tuple[str, str], ...] = (
    ("PackageMatch", "gap"),
    ("MatchCandidate", "reasons"),
)


def _dictionary(language: str) -> dict[str, str]:
    """The shared dictionary plus every per-feature one, merged as the web app merges them.

    `src/i18n/index.ts` folds `features/<name>.<lang>.json` over the shared file so each
    phase-2 feature owns its own strings. Reading only the shared file here would make this
    check blind to exactly the keys the feature teams add — which is most of them.
    """
    text = (I18N / f"{language}.json").read_text(encoding="utf-8")
    merged: dict[str, str] = json.loads(text)
    for feature in sorted((I18N / "features").glob(f"*.{language}.json")):
        merged.update(json.loads(feature.read_text(encoding="utf-8")))
    return merged


def _enum_values(schema: dict[str, Any], prop: str) -> list[str]:
    definition = schema["properties"][prop]
    # An array property carries its enum on `items`; a scalar carries it directly.
    holder = definition.get("items", definition)
    return [value for value in holder["enum"] if isinstance(value, str)]


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize(("schema_name", "prop"), TRANSLATED_ENUMS)
def test_every_rendered_enum_value_is_translated(
    language: str, schema_name: str, prop: str
) -> None:
    contract = load_contract()
    values = _enum_values(contract["components"]["schemas"][schema_name], prop)
    assert values, f"{schema_name}.{prop} declares no enum — the check would pass vacuously"

    dictionary = _dictionary(language)
    missing = [value for value in values if not dictionary.get(value, "").strip()]
    assert not missing, (
        f"{schema_name}.{prop} values with no {language}.json string: {sorted(missing)}"
    )


def test_the_two_dictionaries_declare_the_same_keys() -> None:
    """A key present in one language only renders as its own identifier in the other."""
    az, en = (_dictionary(language) for language in LANGUAGES)

    assert az.keys() == en.keys(), {
        "az_only": sorted(az.keys() - en.keys()),
        "en_only": sorted(en.keys() - az.keys()),
    }


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_dictionary_entry_is_empty(language: str) -> None:
    blank = sorted(key for key, value in _dictionary(language).items() if not value.strip())

    assert not blank, f"{language}.json has empty strings for: {blank}"
