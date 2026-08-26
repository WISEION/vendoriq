**VendorIQ**

Vendor Management & Market Intelligence System

System design specification · Version 1.0 · 24 August 2026

Prepared for: Gasimov, Zion Noiz — procurement & tendering (Uni Ko QSC
context)

Basis: Prekvalifikasiya Müraciət Forması (11-sheet vendor application),
Prekvalifikasiya TQS2026006 Rev1 and Rev4 scoring workbooks, WESA
completed application.

Companion: Clickable prototype (VendorIQ) — vendor portal and manager
dashboard seeded with the 13 TQS2026006 vendors.

**Contents**

1\. Purpose and objectives

2\. Current state and what the design keeps

3\. Scope, users and roles

4\. System overview

5\. Data model

6\. Data acquisition and integrations

7\. Vendor portal

8\. Manager dashboard

9\. Qualification workflow

10\. Scoring engine

11\. Project matching and go / no-go

12\. Market intelligence

13\. Non-functional requirements

14\. Technology stack recommendation

15\. Delivery roadmap

16\. Assumptions and open decisions

Appendix A — Application field catalogue

Appendix B — Document checklist

Appendix C — Vendors loaded in the prototype

**1. Purpose and objectives**

The system replaces the per-tender Excel prequalification cycle with a
permanent, queryable vendor base. Its job is to answer, at the moment a
tender or project opportunity appears, whether the market can supply the
work packages and materials the project needs, from whom, at what class
of reliability, and with what gaps. That answer feeds the go / no-go
decision.

Three capabilities were requested and are covered here:

1.  **Data acquisition.** Vendor data enters through several channels —
    the vendor's ERP via API, the existing Excel application form, a web
    form in the vendor portal, and manual entry — and lands in one
    vendor record with the source and date of every field recorded.

2.  **Vendor portal.** Registered and prequalified vendors maintain
    their own profile, complete applications, upload documents, see
    their status and score, and are reminded when documents expire.

3.  **Manager dashboard.** Procurement staff review applications, enter
    rubric scores against evidence, approve or reject, run project
    matching, and read the market picture: coverage by category,
    capacity, certification penetration, gaps and data freshness.

The intended outcome is market intelligence: an accurate, current view
of all vendor types — subcontractors and material suppliers — that can
be matched against upcoming projects.

**2. Current state and what the design keeps**

The Excel process already contains the essential design decisions and
the system is built on them rather than around them.

- **Application form.** Eleven sheets: cover page, instructions,
  sections A–G (company profile, financial, technical experience,
  facilities, human resources, HSE & quality, insurance & references), a
  38-item document checklist with codes A-01 … H-02, and a signed
  declaration. The field catalogue (A.1 … G.7 plus three tables) becomes
  the portal form and the Excel import mapping unchanged.

- **Scoring workbook Rev4.** Seven categories totalling 100 points, 24
  criteria, three knock-out criteria (A.1 construction licence, A.4 tax
  clearance, F.1 HSE policy), 0–3 rubric cells for document-verified
  criteria and threshold tables for numeric ones, a 70-point pass mark
  and A–F classes. The formulas were ported one-to-one into the scoring
  engine and verified against all 13 vendors in the Rev4 sheet (13 of 13
  totals and decisions match).

- **Committee workflow.** Raw answers are transcribed from each form,
  documents are checked, rubric scores entered, a summary sheet is
  signed by the commission chair and approved by management. The system
  keeps the same roles and decision points, but the transcription step
  disappears.

Observed limitations the design addresses: vendors re-submit the same
data for each TQS; scores live in a per-tender file and never accumulate
into a vendor history; document expiry (notably A-05 tax clearance,
valid three months) is not tracked; category coverage — who can do what
— is not recorded at all, so matching against a project is a manual
memory exercise; and there is no supplier model, only the subcontractor
one.

**3. Scope, users and roles**

| **Role**            | **Who**                                       | **What they do**                                                                                                                                  |
|---------------------|-----------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| Vendor user         | Contact person at a subcontractor or supplier | Registers, maintains the company profile and categories, completes applications, uploads documents, signs the declaration, sees status and score. |
| Procurement officer | Commercial department staff                   | Invites vendors, imports Excel forms, verifies documents, enters 0–3 rubric scores, requests missing information, prepares the evaluation.        |
| Commission member   | Tender commission                             | Reviews evaluations, records the committee decision and justification.                                                                            |
| Manager / approver  | Head of commercial / management               | Approves prequalification, sets scoring model versions and thresholds, reads market intelligence, makes go / no-go calls.                         |
| Administrator       | IT / system owner                             | Manages users, integrations, category taxonomy, scoring model versions, audit log.                                                                |

In scope for phase 1: subcontractors and material suppliers, the Rev4
subcontractor model, a supplier model, Excel and portal ingestion,
project matching and the market views. Out of scope for phase 1:
e-tendering (bid submission and price comparison), contract management
and invoicing. These are natural phase-3 extensions because the vendor
base and project packages already exist.

**4. System overview**

The system is a conventional three-tier web application with an
integration layer in front of it. Every component is replaceable; the
parts that carry the business logic are the scoring engine, the matching
engine and the data model.

| **Component**           | **Responsibility**                                                       | **Recommended technology**                                                                      |
|-------------------------|--------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|
| Vendor portal (web)     | Bilingual AZ/EN self-service for vendors                                 | React (or Vue) single-page app; served from the same backend                                    |
| Manager dashboard (web) | Review, scoring, matching, intelligence views                            | Same front-end codebase, role-gated routes                                                      |
| API backend             | Business rules, scoring, matching, workflow states, audit                | Python FastAPI or Node NestJS; REST + JSON; OpenAPI documented                                  |
| Database                | Vendors, applications, scores, projects, documents metadata              | PostgreSQL (JSONB for form answers keyed by field code)                                         |
| Document store          | Uploaded PDFs, Excel originals                                           | S3-compatible object storage (MinIO on-premise or cloud)                                        |
| Integration layer       | Excel parser, ERP connectors, registry checks, e-mail intake, scheduling | n8n workflows (already available) calling backend endpoints; Python parsers for Excel           |
| Authentication          | Vendor accounts and staff accounts                                       | Vendors: e-mail + one-time code; staff: SSO (Microsoft 365 / Google) or local accounts with 2FA |
| Notifications           | Expiry reminders, status changes, invitations                            | E-mail (SMTP) and optional WhatsApp Business API, both via n8n                                  |

Data flows in one direction into the vendor record: Excel import, portal
form and ERP adapters all write "field observations" (field code, value,
source, timestamp, confidence). The current value of a field is the most
recent observation from the highest-trust source, and the history is
retained. This is what makes "accurate and current" measurable: the
dashboard can show data freshness per vendor and per field.

**5. Data model**

The entities below are the minimum set. Field-level detail for the
application form is in Appendix A; the document checklist in Appendix B.

| **Entity**          | **Key attributes**                                                                                                                                                                                                                         | **Notes**                                                                                                                                                                                                                                |
|---------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Vendor              | id, legal name, VÖEN (unique), type (subcontractor / supplier / both), legal form, registration year, address, region, website, status, categories\[\], data source summary, last updated                                                  | One record per legal entity regardless of how many tenders it took part in. Status: registered → invited → in progress → submitted → under review → prequalified (class) / rejected / suspended.                                         |
| Contact             | vendor id, name, position, phone, e-mail, is primary, portal login                                                                                                                                                                         | Several contacts per vendor; one is the portal account owner.                                                                                                                                                                            |
| Category            | code, name AZ/EN, kind (work package / material group), parent                                                                                                                                                                             | Two taxonomies: work packages (façade, steel, concrete, MEP, electrical, finishing, flooring, general …) and material groups (ready-mix, rebar, glass & aluminium, electrical, finishing materials …). Vendor selects, manager confirms. |
| Field observation   | vendor id, field code (A.1 … G.7, tables as JSON), value, unit, source (excel / portal / api / registry / manual), source reference (file, API call id), observed at, entered by                                                           | Append-only. Current profile is derived from it.                                                                                                                                                                                         |
| Qualification cycle | id, name (e.g. TQS2026006, 2026 periodic), scoring model version, open / close dates, committee                                                                                                                                            | Groups applications. Periodic re-qualification is just another cycle.                                                                                                                                                                    |
| Application         | vendor id, cycle id, status, submitted at, declaration (signatory, date, stamp file), raw indicators snapshot, rubric scores, per-criterion points, group totals, total, KO result, class, decision, justification, decided by, decided at | The snapshot freezes the raw indicators at submission so later profile changes do not alter a historic score.                                                                                                                            |
| Document            | vendor id, code (A-01 … H-02), file, issue date, expiry date, verified by, verified at, status                                                                                                                                             | Expiry drives reminders; A-05 always expires three months after issue.                                                                                                                                                                   |
| Scoring model       | version, vendor type, criteria\[\] (code, group, max points, rule type, thresholds, KO flag), class bands, pass mark                                                                                                                       | Rev4 is version "sub-4"; supplier model is "sup-1". Applications reference the version they were scored with.                                                                                                                            |
| Project             | code (TQS), name, client, stage (pipeline / go-no-go / tender / execution), estimated value, deadline                                                                                                                                      | The demand side.                                                                                                                                                                                                                         |
| Work package        | project id, category, estimated value, minimum class, required certificates, notes                                                                                                                                                         | Each package is matched independently.                                                                                                                                                                                                   |
| Performance record  | vendor id, project id, on-time %, quality NCR count, HSE incidents, payment disputes, rating, period                                                                                                                                       | Post-award data; feeds re-qualification (planned phase 2).                                                                                                                                                                               |
| Audit event         | actor, entity, action, before / after, timestamp                                                                                                                                                                                           | Every status change, score edit and decision.                                                                                                                                                                                            |

**6. Data acquisition and integrations**

The requirement is to acquire vendor data "through different sources —
API, Excel, form and so on". The design treats each source as an adapter
that produces field observations; the vendor record does not care where
a value came from, but always knows.

**6.1 Excel application form import**

The existing 11-sheet form is parsed sheet by sheet. Each answer cell is
addressed by its code (column B) rather than by position, so the parser
survives row insertions. Tables (completed projects, ongoing projects,
references) become JSON arrays. The document checklist sheet is read for
status per code. The parser computes the derived raw indicators used by
scoring — 3-year average turnover (B.1), largest project value (C.2),
completed and ongoing project counts (C.1, C.3) — and flags anomalies
for the officer: a certificate date older than three months (as in the
WESA file, where A.16 is 2020-09-28), percentages entered as both 0.95
and "85%", and mandatory cells left empty. Intake can be automated by an
n8n workflow watching the tender mailbox for .xlsx attachments.

**6.2 Vendor portal form**

The same field catalogue rendered as a bilingual web form with
validation (VÖEN ten digits, dates, numeric ranges, Yes/No selects),
autosave, a completion meter, document upload against each code and a
pre-submission check that mandatory fields, mandatory documents and the
three knock-out answers are present. Profile data (A.1–A.10, categories)
is stored once and reused across cycles.

**6.3 ERP API connectors**

For vendors willing to connect, a connector pulls the fields that change
often — annual turnover, headcount, engineer count, list of completed
and ongoing projects with values, fleet and equipment registers.
Connectors are per ERP family: 1C (OData / HTTP services, the most
common in the Azerbaijani market), SAP (OData), Odoo (XML-RPC /
JSON-RPC) and a generic REST/CSV contract published by the system for
any other ERP. Pulls run on a schedule (monthly is enough for financial
data; weekly for project lists) and write observations with source
"api". API data does not replace document verification: rubric criteria
still require the PDF evidence, but numeric raw indicators refresh
automatically and the dashboard shows when a vendor's self-reported
number diverges from the API value.

**6.4 Government registries and third-party checks**

Planned adapters: tax clearance status and VÖEN validity (State Tax
Service e-services), construction licence register, and court / debt
registers where accessible. These convert the two most sensitive
knock-out criteria from "vendor says" into "verified", and they can run
on a schedule so a prequalified vendor that falls into tax debt is
flagged before the next tender.

**6.5 Manual entry and project performance**

Officers can enter or correct any field with a mandatory reason; the
observation is marked "manual". After contract award, site and QA teams
record performance (on-time delivery, quality non-conformances, HSE
incidents). Performance is not part of Rev4 but is stored from phase 1
so that a re-qualification model can use it later.

**6.6 Field provenance and freshness**

| **Source**        | **Trust rank** | **Typical fields**                                   | **Refresh**                     |
|-------------------|----------------|------------------------------------------------------|---------------------------------|
| Registry check    | 1 (highest)    | A.4 tax clearance, A.1 licence validity              | Weekly, automated               |
| ERP API           | 2              | B.1–B.7 financials, E.1–E.11 headcount, C tables     | Monthly / weekly                |
| Verified document | 3              | Any criterion with a PDF, after officer verification | Per application                 |
| Portal form       | 4              | Everything the vendor enters                         | Per application; profile yearly |
| Excel import      | 4              | Everything in the form                               | Per application                 |
| Manual            | 5              | Corrections                                          | Ad hoc, with reason             |

A field is "stale" when its most recent observation is older than its
refresh expectation (financials 15 months, headcount 12 months,
documents by expiry date). The market intelligence view counts stale
profiles so that the intelligence is honest about its own accuracy.

**7. Vendor portal**

Five screens, in Azerbaijani by default with an English toggle. The
prototype implements each of them.

| **Screen**           | **Content**                                                                                                                                                                                            | **Rules**                                                                                                                                                                        |
|----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Status               | Stepper (registered → invited → filling → submitted → under review → decision), result with score and class once released, validity date, next steps (expiring documents, annual profile confirmation) | Score breakdown is released only after the commission decision; KO failures show which criterion failed.                                                                         |
| Company profile      | A.1–A.10 identity and contacts, legal form, categories (work packages / material groups), bank details                                                                                                 | Stored once; edits after prequalification create a change request the officer confirms.                                                                                          |
| Application form     | Sections A–G as tabs; each row shows code, question, format, answer cell, required document code; project and reference tables; computed fields (B.4 average turnover, B.8 current ratio)              | Mandatory rows marked; completion meter; autosave; a table row requires at least three completed projects and three references as the Excel form does.                           |
| Documents            | 38-item checklist with mandatory flag, status (uploaded / in preparation / not applicable / missing), file, expiry date                                                                                | PDF only; A-05 expiry auto-set to issue date + 3 months; expiring documents trigger reminders at 30 and 7 days.                                                                  |
| Declaration & submit | Declaration text, signatory name and position, agreement checkbox, pre-submission check list, submit                                                                                                   | Submit is enabled only when mandatory fields, mandatory documents and the three KO answers are complete. Submission freezes the raw-indicator snapshot and notifies the officer. |

**8. Manager dashboard**

| **Screen**                | **Content**                                                                                                                                                                                                                                                                                                                                                                                           |
|---------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Overview                  | KPI tiles (vendors in register, prequalified, awaiting review, documents expiring in 60 days); coverage by category with A/B share; class distribution; attention list (expiring documents, pending reviews, incomplete applications, category gaps); recent activity feed from all adapters.                                                                                                         |
| Vendor register           | Filterable table: type, category, class, status, search by name / VÖEN; columns for score, class, status, turnover, staff, source, last update. Vendor detail: profile, scorecard with per-criterion raw value and points, project history, document list with expiry state, evaluation history across cycles.                                                                                        |
| Applications & evaluation | Queue by cycle and status. Evaluation screen: every criterion with its raw indicator (pre-filled from the form or API), the evidence document code, an editable 0–3 rubric cell for rubric criteria, live per-criterion points, group totals, total, KO check and class; actions approve / request information / reject with justification. Approve is disabled below the pass mark or on KO failure. |
| Projects & matching       | Project list with value, package count, coverage % and go / no-go pill. Project detail: each work package with minimum class and required certificates, ranked candidate vendors with score, class, largest project, capacity fit and eligibility reason; recommendation text.                                                                                                                        |
| Market intelligence       | Category × class matrix; aggregate capacity per category (sum of turnover, engineers, vendor count); certification and insurance penetration among prequalified subcontractors; data source split and stale-profile count; expiring documents list; market gaps (categories with no prequalified vendor).                                                                                             |
| Scoring models            | Read-only view of each model version: criteria, max points, rule, KO flag, class bands. Editing creates a new version; older applications keep theirs.                                                                                                                                                                                                                                                |
| Data sources              | Adapter list with status, record count and last sync; Excel import with a mapping preview and anomaly warnings; ERP connector configuration per vendor.                                                                                                                                                                                                                                               |

**9. Qualification workflow**

Application states and who moves them:

| **State**                | **Entered by**                                         | **Exit**                                                          |
|--------------------------|--------------------------------------------------------|-------------------------------------------------------------------|
| Registered               | Vendor self-registration or officer import             | Officer invites to a cycle                                        |
| Invited                  | Officer / bulk invitation for a TQS                    | Vendor opens the application                                      |
| In progress              | Vendor                                                 | Vendor submits; or officer marks incomplete after deadline        |
| Submitted                | Vendor (declaration signed) or Excel import            | Officer starts review                                             |
| Under review             | Officer                                                | Officer completes rubric; commission records decision             |
| Information requested    | Officer                                                | Vendor supplies missing data → back to under review               |
| Prequalified (A / B / C) | Manager approval                                       | Valid 12 months; expiry or KO registry failure → re-qualification |
| Rejected (D / F / KO)    | Commission decision                                    | Vendor may re-apply in the next cycle                             |
| Suspended                | Manager, with reason (performance, tax debt, incident) | Manager lifts                                                     |

Prequalification is valid for twelve months by default. Re-qualification
reuses the stored profile, so the vendor only confirms or updates
changed fields and replaces expired documents.

**10. Scoring engine**

The engine is a pure function: given a scoring model version and a set
of raw indicators it returns per-criterion points, group totals, total,
knock-out result and class. Two rule types exist. Rubric criteria take a
0–3 officer score and yield score ÷ 3 × max points, rounded to one
decimal. Numeric criteria use threshold tables (turnover, equity,
project counts and values, headcount, references) or bands (years in
operation, ongoing projects). Knock-out criteria reject the application
when their raw value is 0 regardless of the total.

**10.1 Subcontractor model — Rev4 (version sub-4)**

| **Group** | **Category**                   | **Points** | **Criteria (max points)**                                                                                                   |
|-----------|--------------------------------|------------|-----------------------------------------------------------------------------------------------------------------------------|
| A         | Company profile & legal status | 15         | A.1 Construction licence (5, KO) · A.2 Years in operation (3) · A.3 Legal structure (2) · A.4 Tax clearance (5, KO)         |
| B         | Financial standing             | 20         | B.1 Avg. 3-year turnover (8) · B.2 Equity (5) · B.3 Bank credit line (3) · B.4 Audited statements (4)                       |
| C         | Technical experience           | 25         | C.1 Similar projects in 5 years (9) · C.2 Largest completed project value (7) · C.3 Ongoing projects (4) · C.4 ISO 9001 (5) |
| D         | Facilities & equipment         | 10         | D.1 Office & workshop (3) · D.2 Equipment & tools (4) · D.3 Fleet (3)                                                       |
| E         | Human resources                | 15         | E.1 Permanent staff (4) · E.2 Engineers (4) · E.3 HSE specialist (3) · E.4 Subcontractor base (4)                           |
| F         | HSE & quality                  | 10         | F.1 HSE policy & plan (4, KO) · F.2 ISO 14001/45001 (3) · F.3 Accident record (3)                                           |
| G         | Insurance & references         | 5          | G.1 Liability insurance (3) · G.2 References (2)                                                                            |

Threshold tables reproduced from the workbook: B.1 turnover \< 0.5M → 0,
\< 1M → 25 %, \< 5M → 50 %, \< 10M → 75 %, else 100 %; B.2 equity \<
0.5M → 0, \< 1M → 30 %, \< 2.5M → 60 %, else 100 %; C.1 projects \< 2 →
0, ≤ 4 → 30 %, ≤ 9 → 70 %, else 100 %; C.2 largest project \< 1M → 0, \<
3M → 40 %, \< 7M → 75 %, else 100 %; C.3 ongoing 0 → 25 %, ≤ 3 → 50 %, ≤
6 → 100 %, \> 6 → 75 %; E.1 staff \< 20 → 0, \< 50 → 40 %, \< 100 → 75
%, else 100 %; E.2 engineers \< 3 → 0, ≤ 7 → 40 %, ≤ 15 → 75 %, else 100
%; G.2 references 0 → 0, ≤ 2 → 40 %, ≤ 5 → 70 %, else 100 %; A.2 years 0
→ 0, ≤ 3 → 1, ≤ 7 → 2, else 3. Classes: A 90–100 (invite, first
priority), B 80–89 (invite), C 70–79 (conditional invite), D 60–69 (not
invited), F below 60 (reject), KO (automatic reject).

**Verification.** The ported engine was run against the Rev4 workbook
for all 13 vendors: Shield 94.7 A, Wesa 90.3 A, Arti Qrup 84.0 B,
İNPROCON 83.5 B, Hasan Holding 76.2 C, Gilan 73.0 C, İbrahimovs 39.1 F,
Ranuni 38.3 KO, Ray Group 32.3 KO, and the four vendors without data at
KO. All totals and decisions match.

**10.2 Supplier model — v1 proposal (version sup-1)**

Material suppliers are judged on what a contractor actually needs from
them: the right products, in stock or producible, delivered on time, at
a competitive price, with documents that pass site QA. The proposed
model keeps the same 100-point frame and rubric mechanics so officers
work the same way, but re-weights the groups.

| **Group** | **Category**                   | **Points** | **Criteria (max points)**                                                                                                                                                                 |
|-----------|--------------------------------|------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| A         | Company profile & legal status | 15         | A.1 Registration / trade permit (5, KO) · A.2 Years (3) · A.3 Legal structure (2) · A.4 Tax clearance (5, KO)                                                                             |
| B         | Financial standing             | 15         | B.1 Avg. turnover (6) · B.2 Equity (4) · B.3 Credit line (2) · B.4 Audited statements (3)                                                                                                 |
| C         | Product & technical capability | 25         | C.1 Product range coverage (7) · C.2 Production / stock capacity (7) · C.3 Manufacturer authorisation or origin documents (5, KO) · C.4 Product certificates — CE, GOST, test reports (6) |
| D         | Logistics & delivery           | 15         | D.1 Local warehouse / stock (5) · D.2 Own transport (4) · D.3 Average lead time in days (6)                                                                                               |
| E         | Commercial terms               | 15         | E.1 Price competitiveness vs. benchmark (6) · E.2 Payment terms / credit (5) · E.3 Warranty (4)                                                                                           |
| F         | Quality & HSE                  | 10         | F.1 ISO 9001 (4) · F.2 Defect / return record (3) · F.3 Site-delivery HSE compliance (3)                                                                                                  |
| G         | References                     | 5          | G.1 Client references (3) · G.2 Delivery track record (2)                                                                                                                                 |

Lead time (D.3) is scored inversely: ≤ 3 days 100 %, ≤ 7 days 75 %, ≤ 14
days 50 %, ≤ 30 days 25 %, longer 0. Price competitiveness (E.1) is a
rubric today; once quotations are captured per material group it becomes
a computed criterion (vendor price vs. median of the last six months of
quotes). The three knock-outs are registration, tax clearance and
manufacturer authorisation or proof of origin — counterfeit or
grey-import material is the supplier-side equivalent of an unlicensed
subcontractor. The weights are a starting point for the commission to
adjust; the model is versioned so adjustments do not disturb
already-scored applications.

**10.3 Model governance**

- Every model version is immutable once an application has been scored
  with it.

- Changing a weight, threshold or KO flag creates a new version with an
  effective date and a note.

- The evaluation screen shows the version used; the vendor sees the
  class bands but not other vendors' scores.

- An optional second-evaluator mode records two rubric sets and flags
  criteria where they differ by more than one point.

**11. Project matching and go / no-go**

A project is described as a set of work packages and material packages,
each with a category, estimated value, minimum acceptable class and
required certificates. Matching runs per package and aggregates to the
project.

**11.1 Package rules**

1.  Candidates are vendors whose confirmed categories include the
    package category.

2.  A candidate is eligible when it is currently prequalified, passed
    knock-out, has class at or above the package minimum, and holds the
    required certificates (ISO 9001 for quality-critical packages, ISO
    45001 for high-risk site work).

3.  Capacity fit: the vendor's largest completed project is at least 40
    % of the package value (for suppliers: one quarter of annual
    turnover). This stops a class-A finishing contractor with a 0.5M
    track record being treated as a fit for a 4.5M package.

4.  Package state: GO when at least two class A or B vendors with
    capacity fit are eligible; CONDITIONAL when at least one eligible
    vendor exists; NO-GO when none.

**11.2 Project rules**

Project GO when every package is GO; NO-GO when any package is NO-GO;
otherwise CONDITIONAL. Coverage is the value share of packages that are
not NO-GO. The screen shows the recommendation and, for each weak
package, the specific gap (no vendor in category, only class C,
certificate missing, capacity too small) so the sourcing action is
obvious. On the TQS-238 sample in the prototype the flooring package has
no prequalified vendor, which makes the project NO-GO at 96 % coverage —
a realistic result that tells the manager exactly what to fix before
bidding.

The thresholds (two strong vendors, 40 % capacity ratio, minimum class
per package) are parameters, not code, and are set per project or per
organisation default.

**12. Market intelligence**

The intelligence views are derived from the same records, so they are as
current as the last adapter run and as honest as the freshness counter
beside them.

- **Coverage matrix.** Category × class counts of scored vendors; empty
  rows are market gaps to source before the next tender.

- **Capacity.** Per category: number of prequalified vendors, combined
  turnover, engineers, ongoing-project load. Ongoing load is the early
  warning that the good vendors are busy.

- **Certification and insurance penetration.** Share of prequalified
  subcontractors with ISO 9001, 14001 / 45001, liability insurance,
  audited statements and a full-time HSE specialist — useful both for
  tender conditions and for telling vendors what the market expects.

- **Expiry and freshness.** Documents expiring in 60 days; profiles
  older than 90 days; vendors whose API values diverge from
  self-reported values.

- **Price intelligence (phase 2).** Once supplier quotations are
  captured per material group, median and range per group over time, and
  each supplier's position relative to it.

- **Trend.** Scores per vendor across cycles; category coverage over
  time; share of applications rejected on KO.

**13. Non-functional requirements**

| **Area**     | **Requirement**                                                                                                                                                                                                               |
|--------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Language     | Azerbaijani and English for all user-facing text, switchable per user; field catalogue and category names bilingual; documents in whatever language the vendor provides.                                                      |
| Security     | TLS everywhere; vendors see only their own data; staff roles enforced server-side; documents served through signed, expiring links; personal data of contacts handled under Azerbaijani personal-data law; encrypted backups. |
| Audit        | Immutable log of every status change, score edit, decision and integration write; exportable for committee minutes.                                                                                                           |
| Availability | Business-hours SLA is sufficient; nightly backups with 30-day retention; restore tested quarterly.                                                                                                                            |
| Performance  | Register and matching queries under one second at 1,000 vendors and 100 projects; Excel import under 30 seconds per file.                                                                                                     |
| Hosting      | On-premise VM or Azerbaijani cloud region if data residency is required; otherwise any cloud. Containerised (Docker) so the choice can change.                                                                                |
| Export       | Every table exportable to Excel; the evaluation summary exportable as the current commission summary sheet layout for signature.                                                                                              |

**14. Technology stack recommendation**

A custom web application was chosen in the briefing. Within that, the
recommendation is: PostgreSQL for the database; a Python FastAPI backend
(Python also hosts the Excel parser with openpyxl and the scoring
engine, so one language covers the logic); a React front-end with a
component library that supports right-to-left-free bilingual text and
dense tables; MinIO or cloud object storage for documents; n8n for
scheduled pulls, mailbox intake and notifications, calling the backend's
documented API; and Docker Compose for deployment on a single server
initially. The prototype's scoring and matching functions are written in
plain JavaScript and can be transliterated to Python line for line, or
kept in a shared TypeScript package if a Node backend is preferred.

**15. Delivery roadmap**

| **Phase**                     | **Duration**                     | **Delivers**                                                                                                                                                                                                        |
|-------------------------------|----------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 0 — Foundation                | 3–4 weeks                        | Data model, authentication, category taxonomy, scoring engine (sub-4 and sup-1) with the Rev4 verification suite, audit log.                                                                                        |
| 1 — Replace the Excel cycle   | 5–6 weeks                        | Excel importer with anomaly report, vendor register, application review and evaluation screens, decision workflow, exportable commission summary. Load the TQS2026006 vendors. First real cycle runs in the system. |
| 2 — Vendor portal             | 4–5 weeks                        | Bilingual portal: profile, application form, document upload with expiry, declaration and submit, reminders. Vendors stop sending Excel.                                                                            |
| 3 — Matching and intelligence | 4 weeks                          | Projects and packages, matching engine with configurable thresholds, go / no-go screen, market views, freshness metrics.                                                                                            |
| 4 — Integrations              | ongoing, 2–3 weeks per connector | ERP connectors starting with the ERP most vendors use (survey first), registry checks, performance records, quotation capture for price intelligence.                                                               |

Phases 1 and 2 can be built in parallel by two developers; the whole
programme is roughly four to five months to phase 3 with a small team,
and the Excel process continues to work throughout because the importer
accepts the current form unchanged.

**16. Assumptions and open decisions**

- **Vendor ERPs.** Which ERP systems the vendor base runs is unknown;
  the design assumes a mix dominated by 1C and spreadsheets. Recommend a
  short survey of the prequalified vendors before building the first
  connector.

- **Category taxonomy.** The 15 categories in the prototype are a
  starting list; the assignments to the 13 vendors are illustrative and
  must be confirmed by the vendors or the officer.

- **Supplier model weights.** Proposed, not validated. Suggest the
  commission scores three known suppliers with it and adjusts before
  version sup-1 is frozen.

- **Currency.** The Rev4 sheet labels turnover as USD in the methodology
  but the raw data and thresholds are AZN; the system stores AZN and the
  labels should be corrected in the model description.

- **Matching thresholds.** Two strong vendors and the 40 % capacity
  ratio are defaults for discussion.

- **Validity period.** Twelve-month prequalification validity is
  assumed; a shorter period for class C is an option.

- **Organisation.** The prototype is branded for Uni Ko QSC's commercial
  department because the forms are; the product name VendorIQ is a
  placeholder.

**Appendix A — Application field catalogue**

Codes, questions and required document per section, as carried from the
Excel form into the portal and the importer. Types: text, number, date,
Y/N, table, calc (computed).

**A. Company profile / A. Şirkət Profili**

| **Code** | **Question (EN)**                                     | **Sual (AZ)**                                  | **Type** | **Doc**   |
|----------|-------------------------------------------------------|------------------------------------------------|----------|-----------|
| A.1      | Full legal name                                       | Şirkətin tam rəsmi adı                         | text     | A-01      |
| A.2      | Trade register number                                 | Ticarət reyestr nömrəsi                        | text     | A-02      |
| A.3      | Tax ID (VÖEN)                                         | VÖEN                                           | text     | A-02      |
| A.4      | Year of registration                                  | Qeydiyyat ili                                  | number   | A-02      |
| A.5      | Legal address                                         | Hüquqi ünvan (tam)                             | text     | A-03      |
| A.6      | Primary contact                                       | Əsas əlaqə şəxsi                               | text     | —         |
| A.7      | Position                                              | Vəzifəsi                                       | text     | —         |
| A.8      | Phone / WhatsApp                                      | Telefon / WhatsApp                             | text     | —         |
| A.9      | E-mail                                                | E-poçt                                         | text     | —         |
| A.10     | Website                                               | Veb sayt                                       | text     | —         |
| A.11     | Construction licence held? ⚠ MANDATORY                | Tikinti lisenziyası mövcuddurmu? ⚠ MƏCBURİ     | Y/N      | A-04 · KO |
| A.12     | Licence number                                        | Lisenziyanın nömrəsi                           | text     | A-04      |
| A.13     | Issue date                                            | Verilmə tarixi                                 | date     | A-04      |
| A.14     | Valid until                                           | Etibarlılıq müddəti                            | date     | A-04      |
| A.15     | Tax clearance certificate (last 3 months) ⚠ MANDATORY | Vergi borcsuzluğu arayışı (son 3 ay) ⚠ MƏCBURİ | Y/N      | A-05 · KO |
| A.16     | Certificate date                                      | Arayışın verilmə tarixi                        | date     | A-05      |
| A.17     | Legal form                                            | Təsis forması                                  | text     | A-03      |
| A.18     | Number of founders                                    | Təsisçilərin sayı                              | number   | A-06      |
| A.19     | Charter capital (AZN)                                 | Nizamnamə kapitalı (AZN)                       | number   | A-03      |
| A.20     | IBAN                                                  | IBAN                                           | text     | A-07      |

**B. Financial / B. Maliyyə**

| **Code** | **Question (EN)**        | **Sual (AZ)**                          | **Type** | **Doc** |
|----------|--------------------------|----------------------------------------|----------|---------|
| B.1      | Turnover, last full year | Son tam il üzrə dövriyyə               | number   | B-01    |
| B.2      | Year −2                  | İkinci son il                          | number   | B-01    |
| B.3      | Year −3                  | Üçüncü son il                          | number   | B-01    |
| B.4      | 3-year average (auto)    | Son 3 ilin orta dövriyyəsi (avtomatik) | calc     | —       |
| B.5      | Equity                   | Öz kapitalı (Equity)                   | number   | B-02    |
| B.6      | Current assets           | Cari aktivlər                          | number   | B-02    |
| B.7      | Current liabilities      | Cari öhdəliklər                        | number   | B-02    |
| B.8      | Current ratio (auto)     | Likvidlik əmsalı (avtomatik)           | calc     | —       |
| B.9      | Bank credit line?        | Bank kredit xətti mövcuddurmu?         | Y/N      | B-03    |
| B.10     | Credit line amount       | Kredit xəttinin məbləği                | number   | B-03    |
| B.11     | Bank                     | Bank adı                               | text     | B-03    |
| B.12     | Audited in last 3 years? | Son 3 ildə audit olmuşdurmu?           | Y/N      | B-04    |
| B.13     | Audit firm               | Audit şirkəti                          | text     | B-04    |

**C. Technical experience / C. Texniki Təcrübə**

| **Code** | **Question (EN)**                                              | **Sual (AZ)**                                                     | **Type** | **Doc** |
|----------|----------------------------------------------------------------|-------------------------------------------------------------------|----------|---------|
| C.t1     | Project table: name, client, start, end, duration, value, type | Layihə cədvəli: ad, sifarişçi, başlama, bitmə, müddət, dəyər, tip | table    | C-01    |
| C.t2     | Table: name, client, start, planned end, %, value              | Layihə cədvəli: ad, sifarişçi, başlama, planlanan bitmə, %, dəyər | table    | —       |
| C.1      | ISO 9001 held?                                                 | ISO 9001 mövcuddurmu?                                             | Y/N      | C-02    |
| C.2      | Certificate number                                             | Sertifikatın nömrəsi                                              | text     | C-02    |
| C.3      | Valid until                                                    | Etibarlılıq tarixi                                                | date     | C-02    |

**D. Facilities & equipment / D. Maddi-Texniki Baza**

| **Code** | **Question (EN)**             | **Sual (AZ)**                            | **Type** | **Doc** |
|----------|-------------------------------|------------------------------------------|----------|---------|
| D.1      | Head office address           | Baş ofisin ünvanı                        | text     | D-01    |
| D.2      | Office area (m²)              | Ofis sahəsi (m²)                         | number   | D-01    |
| D.3      | Ownership (own/rent)          | Mülkiyyət forması (öz/kira)              | text     | D-01    |
| D.4      | Workshop area (m²)            | Emalatxana sahəsi (m²)                   | number   | D-01    |
| D.5      | Warehouse area (m²)           | Anbar sahəsi (m²)                        | number   | D-01    |
| D.6      | Total construction equipment  | İnşaat avadanlıqlarının ümumi sayı       | number   | D-02    |
| D.7      | Cranes / hoists               | Kran / yük qaldırıcı                     | number   | D-02    |
| D.8      | Concrete mixers & pumps       | Beton qarışdırıcı və nasos               | number   | D-02    |
| D.9      | Welding & metalwork equipment | Qaynaq və metal emal avadanlığı          | number   | D-02    |
| D.10     | Power tool sets               | Elektrik alət dəstləri                   | number   | D-02    |
| D.11     | Trucks                        | Yük maşınları                            | number   | D-03    |
| D.12     | Vans / cars                   | Mikroavtobus / minik                     | number   | D-03    |
| D.13     | Heavy machinery               | İxtisas texnikası (ekskavator, buldozer) | number   | D-03    |
| D.14     | All vehicles insured?         | Bütün nəqliyyat sığortalıdırmı?          | Y/N      | D-03    |

**E. Human resources / E. Kadr Resursları**

| **Code** | **Question (EN)**                   | **Sual (AZ)**                        | **Type** | **Doc** |
|----------|-------------------------------------|--------------------------------------|----------|---------|
| E.1      | Permanent staff                     | Ümumi daimi heyət                    | number   | E-01    |
| E.2      | Temporary / contract                | Müvəqqəti / müqaviləli               | number   | E-01    |
| E.3      | Administrative staff                | İnzibati heyət                       | number   | E-01    |
| E.4      | Chief engineer / technical director | Baş mühəndis / texniki direktor      | number   | E-02    |
| E.5      | Civil engineers                     | Tikinti mühəndisləri                 | number   | E-02    |
| E.6      | Architects                          | Memarlar                             | number   | E-02    |
| E.7      | Electrical engineers                | Elektrik mühəndisləri                | number   | E-02    |
| E.8      | MEP / HVAC engineers                | MEP / HVAC mühəndisləri              | number   | E-02    |
| E.9      | Technicians / foremen               | Texniklər (usta, texnik)             | number   | E-02    |
| E.10     | Skilled workers                     | İxtisaslı fəhlələr                   | number   | E-01    |
| E.11     | Unskilled workers                   | Köməkçi fəhlələr                     | number   | E-01    |
| E.12     | Full-time HSE specialist?           | Tam ştatlı SƏTƏMM mütəxəssisi varmı? | Y/N      | E-03    |
| E.13     | HSE specialist certified?           | SƏTƏMM ixtisas sertifikatı           | Y/N      | E-03    |
| E.14     | QC staff                            | Keyfiyyət nəzarət heyəti             | number   | E-02    |
| E.15     | Regular subcontractors              | Daimi subpodratçıların sayı          | number   | E-04    |
| E.16     | Contracts formalised?               | Müqavilələr rəsmiləşdirilibmi?       | Y/N      | E-04    |

**F. HSE & quality / F. SƏTƏMM və Keyfiyyət**

| **Code** | **Question (EN)**                | **Sual (AZ)**                           | **Type** | **Doc**   |
|----------|----------------------------------|-----------------------------------------|----------|-----------|
| F.1      | HSE policy document? ⚠ MANDATORY | SƏTƏMM siyasəti sənədi varmı? ⚠ MƏCBURİ | Y/N      | F-01 · KO |
| F.2      | HSE plan date                    | SƏTƏMM planının tarixi                  | date     | F-01      |
| F.3      | HSE training delivered?          | İşçilərə SƏTƏMM təlimi keçirilirmi?     | Y/N      | F-02      |
| F.4      | Training hours / year            | İl ərzində təlim saatları               | number   | F-02      |
| F.5      | ISO 14001?                       | ISO 14001 varmı?                        | Y/N      | F-03      |
| F.6      | Number                           | Nömrə                                   | text     | F-03      |
| F.7      | Valid until                      | Etibarlılıq                             | date     | F-03      |
| F.8      | ISO 45001?                       | ISO 45001 varmı?                        | Y/N      | F-04      |
| F.9      | Number                           | Nömrə                                   | text     | F-04      |
| F.10     | Valid until                      | Etibarlılıq                             | date     | F-04      |
| F.11     | Fatalities                       | Ölümlə nəticələnən hadisə               | number   | F-05      |
| F.12     | Serious injuries                 | Ağır xəsarət                            | number   | F-05      |
| F.13     | Lost-time incidents              | İş günü itkisi ilə hadisə               | number   | F-05      |
| F.14     | LTIR (last year)                 | LTIR (son il)                           | number   | F-05      |
| F.15     | All workers issued PPE?          | Bütün işçilər FMV ilə təmin olunurmu?   | Y/N      | F-06      |
| F.16     | PPE quality certificate?         | FMV keyfiyyət sertifikatı               | Y/N      | F-06      |

**G. Insurance & references / G. Sığorta və Referanslar**

| **Code** | **Question (EN)**                                 | **Sual (AZ)**                                          | **Type** | **Doc** |
|----------|---------------------------------------------------|--------------------------------------------------------|----------|---------|
| G.1      | Professional liability insurance?                 | Peşəkar məsuliyyət sığortası varmı?                    | Y/N      | G-01    |
| G.2      | Insurer                                           | Sığorta şirkəti                                        | text     | G-01    |
| G.3      | Policy number                                     | Polis nömrəsi                                          | text     | G-01    |
| G.4      | Cover limit (AZN)                                 | Sığorta məbləği (AZN)                                  | number   | G-01    |
| G.5      | Valid until                                       | Etibarlılıq tarixi                                     | date     | G-01    |
| G.6      | General liability insurance?                      | Ümumi məsuliyyət sığortası varmı?                      | Y/N      | G-01    |
| G.7      | Cover limit (AZN)                                 | Sığorta məbləği (AZN)                                  | number   | G-01    |
| G.t1     | Reference table: client, project, contact, letter | Referans cədvəli: müştəri, layihə, əlaqə şəxsi, məktub | table    | G-02    |

**Appendix B — Document checklist**

| **Code** | **Document (EN)**                     | **Sənəd (AZ)**                              | **Mandatory** |
|----------|---------------------------------------|---------------------------------------------|---------------|
| A-01     | State registration certificate        | Şirkətin dövlət qeydiyyatı sənədi           | Yes           |
| A-02     | Tax ID & trade register extract       | VÖEN və Ticarət reyestri çıxarışı           | Yes           |
| A-03     | Charter (latest)                      | Nizamnamə (son redaksiyası)                 | Yes           |
| A-04     | Construction licence (valid)          | Tikinti lisenziyası (qüvvədə)               | Yes           |
| A-05     | Tax clearance (last 3 months)         | Vergi borcsuzluğu arayışı (son 3 ay)        | Yes           |
| A-06     | Founders' ID copies                   | Təsisçilərin şəxsiyyət vəsiqəsi             | Optional      |
| A-07     | Bank details (IBAN letter)            | Bank rekvizitləri (IBAN)                    | Optional      |
| B-01     | P&L, last 3 years                     | Son 3 ilin mənfəət-zərər hesabatı           | Yes           |
| B-02     | Balance sheet, last year              | Son ilin balans hesabatı                    | Yes           |
| B-03     | Bank credit line letter               | Bank kredit xətti məktubu                   | Optional      |
| B-04     | Audited financial statement           | Auditdən keçmiş hesabat                     | Optional      |
| C-01     | Project certificates & client letters | Layihə sertifikatları və müştəri məktubları | Yes           |
| C-02     | ISO 9001 certificate                  | ISO 9001 sertifikatı                        | Optional      |
| D-01     | Office/workshop title or lease        | Ofis/emalatxana mülkiyyət/kira müqaviləsi   | Optional      |
| D-02     | Equipment list & photos               | Avadanlıq siyahısı və şəkilləri             | Optional      |
| D-03     | Vehicle registration documents        | Nəqliyyat texniki pasportları               | Optional      |
| E-01     | Staff list (counts)                   | İşçi heyətinin siyahısı                     | Yes           |
| E-02     | Engineers' diplomas                   | Mühəndis diplomları                         | Optional      |
| E-03     | HSE specialist certificate            | SƏTƏMM mütəxəssisinin sertifikatı           | Optional      |
| E-04     | Subcontractor agreements list         | Subpodratçı müqavilələri siyahısı           | Optional      |
| F-01     | HSE policy & plan                     | SƏTƏMM siyasəti və planı                    | Yes           |
| F-02     | HSE training log                      | SƏTƏMM təlim jurnalı                        | Optional      |
| F-03     | ISO 14001 certificate                 | ISO 14001 sertifikatı                       | Optional      |
| F-04     | ISO 45001 certificate                 | ISO 45001 sertifikatı                       | Optional      |
| F-05     | Accident report (3 years)             | Bədbəxt hadisə hesabatı (3 il)              | Optional      |
| F-06     | PPE certificates                      | FMV sertifikatları                          | Optional      |
| G-01     | Liability insurance policy            | Məsuliyyət sığortası polisi                 | Optional      |
| G-02     | Client reference letters (min 3)      | Müştəri referans məktubları (min 3)         | Yes           |
| H-01     | Signed declaration                    | Rəhbərin imzaladığı Bəyannamə               | Yes           |
| H-02     | Stamped form                          | Möhürlə təsdiq olunmuş forma                | Yes           |

**Appendix C — Vendors loaded in the prototype**

| **Vendor**                | **VÖEN**                | **Reg.**    | **Staff** | **Rev4 total** | **Decision**      |
|---------------------------|-------------------------|-------------|-----------|----------------|-------------------|
| İbrahimovs Group MMC      | 1804034391              | 2018        | 10        | 39.1           | F — RƏDD          |
| Snek Group MMC            | —                       | —           | —         | 1              | KO — RƏDD         |
| Akabe İnşaat              | —                       | —           | —         | 1              | KO — RƏDD         |
| Bianco Group MMC          | —                       | —           | —         | 1              | KO — RƏDD         |
| VVESA MMC (Wesa)          | 1003915341              | 2015        | 80        | 90.3           | A — Əla (DƏVƏT)   |
| Hasan Holding             | 1700116471              | 2004        | 65        | 76.2           | C — Şərti DƏVƏT   |
| Ranuni MMC (Parket House) | 2004765571              | 2017        | 10        | 38.3           | KO — RƏDD         |
| Ray Group                 | 2004824871              | 2018        | —         | 32.3           | KO — RƏDD         |
| Shield                    | 2002138471              | 2011        | 60        | 94.7           | A — Əla (DƏVƏT)   |
| Arti Qrup MMC             | 1801310241              | 2021        | 155       | 84             | B — Yaxşı (DƏVƏT) |
| Gilan (Kila Qrup)         | 1400915571 / 7200482051 | 2006 / 2016 | 327       | 73             | C — Şərti DƏVƏT   |
| Golden ABA                | —                       | —           | —         | 1              | KO — RƏDD         |
| İNPROCON MMC              | 1701503521              | 2013        | 41        | 83.5           | B — Yaxşı (DƏVƏT) |
