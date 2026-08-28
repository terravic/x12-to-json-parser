---
name: x12-healthcare-parser
description: Production-ready EDI X12 (5010) and C-CDA XML healthcare transaction parser with interactive visual mapping dashboards, field-by-field semantic dictionaries, and live translation inspectors.
---

# EDI X12 & C-CDA Healthcare Parser Skill

This skill enables autonomous agents and users to parse raw EDI X12 healthcare transactions (`837`, `835`, `270`, `271`, `277`, `275`, `278`) and embedded C-CDA XML clinical documents into structured JSON, as well as render interactive, business-ready visual dashboards.

---

## 1. Visual Dashboard Capabilities

Enterprise AI environments render custom visual UI widgets using a sandboxed `<iframe>` container.

### How Dashboard Rendering Works
1. **Sandboxed HTML/JS/CSS Execution**: Renders self-contained single-page dashboards with full DOM interactivity and zero external node dependencies.
2. **Tailwind CSS Styling**:
   ```html
   <script src="https://cdn.tailwindcss.com"></script>
   ```
3. **Workspace Theme Adaptation**: Uses CSS variables (`--app-background`, `--app-foreground`, `--app-card`, `--app-border`, `--app-primary`, `--app-muted`, etc.) to match host workspace color palettes.
4. **Light & Dark Theme Toggle**: Adapts seamlessly to system preferences via `html.light` / `html.dark` classes with a built-in user theme switch button.

For architecture and sandbox details, see the [Visual Dashboard Guide](skills/x12-healthcare-parser/references/visual_dashboard_guide.md).

---

## 2. Interactive Visual Dashboard Features

The visual dashboard provides:

1. **Interactive X12 & JSON Synchronized Inspector**:
   - **Clickable Segment Stream**: Click any segment (`ISA`, `GS`, `ST`, `CLM`, `NM1`, `SV1`, `CLP`, `CAS`, `STC`, `BDS`, etc.) to inspect its details.
   - **Healthcare Business Meaning Card**: Displays segment tag, official name, healthcare workflow purpose, EDI 5010 loop name, target JSON key path, and element-by-element value breakdown table.
   - **JSON Equivalent Subtree**: Displays the exact JSON node corresponding to the clicked segment with one-click copy.
2. **Transaction Details & Metrics**:
   - KPI metrics bar (Transaction Type, Billed/Paid Amount, Claims, Service Lines, Flagged Attachments, Clinical records).
   - Envelope grids (ISA, GS, ST, SE, GE, IEA).
   - Business Entities cards (Submitter, Receiver, Billing Provider, Subscriber, Patient, Payers).
   - Transaction-specific tables for 837 Claims, 835 Remittance, 277 Attachment requests, 270/271 Eligibility, and 278 Prior Authorization.
3. **C-CDA Clinical Payload Viewer (for 275 transactions)**:
   - Formatted clinical document viewer displaying Patient Demographics, Allergies, Active Medications, Problem List / Diagnoses, Vital Signs, and Clinical Notes.
4. **Raw X12 File Viewer**:
   - Line numbering, syntax highlighting, search/filter, copy EDI text, and download `.x12` file.
5. **Structured JSON Viewer**:
   - Complete hierarchical JSON output with syntax highlighting, search/filter, copy JSON, and download `.json` file.
6. **Field Mapping Specification**:
   - Complete searchable dictionary of standard X12 segments to JSON mappings.
7. **Live In-Dashboard Parser & Sample Switcher**:
   - Drag-and-drop or paste any custom X12 transaction directly in the UI to re-parse and re-render on the fly.

---

## 3. Workflow: Parsing & Generating Visual Dashboards

When the user provides an X12 file or asks to parse/inspect EDI transactions:

### Step 1: Execute Parser & Dashboard Generator
Run the executable generator helper script:
```bash
python3 skills/x12-healthcare-parser/scripts/generate_visual_dashboard.py <path_to_file.x12> -o docs/x12_dashboard.html
```

Or from Python:
```python
from x12_parser import X12Parser

# Parse to structured JSON
parsed_data = X12Parser.parse(raw_x12_content)

# Generate interactive visual dashboard
X12Parser.generate_dashboard(
    parsed_data,
    output_path="docs/x12_dashboard.html",
    raw_x12=raw_x12_content,
    title="Dashboard - Healthcare Transaction"
)
```

### Step 2: Present Results to User
1. Summarize the transaction type, key metrics (billed charges, paid amounts, claims count, clinical findings).
2. Provide a relative path link to open the visual dashboard:
   ```markdown
   [Open Interactive Visual Dashboard](docs/x12_dashboard.html)
   ```

---

## 4. Helper Scripts & References

- **Executable Helper Script**: [generate_visual_dashboard.py](skills/x12-healthcare-parser/scripts/generate_visual_dashboard.py)
- **Visual Dashboard Guide**: [visual_dashboard_guide.md](skills/x12-healthcare-parser/references/visual_dashboard_guide.md)
- **EDI to JSON Mapping Specifications**: [x12_json_mapping_specs.md](skills/x12-healthcare-parser/references/x12_json_mapping_specs.md)
- **Python Usage Example**: [parse_and_visualize_example.py](skills/x12-healthcare-parser/examples/parse_and_visualize_example.py)
