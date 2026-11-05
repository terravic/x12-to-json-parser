# Product Requirements Document (PRD): EDI X12-to-JSON Healthcare Parser and HL7 C-CDA Integration Engine

## 1. Document Overview

### 1.1 Purpose
This Product Requirements Document specifies the functional, architectural, interface, and verification requirements for the EDI X12-to-JSON Healthcare Parser (`x12_parser`), its HL7 C-CDA XML clinical payload extractor, its HTTP REST and Server-Sent Events (SSE) API service, and its standalone interactive HTML5 studio (`dashboard.html`) as defined in `DESIGN.md`.

### 1.2 Problem Statement
Healthcare administrative and clinical data exchanges rely on ANSI ASC X12 Version 5010 transactions (`270`, `271`, `278`, `837`, `835`, `277`, `275`) and embedded HL7 Consolidated Clinical Document Architecture (C-CDA R2.1 and R1.1) XML payloads. Raw X12 streams use positional delimiters, compact segment identifiers, and nested hierarchical loops (`2000`, `2010`, `2100`, `2300`, `2400`), while clinical `275` envelopes embed raw or Base64-encoded XML documents inside binary segments (`BDS`/`BIN`). Engineering teams, billing analysts, utilization reviewers, and automated workflows require deterministic conversion of these streams into structured JSON alongside synchronized visual inspection tools that operate without external runtime dependencies.

### 1.3 Scope
The system provides:
1. A Python 3.8+ standard-library parsing engine converting X12 5010 interchanges and embedded C-CDA XML payloads into hierarchical, semantically keyed JSON.
2. Specialized transaction parsers covering eligibility (`270`/`271`), prior authorization (`278`), claims (`837`), remittance advice (`835`), claim status and attachment requests (`277`), and clinical attachment envelopes (`275`).
3. A standalone, single-file HTML5 dashboard (`dashboard.html` and transaction bundles in `docs/`) implementing the typography, theme, layout, visualization, and cross-tab synchronization specifications in `DESIGN.md`.
4. A command-line interface (`x12_parser.cli`), a multi-threaded HTTP REST and SSE streaming server (`x12_parser.api.server`), OpenAPI 3.1.0 schemas, and skill/plugin manifests.

---

## 2. Target Users and Operational Scenarios

| User Group | Primary Operational Need | System Capability |
|---|---|---|
| **Revenue Cycle and Billing Analysts** | Inspect submitted `837` claim charges, `835` remittance payments, contractual write-offs, and CARC reason codes without reading raw EDI text. | Synchronized KPI strip, financial domain charts, claim/remittance tables, and plain-language code descriptions. |
| **Clinical Documentation Specialists** | Identify pended claims in `277` notifications and verify patient demographics, allergies, medications, diagnoses, vitals, and progress notes in `275` attachments. | Automated `required_attachments` flagging (`STC`/`PWK`) and structured `attached_clinical_data` C-CDA XML decoding. |
| **Healthcare Integration Engineers** | Parse arbitrary X12 5010 streams with custom delimiters via Python API, CLI pipes, or HTTP endpoints with deterministic schema output. | `X12Parser`, `CCDAParser`, `x12_parser.cli`, and `POST /v1/parse/x12` with SHA-256 provenance and envelope parity validation. |
| **Automated Agent Workflows** | Invoke structured parsing and generate self-contained HTML inspection artifacts in local or sandboxed webview environments. | OpenAPI 3.1.0 specification, `x12_parser/manifests/skill-manifest.json`, and `skills/x12-healthcare-parser/SKILL.md`. |

---

## 3. Functional Requirements

### 3.1 Core X12 5010 Parsing Engine (`x12_parser/engine/`)
- **FR-ENG-01 (Dynamic Delimiter Detection):** Extract element separator (`ISA` byte index 3), repetition separator (`ISA11`), component sub-element separator (`ISA16`), and segment terminator (character immediately following `ISA16`) directly from the 106-character `ISA` interchange header, supporting standard (`*`, `:`, `^`, `~`) and custom (`|`, `>`, `!`, `#`) delimiters.
- **FR-ENG-02 (Binary Payload Preservation):** Preserve embedded XML and Base64 payloads inside `BDS` and `BIN` segments when XML attributes or text bodies contain characters matching X12 delimiters.
- **FR-ENG-03 (Envelope Parity Validation):** Parse and correlate `ISA`/`IEA` interchange headers, `GS`/`GE` functional groups, and `ST`/`SE` transaction sets, supporting multi-group and multi-transaction batches.
- **FR-ENG-04 (Hierarchical Loop Construction):** Assemble flat segment sequences into nested loop trees (`Loop 1000A/B`, `2000A/B/C`, `2010AA/AB/BA`, `2100`, `2300`, `2400`) and parent-child `HL` hierarchy nodes.
- **FR-ENG-05 (Semantic Element Mapping):** Map positional element identifiers (such as `CLM02`, `BPR02`, `CLP04`, `NM109`, `SV101`) and standard qualifier codes (entity roles, claim statuses, CARC groups, place-of-service codes, LOINC/PWK report types) to descriptive JSON keys.

### 3.2 Transaction Set Handlers (`x12_parser/transaction_parsers/`)
- **FR-TX-270/271 (Eligibility Inquiry and Benefit Response):** Extract information source, information receiver, subscriber, dependents, `EQ` service type inquiries (`270`), and `EB` benefit coverage schedules including plan descriptions, copayments, deductibles, and coinsurance rates (`271`).
- **FR-TX-278 (Prior Authorization Services Review):** Extract utilization management organization, requester, subscriber, `UM` review categories, `HCR` certification action codes and authorization numbers, `HI` diagnoses, and `SV1`/`SV2` service lines.
- **FR-TX-837 (Professional and Institutional Claims):** Extract submitter, receiver, billing provider, rendering provider, subscriber, payer, `CLM` claim headers, `DTP` service dates, `HI` ICD-10-CM diagnosis codes, and `LX`/`SV1`/`SV2` itemized service lines.
- **FR-TX-835 (Electronic Remittance Advice):** Extract `BPR` payment totals and settlement methods (`ACH`/`CHK`), `TRN` trace numbers, payer/payee records, `CLP` claim adjudications, `CAS` claim and line adjustments (`CO`, `PR`, `OA`, `PI`), `SVC` line payments, and `PLB` provider-level adjustments.
- **FR-TX-277 (Claim Status and Attachment Requests):** Detect `STC` status categories (`R0` through `R5` and action code `A4`) paired with `PWK` paperwork segments to populate a top-level `required_attachments` list containing claim tracking numbers, payer control numbers, report type codes, transmission methods, and attachment control identifiers.
- **FR-TX-275 (Patient Information Attachment Envelope):** Extract submitter, receiver, patient, `CAT`/`EFI` metadata, and `BDS`/`BIN` payloads; detect raw UTF-8 XML versus Base64-encoded payloads; and invoke `CCDAParser` to populate `attached_clinical_data`.

### 3.3 HL7 C-CDA Clinical XML Extractor (`x12_parser/clinical_parsers/`)
- **FR-CCDA-01 (Namespace-Agnostic XML Parsing):** Parse HL7 C-CDA R2.1 and R1.1 XML documents (`urn:hl7-org:v3` and `urn:hl7-org:sdtc`) using Python's standard `xml.etree.ElementTree`.
- **FR-CCDA-02 (Structured Clinical Sections):** Extract and normalize:
  - `document_metadata`: Document ID, LOINC code, title, effective timestamp, and author details.
  - `patient_demographics`: MRN/identifiers, full name, administrative gender, birth date, marital status, address, and telecom.
  - `allergies`: Substance name, RxNorm/UNII code, reaction manifestation, severity, and status.
  - `medications`: Medication display name, RxNorm code, dose quantity/unit, route of administration, effective dates, and instructions.
  - `problems_and_diagnoses`: Condition name, ICD-10-CM or SNOMED CT code, clinical status, and onset date.
  - `vital_signs`: Organizer timestamps and individual observations (blood pressure, heart rate, respiratory rate, body temperature, SpO2, height, weight, BMI).
  - `clinical_notes_and_evaluations`: Section titles and narrative clinical text supporting medical necessity review.

---

## 4. Interactive Dashboard Requirements (`DESIGN.md` Alignment)

### 4.1 Visual, Typographic, and Theme Architecture
- **FR-UI-01 (Self-Contained Delivery):** Generate standalone HTML5 files (`dashboard.html` at the project root, `x12_parser/ui/x12_mapping_dashboard.html`, and pre-rendered files in `docs/`) containing inline CSS and ES6+ JavaScript with zero external network or CDN dependencies.
- **FR-UI-02 (Typography Stack):** Apply `DM Sans` / `Geist Sans` for UI controls and prose, `Instrument Serif` for display headers, and `Geist Mono` with `font-variant-numeric: tabular-nums` for numeric metrics, identifiers, hashes, and tables.
- **FR-UI-03 (Single-Level Bento Surfaces):** Organize panes in flat single-level grids separated by `1px solid` borders (`6px` to `8px` border radius) with solid surface tokens and zero multi-stop background gradients.
- **FR-UI-04 (Segmented Theme Control and OS Detection):** Provide a three-button segmented control (`#theme-btn-light` `Light`, `#theme-btn-dark` `Dark`, `#theme-btn-system` `System`) persisting user selection in `localStorage`, tracking OS changes via `window.matchMedia('(prefers-color-scheme: dark)')`, and embedding a backend `system_theme` fallback:
  - Light Mode tokens: `#FAFAF9` page background, `#FFFFFF` surface, `#E7E5E4` border/gridline, `#1C1917` primary text, `#787774` secondary text.
  - Dark Mode tokens: `#0D0E11` page background, `#16171D` surface, `#292A30` border/gridline, `#ECE8E2` primary text, `#9A9895` secondary text.
- **FR-UI-05 (Semantic Visualization Palette):** Apply `#0D9488` (Vibrant Teal), `#D97706` (Energetic Amber), `#4F46E5` (Vivid Indigo), `#059669` (Functional Emerald), and `#E11D48` (Deep Rose) across all charts, heatmaps, graphs, and 3D structural projections.

### 4.2 Studio Visualizations and Synchronized Tabs
- **FR-UI-06 (Full Cross-Tab State Synchronization):** Selecting any sample transaction in `#datasetSelector`, clicking a row in the heatmap or provenance audit table, or parsing a custom uploaded/pasted X12 stream (`#btnOpenUploadModal`) updates every UI component across all seven tabs:
  1. `Workspace Studio`: Six-cell KPI bento strip, 2D quantitative domain/financial/latency SVG chart (`#financialChartSurface` defaulting to `Selected Stream`), `Loop Stratum Concentration Matrix` heatmap, `Interactive Relationship Node Map` directed SVG graph with pan/zoom, and `Structural Data Diagram` 3D perspective projection (`#molecular3dSurface`, `Software Projection Fallback`) auto-selecting active X12 spatial loop lattices or C-CDA RxNorm conformers (`Lisinopril 314076`, `Penicillin G 70618`).
  2. `Interactive X12 & JSON Explorer`: Synchronized 3-column split view linking raw segments, element breakdown tables, and target JSON subtrees.
  3. `Transaction & Provenance`: Active stream provenance banner, workspace SHA-256 parity table, `ISA`/`GS`/`ST` envelope audit cells, participant entity cards, and transaction-specific tables (`837`, `835`, `277`, `275`, `271`, `270`, `278`).
  4. `C-CDA Clinical Payload`: Full decoded C-CDA R2.1 clinical view for `275` streams (both server-parsed and client-side uploaded XML/Base64) and active-stream clinical/diagnostic extraction for non-`275` streams.
  5. `Raw X12 File`: Line-numbered raw EDI stream with live search, copy, and `.x12` download.
  6. `Structured JSON`: Complete formatted JSON payload with live search, copy, and `.json` download.
  7. `Field Mapping Spec`: Searchable 5010 semantic mapping table dynamically badging segments present in the active stream (`N in stream`).
- **FR-UI-07 (Offline Client-Side and Live HTTP/SSE Parsing):** Support full client-side X12 and C-CDA XML/Base64 parsing when opened directly from local disk, while automatically connecting to `/v1/events` and `POST /v1/parse/x12?include_telemetry=1` when served via `x12_parser.api.server`.

---

## 5. Interfaces and Integration Specifications

### 5.1 Python Package API (`x12_parser`)
- `X12Parser.parse(raw_x12: str) -> dict`: Parses an X12 5010 string into structured JSON.
- `X12Parser.generate_dashboard(data_or_raw, output_path=None, raw_x12="", title=...) -> str`: Generates a standalone HTML5 dashboard string and optionally writes it to `output_path`.
- `CCDAParser.parse(xml_or_b64: str, is_base64: bool = False) -> dict`: Extracts structured clinical JSON from HL7 C-CDA XML.

### 5.2 Command-Line Interface (`x12_parser/cli.py`)
- Supports file path or `-` (`stdin`) input, `-o/--output` JSON file writing, `--pretty` formatting, `--summary` ASCII reporting, and `--html/--dashboard` HTML dashboard generation using relative paths.

### 5.3 HTTP REST and SSE Server (`x12_parser/api/server.py`)
- `GET /` and `GET /dashboard`: Serves `dashboard.html`.
- `GET /v1/health`: Returns service health and version JSON.
- `GET /v1/events`: Streams live `parse_update` telemetry events over SSE (`text/event-stream`).
- `POST /v1/parse/x12`: Accepts `application/json` (`{"raw_x12": "...", "context": "...", "source_path": "..."}`) or `text/plain`; supports `?format=html` for HTML dashboard generation and `?include_telemetry=1` for full telemetry-wrapped dataset records.
- `GET /openapi.json`, `GET /.well-known/ai-plugin.json`, `GET /skill-manifest.json`: Serves machine-readable API and skill metadata.

---

## 6. Non-Functional and Verification Requirements

- **NFR-01 (Zero Mandatory External Dependencies):** Core parsing, C-CDA XML extraction, CLI execution, HTTP/SSE serving, and HTML dashboard generation rely strictly on the Python 3.8+ standard library.
- **NFR-02 (Deterministic Output and Provenance):** Identical X12 inputs produce deterministic loop trees, semantic keys, and SHA-256 digests.
- **NFR-03 (Relative Path Portability):** All scripts, manifests, sample loaders, documentation references, and archive utilities operate using relative paths anchored at the project root directory.
- **NFR-04 (Automated Test Suite):** `tests/run_all_tests.py` validates delimiter auto-detection, custom delimiters, envelope integrity, `837`/`835`/`270`/`271`/`278` field accuracy, `277` attachment flagging, `275` raw and Base64 C-CDA extraction, REST/SSE endpoints, OpenAPI/manifest schemas, and `DESIGN.md` token compliance across 25 automated unit and integration tests.
