# Visual Dashboard Architecture & Developer Guide

This guide documents how the standalone interactive HTML5 Visual Dashboard (`dashboard.html`) operates in strict alignment with `DESIGN.md`.

---

## 1. Runtime & Execution Environment

- **Self-Contained Zero-Dependency Execution**: Renders inside standard browsers, offline `file://` contexts, and sandboxed webviews using pure HTML5, Vanilla CSS custom properties, and Vanilla ES6+ JavaScript (no external JS/CSS framework CDNs).
- **Live Server-Sent Events (SSE) & Incremental Updates**: Connects to `/v1/events` when served over HTTP (`python3 -m x12_parser.api.server`) and exposes `window.updateDashboardData(payload)` to ingest live parsed streams without resetting scroll position, active tab, or 3D/SVG camera state.
- **Empirical Data & Provenance**: Embeds SHA-256 source digests, parse execution timings, HIPAA 5010 envelope parity audits, and HL7 C-CDA R2.1 clinical payloads.

---

## 2. Typography & Theme Token System

### Typography (`DESIGN.md` Section 1)
- **UI Sans-Serif**: `DM Sans`
- **Display Serif**: `Instrument Serif`
- **Tabular Monospace**: `IBM Plex Mono` (`font-variant-numeric: tabular-nums`)

### Surface, Border & Text Tokens (`DESIGN.md` Section 3)
- **Light Mode** (`html[data-theme="light"]`):
  - `--bg-page: #FAFAF9`
  - `--bg-surface: #FFFFFF`
  - `--border: #E7E5E4` (`1px solid`, `6px`–`8px` radius)
  - `--text-primary: #1C1917`
  - `--text-secondary: #787774`
- **Dark Mode** (`html[data-theme="dark"]`):
  - `--bg-page: #0D0E11`
  - `--bg-surface: #16171D`
  - `--border: #292A30` (`1px solid`, `6px`–`8px` radius)
  - `--text-primary: #ECE8E2`
  - `--text-secondary: #9A9895`

### Three-Icon Theme Selector
- `#theme-btn-light` (`data-theme-mode="light"`, Sun SVG)
- `#theme-btn-dark` (`data-theme-mode="dark"`, Crescent Moon SVG)
- `#theme-btn-system` (`data-theme-mode="system"`, Computer Monitor SVG)
- Tracks OS appearance via `window.matchMedia('(prefers-color-scheme: dark)')` with host OS fallback (`system_theme`) and `localStorage` persistence.

---

## 3. Data Visualization & Single-Level Bento Components

All visualizations use the semantic palette (`#0D9488` Vibrant Teal, `#D97706` Energetic Amber, `#4F46E5` Vivid Indigo, `#059669` Functional Emerald, `#E11D48` Deep Rose):

1. **Financial Adjudication & Parse Telemetry Plot**: 2D quantitative coordinate chart with transparent plot background and subtle axis gridlines (`#E7E5E4` light / `#292A30` dark).
2. **Loop Stratum Concentration Matrix**: Interactive heatmap smoothly transitioning from surface background through Vibrant Teal (`#0D9488`) and Vivid Indigo (`#4F46E5`) to Deep Rose (`#E11D48`).
3. **Interactive Relationship Node Map**: Deterministic SVG DAG with pan/zoom and semantic edge coloring.
4. **Structural Data Diagram**: Interactive 3D conformer viewer (`Lisinopril RxNorm 314076`, `Penicillin G RxNorm 70618`, and `X12 Spatial Loop Lattice`) using hardware WebGL shaders with automatic 2D Canvas software projection fallback.
5. **Synchronized X12-to-JSON Inspector**: Flat 3-column split pane with `1px` cell dividers mapping raw X12 segments to element tables and JSON subtrees.

---

## 4. Generating `dashboard.html`

```bash
# Build full empirical workspace dashboard at project root
python3 -m x12_parser.ui.dashboard_generator dashboard.html

# Or generate for a specific X12 file
python3 skills/x12-healthcare-parser/scripts/generate_visual_dashboard.py sample_data/sample_837_claim.x12 -o dashboard.html
```
