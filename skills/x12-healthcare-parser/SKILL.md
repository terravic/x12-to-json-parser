---
name: x12-healthcare-parser
description: Production-ready EDI X12 (5010) and C-CDA XML healthcare transaction parser with interactive Canvas UI visual mapping dashboards, field-by-field semantic dictionaries, and live translation inspectors.
---

# EDI X12 & C-CDA Healthcare Parser Skill

This skill enables autonomous agents and users to parse raw EDI X12 healthcare transactions (837, 835, 270, 271, 277, 275, 278) and embedded C-CDA XML clinical documents into structured JSON, as well as render interactive, business-ready Canvas UI dashboards.

---

## 1. Canvas UI & Visual Dashboard Support

Enterprise AI environments render custom Canvas UI widgets using a sandboxed HTML/CSS/JS container:

### How Canvas UI Rendering Works
1. **HTML/JS/CSS Execution**: Renders self-contained HTML/JS/CSS documents in an isolated sandbox.
2. **Tailwind CSS Styling**: Styles components using Tailwind CSS:
   ```html
   <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
   ```
3. **Theme & CSS Palette Variables**: Supports responsive theme variables (`--app-background`, `--app-foreground`, `--app-card`, `--app-card-border`, `--app-border`, `--app-primary`, `--app-muted`, `--vscode-font-family`).
4. **Light & Dark Theme Toggle**: The UI adapts seamlessly to system themes via `html.light` and `html.dark` classes, plus a built-in user-clickable theme switcher.
5. **Embedding**:
   - Inline Embed Tag:
     ```html
     <agent-embed src="file:///docs/x12_mapping_dashboard.html" height="500px"></agent-embed>
     ```
   - Standalone Dashboard File: Saved directly to `docs/x12_mapping_dashboard.html` or generated on-demand.

---

## 2. Interactive Visual Dashboard (`x12_mapping_dashboard.html`)

The visual dashboard provides:
- **Transaction Overview**: Quick stats across 837 Claims, 835 Remittances, 270/271 Eligibility, 278 Prior Authorization, 277 Status Requests, and 275 Clinical Attachments.
- **Section-by-Section Semantic Field Guides**:
  1. *Control Envelopes*: `ISA`, `GS`, `ST`, `SE`, `GE`, `IEA`
  2. *Entities & Demographics*: `NM1`, `N3`, `N4`, `PER`, `DMG`, `SBR`, `PAT`
  3. *837 Claims & Services*: `CLM`, `DTP`, `HI`, `LX`, `SV1`, `SV2`, `PWK`
  4. *835 Payment Adjudication*: `BPR`, `TRN`, `CLP`, `CAS`, `SVC`, `PLB`
  5. *277 Status & Attachment Flagging*: `STC` (R0-R5), `PWK` &rarr; `required_attachments`
  6. *275 & C-CDA XML Payloads*: `BDS`, `BIN`, `CAT` &rarr; Demographics, Allergies, Medications, Diagnoses, Vitals, Notes
- **⚡ Live Interactive Inspector & Converter**:
  - Clickable raw EDI segments dynamically highlight corresponding JSON properties, loop definitions, and syntax validation rules.
  - Interactive sample switcher for 837, 835, 277, and 275 transactions.
- **Instant Search & Filter**: Real-time filter across all segment names, JSON paths, and explanations.
- **Light/Dark Display Toggle**: High-contrast, business-ready aesthetic matching corporate healthcare standards.

---

## 3. Invoking the Parser from Code

### Python API
```python
from x12_parser import X12Parser

parsed_json = X12Parser.parse(raw_x12_string)
```

### CLI
```bash
python3 -m x12_parser.cli sample_data/sample_837_claim.x12 --pretty
```

### REST API Server
```bash
python3 -m x12_parser.api.server 8000
# Visual Dashboard: http://localhost:8000/dashboard
# OpenAPI Spec:     http://localhost:8000/openapi.json
# Parse Endpoint:   POST http://localhost:8000/v1/parse/x12
```

