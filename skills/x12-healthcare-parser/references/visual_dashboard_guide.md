# Visual Dashboard Architecture and Developer Guide

This guide documents how the standalone interactive HTML5 dashboard (`dashboard.html`) operates in alignment with `DESIGN.md`.

---

## 1. Runtime and Execution Environment

- **Self-Contained Zero-Dependency Execution**: Renders inside standard web browsers, local filesystem contexts, and sandboxed webviews using HTML5, CSS custom properties, and ES6+ JavaScript without external framework CDNs.
- **Live Server-Sent Events (SSE) and Incremental Updates**: Connects to `/v1/events` when served over HTTP (`python3 -m x12_parser.api.server`) and exposes `window.updateDashboardData(payload)` to ingest live parsed streams without resetting scroll position, active tab, or 3D/SVG viewport state.
- **Empirical Data and Provenance**: Embeds SHA-256 source digests, parse execution timings, X12 5010 envelope parity audits, and HL7 C-CDA R2.1 clinical payloads.

---

## 2. Typography and Theme Token System

### Typography (`DESIGN.md` Section 1)
- **UI Sans-Serif**: `DM Sans`
- **Display Serif**: `Instrument Serif`
- **Tabular Monospace**: `Geist Mono` (`font-variant-numeric: tabular-nums`)

### Surface, Border, and Text Tokens (`DESIGN.md` Section 3)
- **Light Mode** (`html[data-theme="light"]`):
  - `--bg-page: #FAFAF9`
  - `--bg-surface: #FFFFFF`
  - `--border: #E7E5E4` (`1px solid`, `6px` to `8px` radius)
  - `--text-primary: #1C1917`
  - `--text-secondary: #787774`
- **Dark Mode** (`html[data-theme="dark"]`):
  - `--bg-page: #0D0E11`
  - `--bg-surface: #16171D`
  - `--border: #292A30` (`1px solid`, `6px` to `8px` radius)
  - `--text-primary: #ECE8E2`
  - `--text-secondary: #9A9895`

### Segmented Theme Selector
- `#theme-btn-light` (`data-theme-mode="light"`, label `Light`)
- `#theme-btn-dark` (`data-theme-mode="dark"`, label `Dark`)
- `#theme-btn-system` (`data-theme-mode="system"`, label `System`)
- Tracks OS appearance via `window.matchMedia('(prefers-color-scheme: dark)')` with host backend fallback (`system_theme`) and `localStorage` persistence.

---

## 3. Data Visualization and Bento Components

All visualizations use the semantic palette (`#0D9488` Vibrant Teal, `#D97706` Energetic Amber, `#4F46E5` Vivid Indigo, `#059669` Functional Emerald, `#E11D48` Deep Rose):

1. **Active Transaction Financial and Domain Profile**: 2D quantitative coordinate chart with transparent plot background and horizontal axis gridlines (`#E7E5E4` light / `#292A30` dark).
2. **Loop Stratum Concentration Matrix**: Interactive heatmap interpolating from surface background through Vibrant Teal (`#0D9488`) and Vivid Indigo (`#4F46E5`) to Deep Rose (`#E11D48`).
3. **Interactive Relationship Node Map**: Deterministic SVG directed graph with pan, zoom, and semantic link coloring.
4. **Structural Data Diagram**: Interactive 3D perspective conformer viewer (`Lisinopril RxNorm 314076`, `Penicillin G RxNorm 70618`, and `Active X12 Spatial Loop Lattice`) using deterministic 3D perspective projection (`Software Projection Fallback`).
5. **Synchronized X12-to-JSON Explorer**: Flat 3-column split pane with `1px` cell dividers mapping raw X12 segments to element tables and JSON subtrees.

---

## 4. Generating `dashboard.html`

```bash
# Build workspace dashboard at project root
python3 -m x12_parser.ui.dashboard_generator dashboard.html

# Generate dashboard for a specific X12 file
python3 skills/x12-healthcare-parser/scripts/generate_visual_dashboard.py sample_data/sample_837_claim.x12 -o dashboard.html
```
