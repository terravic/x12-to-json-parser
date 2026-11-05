---
name: x12-healthcare-parser
description: EDI X12 (5010) and HL7 C-CDA XML healthcare transaction parser with interactive HTML mapping dashboards, field-by-field semantic dictionaries, and synchronized segment inspection.
---

# EDI X12 and C-CDA Healthcare Parser Skill

This skill parses raw EDI X12 healthcare transactions (`837`, `835`, `270`, `271`, `277`, `275`, `278`) and embedded HL7 C-CDA XML clinical documents into structured JSON and generates standalone interactive HTML dashboards (`dashboard.html`).

---

## 1. Visual Dashboard Architecture

1. **Self-Contained HTML5, CSS, and JavaScript Execution**: Renders standalone single-page dashboards (`dashboard.html`) directly from local disk or over HTTP without external framework CDNs.
2. **Light, Dark, and System Palette (`DESIGN.md`)**: Uses `#FAFAF9` and `#FFFFFF` surfaces in Light Mode and `#0D0E11` and `#16171D` surfaces in Dark Mode, paired with `DM Sans`, `Instrument Serif`, and tabular `Geist Mono`.
3. **Segmented Theme Selector**: Switches between Light (`#theme-btn-light`), Dark (`#theme-btn-dark`), and System (`#theme-btn-system`) preferences via `localStorage`, real-time `matchMedia('(prefers-color-scheme: dark)')`, and host desktop environment detection.
4. **Live SSE Telemetry and Multi-Modal Visualization**: Includes a 2D quantitative financial and domain chart, loop concentration heatmap, SVG `Interactive Relationship Node Map`, 3D perspective `Structural Data Diagram`, and `/v1/events` Server-Sent Events streaming.

For technical specifications, see [visual_dashboard_guide.md](skills/x12-healthcare-parser/references/visual_dashboard_guide.md).

---

## 2. Dashboard Tabs and Capabilities

1. **Workspace Studio**:
   - Six-cell KPI summary strip (`tabular-nums`), 2D quantitative domain chart, loop concentration matrix, interactive directed graph, and 3D spatial conformer projection.
2. **Interactive X12 and JSON Explorer**:
   - Clickable raw X12 segment stream synchronized with segment definitions, element-by-element parsed tables, and target JSON subtrees.
3. **Transaction and Provenance**:
   - SHA-256 digests, parse timings, envelope parity checks (`ISA`/`GS`/`ST`/`SE`/`GE`/`IEA`), business entity cards, and transaction-specific detail tables for `837`, `835`, `277`, `275`, `271`, `270`, and `278`.
4. **C-CDA Clinical Payload**:
   - Decoded HL7 C-CDA R2.1 clinical summary for `275` envelopes (demographics, allergies, active medications, diagnoses, vital signs, clinical notes) and diagnostic/clinical extracts for non-`275` streams.
5. **Raw X12 File**:
   - Line-numbered raw EDI stream viewer with search filtering, clipboard copy, and `.x12` download.
6. **Structured JSON**:
   - Complete parsed JSON tree with search filtering, clipboard copy, and `.json` download.
7. **Field Mapping Spec**:
   - Searchable X12 5010 to JSON dictionary highlighting segments active in the selected transaction stream.

---

## 3. Execution Workflow

### Command-Line Dashboard Generation
```bash
python3 skills/x12-healthcare-parser/scripts/generate_visual_dashboard.py sample_data/sample_837_claim.x12 -o docs/dashboard_837_claim.html
```

### Python Library Execution
```python
from x12_parser import X12Parser

parsed_data = X12Parser.parse(raw_x12_content)

X12Parser.generate_dashboard(
    parsed_data,
    output_path="docs/x12_dashboard.html",
    raw_x12=raw_x12_content,
    title="Dashboard - Healthcare Transaction"
)
```

---

## 4. Reference Files

- **Dashboard Generator Script**: [generate_visual_dashboard.py](skills/x12-healthcare-parser/scripts/generate_visual_dashboard.py)
- **Visual Dashboard Guide**: [visual_dashboard_guide.md](skills/x12-healthcare-parser/references/visual_dashboard_guide.md)
- **EDI to JSON Mapping Specifications**: [x12_json_mapping_specs.md](skills/x12-healthcare-parser/references/x12_json_mapping_specs.md)
- **Python Usage Example**: [parse_and_visualize_example.py](skills/x12-healthcare-parser/examples/parse_and_visualize_example.py)
