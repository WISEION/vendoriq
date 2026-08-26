"""Remote payload → field observations.

Every adapter that reads a structured payload — the generic REST connector, the CSV
connector and the three mocked ERP families — shares this file. The remote shape differs
(1C nests under ``Kontragent``, SAP under ``d.results[0]``, Odoo returns a flat record);
the *mapping* does not, because the difference is expressed in the configured
``field_map``, not in code.

``field_map`` is ``{remote path: VendorIQ field code}``. The path is dotted, and a numeric
segment indexes a list: ``d.results.0.AnnualTurnover``. A path that the payload does not
carry produces no observation and no error — a source that does not know a field has said
nothing about it, which is different from saying it is empty (ADR-004).

Values are normalised with ``vendoriq_excel_import.normalise`` rather than a second
implementation: "1 250 000", "1,250" and "85%" mean the same thing whether a human typed
them into a spreadsheet or an ERP exported them into a CSV column.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from vendoriq_excel_import import ImportWarning
from vendoriq_excel_import.normalise import (
    clean_text,
    is_blank,
    normalise_bool,
    normalise_number,
)

from ..models.enums import ObservationSource
from .base import Observation

#: Field-code prefixes whose values are numbers. Everything else stays as the source sent it.
_NUMERIC_PREFIXES = ("B.", "C.", "E.", "A.2")
#: Field codes the form records as a Yes/No answer.
_BOOLEAN_CODES = frozenset({"A.11", "A.12", "A.13", "A.15", "F.1", "F.3", "F.4", "G.1", "G.3"})


def parse_json(raw: bytes | str) -> Any:
    """Decode a JSON payload, or say plainly that it was not JSON."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    return json.loads(text)


def parse_csv(raw: bytes | str) -> dict[str, str]:
    """First data row of a single-vendor CSV extract, keyed by its header.

    A CSV connector is defined by the system for "any other ERP" (spec §6.3), and the
    contract it publishes is one row per vendor. Extra rows are ignored rather than merged:
    guessing which of two conflicting rows is the vendor would be inventing a value.
    """
    text = raw.decode("utf-8-sig", errors="replace") if isinstance(raw, bytes) else raw
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        return {
            str(key): ("" if value is None else str(value)) for key, value in row.items() if key
        }
    return {}


def resolve_path(payload: Any, path: str) -> Any:
    """Walk a dotted path; a numeric segment indexes a sequence. Missing → ``None``."""
    current = payload
    for segment in path.split("."):
        if current is None:
            return None
        if isinstance(current, Mapping):
            current = current.get(segment)
        elif isinstance(current, Sequence) and not isinstance(current, str | bytes):
            if not segment.isdigit():
                return None
            index = int(segment)
            current = current[index] if index < len(current) else None
        else:
            return None
    return current


def coerce(field_code: str, value: Any) -> Any:
    """Give a remote value the shape the field catalogue expects.

    CSV hands everything over as text; JSON is typed but an ERP still exports "1 250 000"
    as a string often enough to matter. Coercion is by field code, and a value that will
    not convert is kept verbatim rather than dropped — the officer sees what arrived.
    """
    if isinstance(value, list | dict):
        return value
    if field_code in _BOOLEAN_CODES:
        parsed_bool = normalise_bool(value)
        return value if parsed_bool is None else parsed_bool
    if field_code.startswith(_NUMERIC_PREFIXES):
        number = normalise_number(value)
        return value if number is None else number
    return clean_text(value) if isinstance(value, str) else value


def observations_from(
    payload: Any,
    field_map: Mapping[str, str],
    *,
    source: ObservationSource,
    source_ref: str,
    observed_at: datetime | None = None,
) -> tuple[list[Observation], list[ImportWarning]]:
    """Apply ``field_map`` to ``payload``. Absent paths are silent; unusable ones warn."""
    observations: list[Observation] = []
    warnings: list[ImportWarning] = []
    for remote_path, field_code in field_map.items():
        raw = resolve_path(payload, remote_path)
        if raw is None or is_blank(raw):
            continue
        value = coerce(field_code, raw)
        if isinstance(value, str) and field_code.startswith(_NUMERIC_PREFIXES):
            warnings.append(
                ImportWarning(
                    code="unparsable_value",
                    message_en=(
                        f"{field_code}: the source returned «{value}», which is not a number; "
                        "kept as text."
                    ),
                    message_az=(
                        f"{field_code}: mənbə «{value}» qaytardı, bu rəqəm deyil; "
                        "mətn kimi saxlanıldı."
                    ),
                    severity="warning",
                    field_code=field_code,
                    raw_value=str(raw),
                )
            )
        observations.append(
            Observation(
                field_code=field_code,
                value=value,
                source=source,
                source_ref=f"{source_ref}#{remote_path}",
                observed_at=observed_at,
            )
        )
    return observations, warnings
