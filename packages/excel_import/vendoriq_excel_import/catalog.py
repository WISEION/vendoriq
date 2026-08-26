"""The application field and document catalogues, and the sheet layout of the form.

Transcribed from spec Appendix A and Appendix B (the same rows the prototype carries in
``seed/data.json``). The importer keys everything on these codes: a cell is found by its
code in column B, never by row number, so an inserted row does not move an answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: What a cell holds. ``calc`` cells are the form's own formulas — the importer ignores
#: them and recomputes the derived indicators itself.
FieldKind = Literal["text", "number", "date", "bool", "calc", "table"]


@dataclass(frozen=True, slots=True)
class FieldDef:
    """One row of the field catalogue (spec Appendix A)."""

    code: str
    section: str
    kind: FieldKind
    #: Document code the answer must be evidenced by, ``None`` when the form asks for none.
    doc: str | None
    #: ``True`` for the three knock-out questions — an empty cell is an import error.
    mandatory: bool
    name_az: str
    name_en: str


@dataclass(frozen=True, slots=True)
class DocumentDef:
    """One row of the document checklist (spec Appendix B)."""

    code: str
    name_az: str
    name_en: str
    mandatory: bool


_FIELDS: tuple[FieldDef, ...] = (
    FieldDef("A.1", "A", "text", "A-01", False, "Şirkətin tam rəsmi adı", "Full legal name"),
    FieldDef("A.2", "A", "text", "A-02", False, "Ticarət reyestr nömrəsi", "Trade register number"),
    FieldDef("A.3", "A", "text", "A-02", False, "VÖEN", "Tax ID (VÖEN)"),
    FieldDef("A.4", "A", "number", "A-02", False, "Qeydiyyat ili", "Year of registration"),
    FieldDef("A.5", "A", "text", "A-03", False, "Hüquqi ünvan (tam)", "Legal address"),
    FieldDef("A.6", "A", "text", None, False, "Əsas əlaqə şəxsi", "Primary contact"),
    FieldDef("A.7", "A", "text", None, False, "Vəzifəsi", "Position"),
    FieldDef("A.8", "A", "text", None, False, "Telefon / WhatsApp", "Phone / WhatsApp"),
    FieldDef("A.9", "A", "text", None, False, "E-poçt", "E-mail"),
    FieldDef("A.10", "A", "text", None, False, "Veb sayt", "Website"),
    FieldDef(
        "A.11",
        "A",
        "bool",
        "A-04",
        True,
        "Tikinti lisenziyası mövcuddurmu? ⚠ MƏCBURİ",
        "Construction licence held? ⚠ MANDATORY",
    ),
    FieldDef("A.12", "A", "text", "A-04", False, "Lisenziyanın nömrəsi", "Licence number"),
    FieldDef("A.13", "A", "date", "A-04", False, "Verilmə tarixi", "Issue date"),
    FieldDef("A.14", "A", "date", "A-04", False, "Etibarlılıq müddəti", "Valid until"),
    FieldDef(
        "A.15",
        "A",
        "bool",
        "A-05",
        True,
        "Vergi borcsuzluğu arayışı (son 3 ay) ⚠ MƏCBURİ",
        "Tax clearance certificate (last 3 months) ⚠ MANDATORY",
    ),
    FieldDef("A.16", "A", "date", "A-05", False, "Arayışın verilmə tarixi", "Certificate date"),
    FieldDef("A.17", "A", "text", "A-03", False, "Təsis forması", "Legal form"),
    FieldDef("A.18", "A", "number", "A-06", False, "Təsisçilərin sayı", "Number of founders"),
    FieldDef(
        "A.19", "A", "number", "A-03", False, "Nizamnamə kapitalı (AZN)", "Charter capital (AZN)"
    ),
    FieldDef("A.20", "A", "text", "A-07", False, "IBAN", "IBAN"),
    FieldDef(
        "B.1", "B", "number", "B-01", False, "Son tam il üzrə dövriyyə", "Turnover, last full year"
    ),
    FieldDef("B.2", "B", "number", "B-01", False, "İkinci son il", "Year −2"),
    FieldDef("B.3", "B", "number", "B-01", False, "Üçüncü son il", "Year −3"),
    FieldDef(
        "B.4",
        "B",
        "calc",
        None,
        False,
        "Son 3 ilin orta dövriyyəsi (avtomatik)",
        "3-year average (auto)",
    ),
    FieldDef("B.5", "B", "number", "B-02", False, "Öz kapitalı (Equity)", "Equity"),
    FieldDef("B.6", "B", "number", "B-02", False, "Cari aktivlər", "Current assets"),
    FieldDef("B.7", "B", "number", "B-02", False, "Cari öhdəliklər", "Current liabilities"),
    FieldDef(
        "B.8", "B", "calc", None, False, "Likvidlik əmsalı (avtomatik)", "Current ratio (auto)"
    ),
    FieldDef(
        "B.9", "B", "bool", "B-03", False, "Bank kredit xətti mövcuddurmu?", "Bank credit line?"
    ),
    FieldDef("B.10", "B", "number", "B-03", False, "Kredit xəttinin məbləği", "Credit line amount"),
    FieldDef("B.11", "B", "text", "B-03", False, "Bank adı", "Bank"),
    FieldDef(
        "B.12",
        "B",
        "bool",
        "B-04",
        False,
        "Son 3 ildə audit olmuşdurmu?",
        "Audited in last 3 years?",
    ),
    FieldDef("B.13", "B", "text", "B-04", False, "Audit şirkəti", "Audit firm"),
    FieldDef(
        "C.t1",
        "C",
        "table",
        "C-01",
        False,
        "Layihə cədvəli: ad, sifarişçi, başlama, bitmə, müddət, dəyər, tip",
        "Project table: name, client, start, end, duration, value, type",
    ),
    FieldDef(
        "C.t2",
        "C",
        "table",
        None,
        False,
        "Layihə cədvəli: ad, sifarişçi, başlama, planlanan bitmə, %, dəyər",
        "Table: name, client, start, planned end, %, value",
    ),
    FieldDef("C.1", "C", "bool", "C-02", False, "ISO 9001 mövcuddurmu?", "ISO 9001 held?"),
    FieldDef("C.2", "C", "text", "C-02", False, "Sertifikatın nömrəsi", "Certificate number"),
    FieldDef("C.3", "C", "date", "C-02", False, "Etibarlılıq tarixi", "Valid until"),
    FieldDef("D.1", "D", "text", "D-01", False, "Baş ofisin ünvanı", "Head office address"),
    FieldDef("D.2", "D", "number", "D-01", False, "Ofis sahəsi (m²)", "Office area (m²)"),
    FieldDef(
        "D.3", "D", "text", "D-01", False, "Mülkiyyət forması (öz/kira)", "Ownership (own/rent)"
    ),
    FieldDef("D.4", "D", "number", "D-01", False, "Emalatxana sahəsi (m²)", "Workshop area (m²)"),
    FieldDef("D.5", "D", "number", "D-01", False, "Anbar sahəsi (m²)", "Warehouse area (m²)"),
    FieldDef(
        "D.6",
        "D",
        "number",
        "D-02",
        False,
        "İnşaat avadanlıqlarının ümumi sayı",
        "Total construction equipment",
    ),
    FieldDef("D.7", "D", "number", "D-02", False, "Kran / yük qaldırıcı", "Cranes / hoists"),
    FieldDef(
        "D.8", "D", "number", "D-02", False, "Beton qarışdırıcı və nasos", "Concrete mixers & pumps"
    ),
    FieldDef(
        "D.9",
        "D",
        "number",
        "D-02",
        False,
        "Qaynaq və metal emal avadanlığı",
        "Welding & metalwork equipment",
    ),
    FieldDef("D.10", "D", "number", "D-02", False, "Elektrik alət dəstləri", "Power tool sets"),
    FieldDef("D.11", "D", "number", "D-03", False, "Yük maşınları", "Trucks"),
    FieldDef("D.12", "D", "number", "D-03", False, "Mikroavtobus / minik", "Vans / cars"),
    FieldDef(
        "D.13",
        "D",
        "number",
        "D-03",
        False,
        "İxtisas texnikası (ekskavator, buldozer)",
        "Heavy machinery",
    ),
    FieldDef(
        "D.14",
        "D",
        "bool",
        "D-03",
        False,
        "Bütün nəqliyyat sığortalıdırmı?",
        "All vehicles insured?",
    ),
    FieldDef("E.1", "E", "number", "E-01", False, "Ümumi daimi heyət", "Permanent staff"),
    FieldDef("E.2", "E", "number", "E-01", False, "Müvəqqəti / müqaviləli", "Temporary / contract"),
    FieldDef("E.3", "E", "number", "E-01", False, "İnzibati heyət", "Administrative staff"),
    FieldDef(
        "E.4",
        "E",
        "number",
        "E-02",
        False,
        "Baş mühəndis / texniki direktor",
        "Chief engineer / technical director",
    ),
    FieldDef("E.5", "E", "number", "E-02", False, "Tikinti mühəndisləri", "Civil engineers"),
    FieldDef("E.6", "E", "number", "E-02", False, "Memarlar", "Architects"),
    FieldDef("E.7", "E", "number", "E-02", False, "Elektrik mühəndisləri", "Electrical engineers"),
    FieldDef(
        "E.8", "E", "number", "E-02", False, "MEP / HVAC mühəndisləri", "MEP / HVAC engineers"
    ),
    FieldDef(
        "E.9", "E", "number", "E-02", False, "Texniklər (usta, texnik)", "Technicians / foremen"
    ),
    FieldDef("E.10", "E", "number", "E-01", False, "İxtisaslı fəhlələr", "Skilled workers"),
    FieldDef("E.11", "E", "number", "E-01", False, "Köməkçi fəhlələr", "Unskilled workers"),
    FieldDef(
        "E.12",
        "E",
        "bool",
        "E-03",
        False,
        "Tam ştatlı SƏTƏMM mütəxəssisi varmı?",
        "Full-time HSE specialist?",
    ),
    FieldDef(
        "E.13",
        "E",
        "bool",
        "E-03",
        False,
        "SƏTƏMM ixtisas sertifikatı",
        "HSE specialist certified?",
    ),
    FieldDef("E.14", "E", "number", "E-02", False, "Keyfiyyət nəzarət heyəti", "QC staff"),
    FieldDef(
        "E.15",
        "E",
        "number",
        "E-04",
        False,
        "Daimi subpodratçıların sayı",
        "Regular subcontractors",
    ),
    FieldDef(
        "E.16",
        "E",
        "bool",
        "E-04",
        False,
        "Müqavilələr rəsmiləşdirilibmi?",
        "Contracts formalised?",
    ),
    FieldDef(
        "F.1",
        "F",
        "bool",
        "F-01",
        True,
        "SƏTƏMM siyasəti sənədi varmı? ⚠ MƏCBURİ",
        "HSE policy document? ⚠ MANDATORY",
    ),
    FieldDef("F.2", "F", "date", "F-01", False, "SƏTƏMM planının tarixi", "HSE plan date"),
    FieldDef(
        "F.3",
        "F",
        "bool",
        "F-02",
        False,
        "İşçilərə SƏTƏMM təlimi keçirilirmi?",
        "HSE training delivered?",
    ),
    FieldDef(
        "F.4", "F", "number", "F-02", False, "İl ərzində təlim saatları", "Training hours / year"
    ),
    FieldDef("F.5", "F", "bool", "F-03", False, "ISO 14001 varmı?", "ISO 14001?"),
    FieldDef("F.6", "F", "text", "F-03", False, "Nömrə", "Number"),
    FieldDef("F.7", "F", "date", "F-03", False, "Etibarlılıq", "Valid until"),
    FieldDef("F.8", "F", "bool", "F-04", False, "ISO 45001 varmı?", "ISO 45001?"),
    FieldDef("F.9", "F", "text", "F-04", False, "Nömrə", "Number"),
    FieldDef("F.10", "F", "date", "F-04", False, "Etibarlılıq", "Valid until"),
    FieldDef("F.11", "F", "number", "F-05", False, "Ölümlə nəticələnən hadisə", "Fatalities"),
    FieldDef("F.12", "F", "number", "F-05", False, "Ağır xəsarət", "Serious injuries"),
    FieldDef(
        "F.13", "F", "number", "F-05", False, "İş günü itkisi ilə hadisə", "Lost-time incidents"
    ),
    FieldDef("F.14", "F", "number", "F-05", False, "LTIR (son il)", "LTIR (last year)"),
    FieldDef(
        "F.15",
        "F",
        "bool",
        "F-06",
        False,
        "Bütün işçilər FMV ilə təmin olunurmu?",
        "All workers issued PPE?",
    ),
    FieldDef(
        "F.16", "F", "bool", "F-06", False, "FMV keyfiyyət sertifikatı", "PPE quality certificate?"
    ),
    FieldDef(
        "G.1",
        "G",
        "bool",
        "G-01",
        False,
        "Peşəkar məsuliyyət sığortası varmı?",
        "Professional liability insurance?",
    ),
    FieldDef("G.2", "G", "text", "G-01", False, "Sığorta şirkəti", "Insurer"),
    FieldDef("G.3", "G", "text", "G-01", False, "Polis nömrəsi", "Policy number"),
    FieldDef("G.4", "G", "number", "G-01", False, "Sığorta məbləği (AZN)", "Cover limit (AZN)"),
    FieldDef("G.5", "G", "date", "G-01", False, "Etibarlılıq tarixi", "Valid until"),
    FieldDef(
        "G.6",
        "G",
        "bool",
        "G-01",
        False,
        "Ümumi məsuliyyət sığortası varmı?",
        "General liability insurance?",
    ),
    FieldDef("G.7", "G", "number", "G-01", False, "Sığorta məbləği (AZN)", "Cover limit (AZN)"),
    FieldDef(
        "G.t1",
        "G",
        "table",
        "G-02",
        False,
        "Referans cədvəli: müştəri, layihə, əlaqə şəxsi, məktub",
        "Reference table: client, project, contact, letter",
    ),
)

#: code -> definition, in catalogue order.
FIELD_CATALOG: dict[str, FieldDef] = {f.code: f for f in _FIELDS}

#: The three knock-out questions (brief §1.2). An empty cell is reported as an error.
MANDATORY_FIELD_CODES: tuple[str, ...] = tuple(f.code for f in _FIELDS if f.mandatory)

_DOCUMENTS: tuple[DocumentDef, ...] = (
    DocumentDef(
        "A-01", "Şirkətin dövlət qeydiyyatı sənədi", "State registration certificate", True
    ),
    DocumentDef(
        "A-02", "VÖEN və Ticarət reyestri çıxarışı", "Tax ID & trade register extract", True
    ),
    DocumentDef("A-03", "Nizamnamə (son redaksiyası)", "Charter (latest)", True),
    DocumentDef("A-04", "Tikinti lisenziyası (qüvvədə)", "Construction licence (valid)", True),
    DocumentDef(
        "A-05", "Vergi borcsuzluğu arayışı (son 3 ay)", "Tax clearance (last 3 months)", True
    ),
    DocumentDef("A-06", "Təsisçilərin şəxsiyyət vəsiqəsi", "Founders' ID copies", False),
    DocumentDef("A-07", "Bank rekvizitləri (IBAN)", "Bank details (IBAN letter)", False),
    DocumentDef("B-01", "Son 3 ilin mənfəət-zərər hesabatı", "P&L, last 3 years", True),
    DocumentDef("B-02", "Son ilin balans hesabatı", "Balance sheet, last year", True),
    DocumentDef("B-03", "Bank kredit xətti məktubu", "Bank credit line letter", False),
    DocumentDef("B-04", "Auditdən keçmiş hesabat", "Audited financial statement", False),
    DocumentDef(
        "C-01",
        "Layihə sertifikatları və müştəri məktubları",
        "Project certificates & client letters",
        True,
    ),
    DocumentDef("C-02", "ISO 9001 sertifikatı", "ISO 9001 certificate", False),
    DocumentDef(
        "D-01", "Ofis/emalatxana mülkiyyət/kira müqaviləsi", "Office/workshop title or lease", False
    ),
    DocumentDef("D-02", "Avadanlıq siyahısı və şəkilləri", "Equipment list & photos", False),
    DocumentDef("D-03", "Nəqliyyat texniki pasportları", "Vehicle registration documents", False),
    DocumentDef("E-01", "İşçi heyətinin siyahısı", "Staff list (counts)", True),
    DocumentDef("E-02", "Mühəndis diplomları", "Engineers' diplomas", False),
    DocumentDef("E-03", "SƏTƏMM mütəxəssisinin sertifikatı", "HSE specialist certificate", False),
    DocumentDef(
        "E-04", "Subpodratçı müqavilələri siyahısı", "Subcontractor agreements list", False
    ),
    DocumentDef("F-01", "SƏTƏMM siyasəti və planı", "HSE policy & plan", True),
    DocumentDef("F-02", "SƏTƏMM təlim jurnalı", "HSE training log", False),
    DocumentDef("F-03", "ISO 14001 sertifikatı", "ISO 14001 certificate", False),
    DocumentDef("F-04", "ISO 45001 sertifikatı", "ISO 45001 certificate", False),
    DocumentDef("F-05", "Bədbəxt hadisə hesabatı (3 il)", "Accident report (3 years)", False),
    DocumentDef("F-06", "FMV sertifikatları", "PPE certificates", False),
    DocumentDef("G-01", "Məsuliyyət sığortası polisi", "Liability insurance policy", False),
    DocumentDef(
        "G-02", "Müştəri referans məktubları (min 3)", "Client reference letters (min 3)", True
    ),
    DocumentDef("H-01", "Rəhbərin imzaladığı Bəyannamə", "Signed declaration", True),
    DocumentDef("H-02", "Möhürlə təsdiq olunmuş forma", "Stamped form", True),
)

#: code -> definition, in catalogue order (A-01 … H-02).
DOCUMENT_CATALOG: dict[str, DocumentDef] = {d.code: d for d in _DOCUMENTS}


# --------------------------------------------------------------------------------------
# Sheet layout
#
# Sheets are resolved by the integer that starts their name ("4. C. Texniki Təcrübə" -> 4)
# rather than by the whole title, so a renamed sheet still parses. Within a sheet, rows are
# found by the code in column B; only the *columns* are positional, and section C puts its
# three answers in G/I instead of E/F because the sheet is a wide project table.
# --------------------------------------------------------------------------------------

#: Column holding the field / document code on every section sheet.
CODE_COL = "B"
#: Column holding the question text.
QUESTION_COL = "C"
#: Column holding the unit / format hint ("AZN", "nəfər", "dd.mm.yyyy", "Var/Yoxdur").
UNIT_COL = "D"


@dataclass(frozen=True, slots=True)
class SectionSheet:
    """Where the answers of one A–G section live."""

    #: Leading number of the sheet name.
    index: int
    section: str
    answer_col: str
    doc_col: str


SECTION_SHEETS: tuple[SectionSheet, ...] = (
    SectionSheet(2, "A", "E", "F"),
    SectionSheet(3, "B", "E", "F"),
    SectionSheet(4, "C", "G", "I"),
    SectionSheet(5, "D", "E", "F"),
    SectionSheet(6, "E", "E", "F"),
    SectionSheet(7, "F", "E", "F"),
    SectionSheet(8, "G", "E", "F"),
)

COVER_SHEET_INDEX = 0
DOCUMENTS_SHEET_INDEX = 9
DECLARATION_SHEET_INDEX = 10


@dataclass(frozen=True, slots=True)
class TableColumn:
    """One column of a section table, as an offset from the row-number column."""

    key: str
    offset: int
    kind: FieldKind | Literal["percent"]


@dataclass(frozen=True, slots=True)
class TableDef:
    """A section table: the block title that introduces it and its columns."""

    code: str
    sheet_index: int
    #: Upper-cased fragment of the block title in column B that precedes the header row.
    marker: str
    columns: tuple[TableColumn, ...]


TABLE_DEFS: tuple[TableDef, ...] = (
    TableDef(
        "C.t1",
        4,
        "TAMAMLANMIŞ LAYİHƏLƏR",
        (
            TableColumn("name", 1, "text"),
            TableColumn("client", 2, "text"),
            TableColumn("start", 3, "date"),
            TableColumn("end", 4, "date"),
            TableColumn("duration_months", 5, "number"),
            TableColumn("value", 6, "number"),
            TableColumn("project_type", 7, "text"),
        ),
    ),
    TableDef(
        "C.t2",
        4,
        "HAZIRDA DAVAM EDƏN",
        (
            TableColumn("name", 1, "text"),
            TableColumn("client", 2, "text"),
            TableColumn("start", 3, "date"),
            TableColumn("planned_end", 4, "date"),
            TableColumn("completion_pct", 5, "percent"),
            TableColumn("value", 6, "number"),
            TableColumn("stage", 7, "text"),
        ),
    ),
    TableDef(
        "G.t1",
        8,
        "MÜŞTƏRİ REFERANSLARI",
        (
            TableColumn("client", 1, "text"),
            TableColumn("project", 2, "text"),
            TableColumn("contact", 3, "text"),
        ),
    ),
)

#: Cover-sheet labels (column B, colon stripped) -> key in ``ParsedApplication.meta``.
COVER_LABELS: dict[str, str] = {
    "Layihənin Adı": "project_name",
    "Layihə Kodu / TQS Nömrəsi": "project_code",
    "Sifarişçi Şirkət": "client_name",
    "Əlaqə Şəxsi (Sifarişçidən)": "client_contact",
    "Əlaqə Telefon / E-poçt": "client_contact_phone",
    "Forma Göndərilmə Tarixi": "issued_on",
    "Formanın Son Təqdim Tarixi": "due_on",
    "İştirakçı Kodu": "participant_code",
}

#: Cover-sheet labels of the repeated vendor block -> key in ``ParsedApplication.vendor``.
COVER_VENDOR_LABELS: dict[str, str] = {
    "Şirkətin Tam Adı": "name",
    "VÖEN": "voen",
    "Qeydiyyat İli": "reg_year",
    "Ünvan": "address",
    "Əlaqə Şəxsi": "contact",
    "Vəzifə": "position",
    "Telefon": "phone",
    "E-poçt": "email",
}

#: Section-A codes that also describe the vendor itself -> key in ``ParsedApplication.vendor``.
VENDOR_FIELD_CODES: dict[str, str] = {
    "A.1": "name",
    "A.3": "voen",
    "A.4": "reg_year",
    "A.5": "address",
    "A.6": "contact",
    "A.7": "position",
    "A.8": "phone",
    "A.9": "email",
    "A.10": "website",
    "A.17": "legal_form",
}

#: Status wording in the checklist sheet -> the status the API stores.
DOCUMENT_STATUS_WORDS: dict[str, str] = {
    "hazır": "uploaded",
    "hazir": "uploaded",
    "hazırlanır": "in_preparation",
    "hazirlanir": "in_preparation",
    "aidiyyatsız": "not_applicable",
    "aidiyyatsiz": "not_applicable",
}

#: Row label that carries the checklist's own "N / M" completion count.
DOCUMENT_COMPLETION_LABEL = "TAMAMLANMA DƏRƏCƏSİ"


# --------------------------------------------------------------------------------------
# Scoring workbook layout
# --------------------------------------------------------------------------------------

WORKBOOK_PROFILE_SHEET_INDEX = 2
WORKBOOK_RAW_SHEET_INDEX = 3
WORKBOOK_POINTS_SHEET_INDEX = 4
WORKBOOK_SUMMARY_SHEET_INDEX = 5

#: First column that can hold a participant on the profile / summary sheets.
WORKBOOK_PROFILE_FIRST_COL = 3  # C
#: First column that can hold a participant on the answers / points sheets.
WORKBOOK_ANSWER_FIRST_COL = 5  # E

#: Profile-sheet row labels (column B) -> key on ``WorkbookVendor``.
WORKBOOK_PROFILE_LABELS: dict[str, str] = {
    "Şirkətin tam adı": "name",
    "VÖEN": "voen",
    "Qeydiyyat ili": "reg_year",
    "Ünvan": "address",
    "Əsas əlaqə şəxsi": "contact",
    "Vəzifə": "position",
    "Telefon / WhatsApp": "phone",
    "E-poçt": "email",
    "Veb sayt": "website",
    "Ümumi heyət sayı": "staff",
    "Mühəndis heyəti sayı": "engineers",
}

#: Row codes on the points sheet that hold the group totals, the grand total and the verdict.
WORKBOOK_GROUP_CODES: tuple[str, ...] = ("A", "B", "C", "D", "E", "F", "G")
WORKBOOK_TOTAL_CODE = "Σ"
WORKBOOK_KO_CODE = "KO"
WORKBOOK_DECISION_CODE = "✓"
