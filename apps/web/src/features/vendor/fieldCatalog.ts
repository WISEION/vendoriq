/**
 * The application field catalogue (spec Appendix A), ported verbatim from the approved
 * prototype's `FORM` object (`docs/design/prototype.html`) — same codes, same AZ/EN wording,
 * same section grouping. No endpoint publishes this: it is the form's own structure, not a
 * value any vendor observes, so it lives here as static content rather than being fetched.
 *
 * This is presentational metadata only — codes, questions, input kind, the evidencing
 * document code. No score, no threshold, no completeness rule is computed from it; that
 * stays server-side (`packages/scoring`, `services/answers.py`, `services/submission.py`).
 */

export type SectionKey = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G';

export type FieldKind = 'text' | 'number' | 'date' | 'yn' | 'calc' | 'table';

export interface FieldRow {
  kind: 'field';
  code: string;
  az: string;
  en: string;
  type: FieldKind;
  /** Document checklist code this answer is evidenced by, or `null` when none applies. */
  doc: string | null;
  mandatory?: true;
}

export interface HeaderRow {
  kind: 'header';
  az: string;
  en: string;
}

export type SectionRow = FieldRow | HeaderRow;

export interface FormSection {
  key: SectionKey;
  az: string;
  en: string;
  rows: SectionRow[];
}

function f(
  code: string,
  az: string,
  en: string,
  type: FieldKind,
  doc: string | null,
  mandatory?: true,
): FieldRow {
  return { kind: 'field', code, az, en, type, doc, mandatory };
}

function h(az: string, en: string): HeaderRow {
  return { kind: 'header', az, en };
}

export const FORM_SECTIONS: FormSection[] = [
  {
    key: 'A',
    az: 'A. Şirkət Profili',
    en: 'A. Company profile',
    rows: [
      f('A.1', 'Şirkətin tam rəsmi adı', 'Full legal name', 'text', 'A-01'),
      f('A.2', 'Ticarət reyestr nömrəsi', 'Trade register number', 'text', 'A-02'),
      f('A.3', 'VÖEN', 'Tax ID (VÖEN)', 'text', 'A-02'),
      f('A.4', 'Qeydiyyat ili', 'Year of registration', 'number', 'A-02'),
      f('A.5', 'Hüquqi ünvan (tam)', 'Legal address', 'text', 'A-03'),
      f('A.6', 'Əsas əlaqə şəxsi', 'Primary contact', 'text', null),
      f('A.7', 'Vəzifəsi', 'Position', 'text', null),
      f('A.8', 'Telefon / WhatsApp', 'Phone / WhatsApp', 'text', null),
      f('A.9', 'E-poçt', 'E-mail', 'text', null),
      f('A.10', 'Veb sayt', 'Website', 'text', null),
      h('HÜQUQİ SƏNƏDLƏR', 'LEGAL DOCUMENTS'),
      f(
        'A.11',
        'Tikinti lisenziyası mövcuddurmu? ⚠ MƏCBURİ',
        'Construction licence held? ⚠ MANDATORY',
        'yn',
        'A-04',
        true,
      ),
      f('A.12', 'Lisenziyanın nömrəsi', 'Licence number', 'text', 'A-04'),
      f('A.13', 'Verilmə tarixi', 'Issue date', 'date', 'A-04'),
      f('A.14', 'Etibarlılıq müddəti', 'Valid until', 'date', 'A-04'),
      f(
        'A.15',
        'Vergi borcsuzluğu arayışı (son 3 ay) ⚠ MƏCBURİ',
        'Tax clearance certificate (last 3 months) ⚠ MANDATORY',
        'yn',
        'A-05',
        true,
      ),
      f('A.16', 'Arayışın verilmə tarixi', 'Certificate date', 'date', 'A-05'),
      h('ŞİRKƏT STRUKTURU', 'COMPANY STRUCTURE'),
      f('A.17', 'Təsis forması', 'Legal form', 'text', 'A-03'),
      f('A.18', 'Təsisçilərin sayı', 'Number of founders', 'number', 'A-06'),
      f('A.19', 'Nizamnamə kapitalı (AZN)', 'Charter capital (AZN)', 'number', 'A-03'),
      f('A.20', 'IBAN', 'IBAN', 'text', 'A-07'),
    ],
  },
  {
    key: 'B',
    az: 'B. Maliyyə',
    en: 'B. Financial',
    rows: [
      h('İLLİK DÖVRİYYƏ (AZN)', 'ANNUAL TURNOVER (AZN)'),
      f('B.1', 'Son tam il üzrə dövriyyə', 'Turnover, last full year', 'number', 'B-01'),
      f('B.2', 'İkinci son il', 'Year −2', 'number', 'B-01'),
      f('B.3', 'Üçüncü son il', 'Year −3', 'number', 'B-01'),
      f('B.4', 'Son 3 ilin orta dövriyyəsi (avtomatik)', '3-year average (auto)', 'calc', null),
      h('KAPİTAL VƏ AKTİVLƏR', 'CAPITAL & ASSETS'),
      f('B.5', 'Öz kapitalı (Equity)', 'Equity', 'number', 'B-02'),
      f('B.6', 'Cari aktivlər', 'Current assets', 'number', 'B-02'),
      f('B.7', 'Cari öhdəliklər', 'Current liabilities', 'number', 'B-02'),
      f('B.8', 'Likvidlik əmsalı (avtomatik)', 'Current ratio (auto)', 'calc', null),
      h('BANK VƏ AUDİT', 'BANK & AUDIT'),
      f('B.9', 'Bank kredit xətti mövcuddurmu?', 'Bank credit line?', 'yn', 'B-03'),
      f('B.10', 'Kredit xəttinin məbləği', 'Credit line amount', 'number', 'B-03'),
      f('B.11', 'Bank adı', 'Bank', 'text', 'B-03'),
      f('B.12', 'Son 3 ildə audit olmuşdurmu?', 'Audited in last 3 years?', 'yn', 'B-04'),
      f('B.13', 'Audit şirkəti', 'Audit firm', 'text', 'B-04'),
    ],
  },
  {
    key: 'C',
    az: 'C. Texniki Təcrübə',
    en: 'C. Technical experience',
    rows: [
      h(
        'TAMAMLANMIŞ LAYİHƏLƏR (son 5 il) — cədvəl',
        'COMPLETED PROJECTS (last 5 years) — table',
      ),
      f(
        'C.t1',
        'Layihə cədvəli: ad, sifarişçi, başlama, bitmə, müddət, dəyər, tip',
        'Project table: name, client, start, end, duration, value, type',
        'table',
        'C-01',
      ),
      h('DAVAM EDƏN LAYİHƏLƏR', 'ONGOING PROJECTS'),
      f(
        'C.t2',
        'Layihə cədvəli: ad, sifarişçi, başlama, planlanan bitmə, %, dəyər',
        'Table: name, client, start, planned end, %, value',
        'table',
        null,
      ),
      h('KEYFİYYƏT SERTİFİKATI', 'QUALITY CERTIFICATE'),
      f('C.1', 'ISO 9001 mövcuddurmu?', 'ISO 9001 held?', 'yn', 'C-02'),
      f('C.2', 'Sertifikatın nömrəsi', 'Certificate number', 'text', 'C-02'),
      f('C.3', 'Etibarlılıq tarixi', 'Valid until', 'date', 'C-02'),
    ],
  },
  {
    key: 'D',
    az: 'D. Maddi-Texniki Baza',
    en: 'D. Facilities & equipment',
    rows: [
      h('OFİS VƏ EMALATXANA', 'OFFICE & WORKSHOP'),
      f('D.1', 'Baş ofisin ünvanı', 'Head office address', 'text', 'D-01'),
      f('D.2', 'Ofis sahəsi (m²)', 'Office area (m²)', 'number', 'D-01'),
      f('D.3', 'Mülkiyyət forması (öz/kira)', 'Ownership (own/rent)', 'text', 'D-01'),
      f('D.4', 'Emalatxana sahəsi (m²)', 'Workshop area (m²)', 'number', 'D-01'),
      f('D.5', 'Anbar sahəsi (m²)', 'Warehouse area (m²)', 'number', 'D-01'),
      h('AVADANLIQ VƏ ALƏTLƏR', 'EQUIPMENT & TOOLS'),
      f(
        'D.6',
        'İnşaat avadanlıqlarının ümumi sayı',
        'Total construction equipment',
        'number',
        'D-02',
      ),
      f('D.7', 'Kran / yük qaldırıcı', 'Cranes / hoists', 'number', 'D-02'),
      f('D.8', 'Beton qarışdırıcı və nasos', 'Concrete mixers & pumps', 'number', 'D-02'),
      f('D.9', 'Qaynaq və metal emal avadanlığı', 'Welding & metalwork equipment', 'number', 'D-02'),
      f('D.10', 'Elektrik alət dəstləri', 'Power tool sets', 'number', 'D-02'),
      h('NƏQLİYYAT PARKI', 'FLEET'),
      f('D.11', 'Yük maşınları', 'Trucks', 'number', 'D-03'),
      f('D.12', 'Mikroavtobus / minik', 'Vans / cars', 'number', 'D-03'),
      f('D.13', 'İxtisas texnikası (ekskavator, buldozer)', 'Heavy machinery', 'number', 'D-03'),
      f('D.14', 'Bütün nəqliyyat sığortalıdırmı?', 'All vehicles insured?', 'yn', 'D-03'),
    ],
  },
  {
    key: 'E',
    az: 'E. Kadr Resursları',
    en: 'E. Human resources',
    rows: [
      h('ÜMUMİ HEYƏT', 'HEADCOUNT'),
      f('E.1', 'Ümumi daimi heyət', 'Permanent staff', 'number', 'E-01'),
      f('E.2', 'Müvəqqəti / müqaviləli', 'Temporary / contract', 'number', 'E-01'),
      f('E.3', 'İnzibati heyət', 'Administrative staff', 'number', 'E-01'),
      h('TEXNİKİ HEYƏT', 'TECHNICAL STAFF'),
      f(
        'E.4',
        'Baş mühəndis / texniki direktor',
        'Chief engineer / technical director',
        'number',
        'E-02',
      ),
      f('E.5', 'Tikinti mühəndisləri', 'Civil engineers', 'number', 'E-02'),
      f('E.6', 'Memarlar', 'Architects', 'number', 'E-02'),
      f('E.7', 'Elektrik mühəndisləri', 'Electrical engineers', 'number', 'E-02'),
      f('E.8', 'MEP / HVAC mühəndisləri', 'MEP / HVAC engineers', 'number', 'E-02'),
      f('E.9', 'Texniklər (usta, texnik)', 'Technicians / foremen', 'number', 'E-02'),
      h('FƏHLƏ HEYƏTİ', 'WORKFORCE'),
      f('E.10', 'İxtisaslı fəhlələr', 'Skilled workers', 'number', 'E-01'),
      f('E.11', 'Köməkçi fəhlələr', 'Unskilled workers', 'number', 'E-01'),
      h('SƏTƏMM VƏ KEYFİYYƏT HEYƏTİ', 'HSE & QUALITY STAFF'),
      f(
        'E.12',
        'Tam ştatlı SƏTƏMM mütəxəssisi varmı?',
        'Full-time HSE specialist?',
        'yn',
        'E-03',
      ),
      f('E.13', 'SƏTƏMM ixtisas sertifikatı', 'HSE specialist certified?', 'yn', 'E-03'),
      f('E.14', 'Keyfiyyət nəzarət heyəti', 'QC staff', 'number', 'E-02'),
      h('SUBPODRATÇI BAZASI', 'SUBCONTRACTOR BASE'),
      f('E.15', 'Daimi subpodratçıların sayı', 'Regular subcontractors', 'number', 'E-04'),
      f('E.16', 'Müqavilələr rəsmiləşdirilibmi?', 'Contracts formalised?', 'yn', 'E-04'),
    ],
  },
  {
    key: 'F',
    az: 'F. SƏTƏMM və Keyfiyyət',
    en: 'F. HSE & quality',
    rows: [
      h('SƏTƏMM SİYASƏTİ', 'HSE POLICY'),
      f(
        'F.1',
        'SƏTƏMM siyasəti sənədi varmı? ⚠ MƏCBURİ',
        'HSE policy document? ⚠ MANDATORY',
        'yn',
        'F-01',
        true,
      ),
      f('F.2', 'SƏTƏMM planının tarixi', 'HSE plan date', 'date', 'F-01'),
      f('F.3', 'İşçilərə SƏTƏMM təlimi keçirilirmi?', 'HSE training delivered?', 'yn', 'F-02'),
      f('F.4', 'İl ərzində təlim saatları', 'Training hours / year', 'number', 'F-02'),
      h('ISO SERTİFİKATLARI', 'ISO CERTIFICATES'),
      f('F.5', 'ISO 14001 varmı?', 'ISO 14001?', 'yn', 'F-03'),
      f('F.6', 'Nömrə', 'Number', 'text', 'F-03'),
      f('F.7', 'Etibarlılıq', 'Valid until', 'date', 'F-03'),
      f('F.8', 'ISO 45001 varmı?', 'ISO 45001?', 'yn', 'F-04'),
      f('F.9', 'Nömrə', 'Number', 'text', 'F-04'),
      f('F.10', 'Etibarlılıq', 'Valid until', 'date', 'F-04'),
      h('BƏDBƏXT HADİSƏ STATİSTİKASI (son 3 il)', 'ACCIDENT STATISTICS (3 years)'),
      f('F.11', 'Ölümlə nəticələnən hadisə', 'Fatalities', 'number', 'F-05'),
      f('F.12', 'Ağır xəsarət', 'Serious injuries', 'number', 'F-05'),
      f('F.13', 'İş günü itkisi ilə hadisə', 'Lost-time incidents', 'number', 'F-05'),
      f('F.14', 'LTIR (son il)', 'LTIR (last year)', 'number', 'F-05'),
      h('ŞƏXSİ MÜHAFİZƏ VASİTƏLƏRİ', 'PPE'),
      f('F.15', 'Bütün işçilər FMV ilə təmin olunurmu?', 'All workers issued PPE?', 'yn', 'F-06'),
      f('F.16', 'FMV keyfiyyət sertifikatı', 'PPE quality certificate?', 'yn', 'F-06'),
    ],
  },
  {
    key: 'G',
    az: 'G. Sığorta və Referanslar',
    en: 'G. Insurance & references',
    rows: [
      h('MƏSULİYYƏT SIĞORTASI', 'LIABILITY INSURANCE'),
      f('G.1', 'Peşəkar məsuliyyət sığortası varmı?', 'Professional liability insurance?', 'yn', 'G-01'),
      f('G.2', 'Sığorta şirkəti', 'Insurer', 'text', 'G-01'),
      f('G.3', 'Polis nömrəsi', 'Policy number', 'text', 'G-01'),
      f('G.4', 'Sığorta məbləği (AZN)', 'Cover limit (AZN)', 'number', 'G-01'),
      f('G.5', 'Etibarlılıq tarixi', 'Valid until', 'date', 'G-01'),
      f('G.6', 'Ümumi məsuliyyət sığortası varmı?', 'General liability insurance?', 'yn', 'G-01'),
      f('G.7', 'Sığorta məbləği (AZN)', 'Cover limit (AZN)', 'number', 'G-01'),
      h('MÜŞTƏRİ REFERANSLARI (minimum 3)', 'CLIENT REFERENCES (minimum 3)'),
      f(
        'G.t1',
        'Referans cədvəli: müştəri, layihə, əlaqə şəxsi, məktub',
        'Reference table: client, project, contact, letter',
        'table',
        'G-02',
      ),
    ],
  },
];

export const FORM_SECTION_KEYS: SectionKey[] = FORM_SECTIONS.map((section) => section.key);

export function sectionByKey(key: string): FormSection | undefined {
  return FORM_SECTIONS.find((section) => section.key === key);
}

/** The three knock-out questions (spec Appendix A) — the field codes, not the criteria codes. */
export const KO_FIELD_CODES: readonly string[] = ['A.11', 'A.15', 'F.1'];

/** Table field codes and the columns their rows carry (spec Appendix A). Keys match what
 * `packages/scoring.derive_raw` reads off a table row (`value` for the contract amount). */
export const TABLE_COLUMNS: Record<
  string,
  { key: string; az: string; en: string; type: 'text' | 'number' | 'date' }[]
> = {
  'C.t1': [
    { key: 'name', az: 'Layihənin adı', en: 'Project name', type: 'text' },
    { key: 'client', az: 'Sifarişçi', en: 'Client', type: 'text' },
    { key: 'start', az: 'Başlama', en: 'Start', type: 'date' },
    { key: 'end', az: 'Bitmə', en: 'End', type: 'date' },
    { key: 'duration', az: 'Müddət (ay)', en: 'Duration (months)', type: 'number' },
    { key: 'value', az: 'Dəyər (AZN)', en: 'Value (AZN)', type: 'number' },
    { key: 'project_type', az: 'Tip', en: 'Type', type: 'text' },
  ],
  'C.t2': [
    { key: 'name', az: 'Layihənin adı', en: 'Project name', type: 'text' },
    { key: 'client', az: 'Sifarişçi', en: 'Client', type: 'text' },
    { key: 'start', az: 'Başlama', en: 'Start', type: 'date' },
    { key: 'planned_end', az: 'Planlanan bitmə', en: 'Planned end', type: 'date' },
    { key: 'percent', az: 'Tamamlanma (%)', en: 'Completion (%)', type: 'number' },
    { key: 'value', az: 'Dəyər (AZN)', en: 'Value (AZN)', type: 'number' },
  ],
  'G.t1': [
    { key: 'client', az: 'Müştəri', en: 'Client', type: 'text' },
    { key: 'project', az: 'Layihə', en: 'Project', type: 'text' },
    { key: 'contact', az: 'Əlaqə şəxsi', en: 'Contact', type: 'text' },
    { key: 'letter', az: 'Referans məktubu', en: 'Reference letter', type: 'text' },
  ],
};
