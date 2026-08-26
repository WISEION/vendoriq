"""openpyxl parsers for the 11-sheet application form and the Rev4 scoring workbook.

Fixtures live in ``seed/fixtures/`` — see ``seed/README.md``.

The importer is an *adapter* like any other (spec §6): it produces field observations with
``source = "excel"`` plus a list of warnings for the officer. It never writes to the
database itself — ``parse_application_form`` returns a mapping the officer confirms, and
only then does the API persist it (endpoints ``POST /integrations/excel-import/preview``
and ``POST /integrations/excel-import/runs``).

Two rules run through the whole package:

* **Cells are addressed by their code in column B**, never by row number, so a sheet that
  grew a row still parses (spec §6.1).
* **Nothing reads the clock.** Freshness questions are answered against the date the file
  itself carries, so a fixture parses to the same JSON today and next year.

```python
from vendoriq_excel_import import parse_application_form, parse_scoring_workbook

app = parse_application_form("WESA ….xlsx")
app.answers["A.3"]              # '1003915341'
app.to_observations(source_ref="WESA ….xlsx")

vendors = parse_scoring_workbook("Rev4 ….xlsx")
[(v.name, v.sheet_total, v.sheet_decision) for v in vendors]
```
"""

from __future__ import annotations

from .catalog import (
    DOCUMENT_CATALOG,
    FIELD_CATALOG,
    MANDATORY_FIELD_CODES,
    DocumentDef,
    FieldDef,
)
from .derive import derive_indicators
from .form import TAX_CLEARANCE_VALID_MONTHS, ParsedApplication, parse_application_form
from .normalise import WARNING_CODES, ImportWarning, Severity
from .workbook import RAW_INDICATOR_CODES, WorkbookVendor, parse_scoring_workbook, to_seed_rows

__version__ = "0.1.0"

__all__ = [
    "DOCUMENT_CATALOG",
    "FIELD_CATALOG",
    "MANDATORY_FIELD_CODES",
    "RAW_INDICATOR_CODES",
    "TAX_CLEARANCE_VALID_MONTHS",
    "WARNING_CODES",
    "DocumentDef",
    "FieldDef",
    "ImportWarning",
    "ParsedApplication",
    "Severity",
    "WorkbookVendor",
    "__version__",
    "derive_indicators",
    "parse_application_form",
    "parse_scoring_workbook",
    "to_seed_rows",
]
