"""Typed access to ``seed/data.json`` (seed/README.md).

The file is a hand-maintained fixture, not generated, so this module's only job is to give
the loaders typed access to it and to handle the parsing quirks brief §1.11 documents once
— a multi-value VÖEN cell, the ``"Müddətsiz"`` (no expiry) literal — instead of in every
place that reads a vendor row.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TypedDict, cast

from ..config import REPO_ROOT

SEED_DIR = REPO_ROOT / "seed"
DATA_JSON_PATH = SEED_DIR / "data.json"

#: Named once so every writer stamps the same origin (README's "provenance" rule).
DATA_JSON_SOURCE_REF = "seed/data.json (Rev4 workbook TQS2026006)"


class HistoryEntry(TypedDict, total=False):
    cycle: str
    date: str
    total: float | None


class VendorRow(TypedDict, total=False):
    id: str
    name: str
    voen: int | str | None
    regYear: int | None
    address: str | None
    contact: str | None
    position: str | None
    phone: str | None
    email: str | None
    website: str | None
    staff: int | None
    engineers: int | None
    raw: dict[str, float | int]
    sheetTotal: float
    sheetKO: str
    sheetDecision: str
    cats: list[str]
    status: str
    source: str
    updated: str | None
    region: str | None
    type: str
    docs: dict[str, str | None]
    history: list[HistoryEntry]


class SupplierRow(TypedDict, total=False):
    id: str
    name: str
    voen: str | None
    regYear: int | None
    region: str | None
    contact: str | None
    email: str | None
    phone: str | None
    raw: dict[str, float | int]
    cats: list[str]
    status: str
    source: str
    updated: str | None
    type: str


class PackageRow(TypedDict, total=False):
    id: str
    cat: str
    certs: list[str]
    minClass: str
    value: float


class ProjectRow(TypedDict, total=False):
    id: str
    code: str
    name: str
    client: str | None
    stage: str
    value: float | None
    deadline: str | None
    packages: list[PackageRow]


class CategoryLabel(TypedDict):
    az: str
    en: str


@dataclass(frozen=True, slots=True)
class SeedData:
    """The whole of ``seed/data.json``, typed for the loaders."""

    vendors: tuple[VendorRow, ...]
    suppliers: tuple[SupplierRow, ...]
    projects: tuple[ProjectRow, ...]
    #: Category code -> {"az", "en"} — the 15-row taxonomy (brief §1.10).
    categories: dict[str, CategoryLabel]


def load_seed_data(path: Path = DATA_JSON_PATH) -> SeedData:
    """Read and type ``seed/data.json``. Called fresh each time — the file is 30 KB."""
    document = json.loads(path.read_text(encoding="utf-8"))
    return SeedData(
        vendors=tuple(cast(list[VendorRow], document["vendors"])),
        suppliers=tuple(cast(list[SupplierRow], document["suppliers"])),
        projects=tuple(cast(list[ProjectRow], document["projects"])),
        categories=cast(dict[str, CategoryLabel], document["cats"]),
    )


def parse_voen(raw: int | str | None) -> str | None:
    """Ten digits, or ``None``. A multi-value cell keeps the first (brief §1.11)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    return text or None


def parse_int(raw: int | str | None) -> int | None:
    """An integer, or ``None``. A multi-value cell keeps the first (brief §1.11).

    Gilan (V11) is two legal entities on one row: ``regYear`` reads ``"2006 / 2016"`` the
    same way its VÖEN and address do; the rule that already applies to those applies here.
    """
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw
    text = str(raw).strip()
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    return int(text) if text else None


def parse_date(text: str | None) -> date | None:
    """``"Müddətsiz"`` and blanks become ``None`` (brief §1.11); everything else is ISO."""
    if not text:
        return None
    stripped = text.strip()
    if not stripped or stripped.casefold() == "müddətsiz":
        return None
    return date.fromisoformat(stripped)
