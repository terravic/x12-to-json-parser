# Visual Dashboard Architecture & Developer Guide

This guide explains how the interactive Visual Dashboard operates and details how to build rich, responsive, interactive HTML/JS/CSS dashboards for healthcare transactions.

---

## 1. Visual Dashboard Execution Environment

The Visual Dashboard provides an interactive, visual runtime for exploring healthcare transactions alongside structured data output.

### Key Characteristics:
- **Sandboxed `<iframe>` & Browser Container**: Renders self-contained HTML/CSS/JS documents inside a secure, isolated container.
- **Full Web Standards Support**: Supports HTML5, modern ES6+ JavaScript, CSS grid/flexbox, SVG graphics, and web fonts.
- **Zero Build Step / CDN Integration**: Uses standalone single-file distribution with Tailwind CSS without requiring node_modules bundling.
- **Bi-Directional Interactivity**: Allows clickable elements, stateful tab switching, live search filters, modal popups, clipboard operations, and client-side data parsing.

---

## 2. Styling & CSS Theme Variables

Dashboards adapt automatically to host workspace themes (Light, Dark, High Contrast) using CSS custom properties.

### Tailwind CSS CDN:
```html
<script src="https://cdn.tailwindcss.com"></script>
```

### Standard Theme Variables:
```css
:root {
  --app-background: #0f172a;
  --app-foreground: #f8fafc;
  --app-card: #1e293b;
  --app-card-border: #334155;
  --app-card-foreground: #f8fafc;
  --app-border: #334155;
  --app-primary: #3b82f6;
  --app-primary-foreground: #ffffff;
  --app-muted: #334155;
  --app-muted-foreground: #94a3b8;
  --vscode-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

html.light {
  --app-background: #f8fafc;
  --app-foreground: #0f172a;
  --app-card: #ffffff;
  --app-card-border: #e2e8f0;
  --app-card-foreground: #0f172a;
  --app-border: #e2e8f0;
  --app-primary: #2563eb;
  --app-primary-foreground: #ffffff;
  --app-muted: #f1f5f9;
  --app-muted-foreground: #64748b;
}

body {
  background-color: var(--app-background);
  color: var(--app-foreground);
  font-family: var(--vscode-font-family);
}
```

### Automatic Theme Detection & Manual Toggle:
```javascript
// Detect OS / Host Theme
if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
  document.documentElement.classList.remove('dark');
  document.documentElement.classList.add('light');
}

// User-clickable toggle
function toggleTheme() {
  const html = document.documentElement;
  if (html.classList.contains('light')) {
    html.classList.remove('light');
    html.classList.add('dark');
  } else {
    html.classList.remove('dark');
    html.classList.add('light');
  }
}
```

---

## 3. Core Visual Dashboard Components for X12 Healthcare

The X12 Visual Dashboard is organized into modular components:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Header & KPI Metrics Bar (Tx Type, Billed/Paid Total, Claims, C-CDA)     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. Navigation Tabs                                                          │
│    [Interactive Explorer] [Details] [C-CDA] [Raw X12] [JSON]                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. Main Display Panel (Dynamic depending on active tab):                    │
│                                                                             │
│  ┌─────────────────────────┬──────────────────────┬──────────────────────┐  │
│  │ Left: Clickable X12     │ Middle: Segment Spec │ Right: Structured    │  │
│  │ Segment List with Loop  │ & Business Meaning   │ JSON Tree with Auto  │  │
│  │ & Tag Badges            │ Element Breakdown    │ Highlight & Sync     │  │
│  └─────────────────────────┴──────────────────────┴──────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. Client-side Drag-and-Drop Parser & Quick Sample Switcher Modal           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1. Synchronized Segment-to-JSON Inspector
- **Left Column**: Interactive list of all raw X12 segments (`ISA`, `GS`, `ST`, `CLM`, `NM1`, `SV1`, `CLP`, `CAS`, `STC`, `BDS`, etc.).
- **Middle Column**: Segment Deep-Dive Card showing segment name, healthcare workflow explanation, EDI 5010 loop name, target JSON key path, and element-by-element table.
- **Right Column**: Structured JSON viewer highlighting the exact JSON object/property corresponding to the clicked segment.

### 2. Dedicated Full Raw X12 Viewer
- Line numbering, syntax highlighting, search/filter input, copy-to-clipboard, and `.x12` file download.

### 3. Dedicated Full JSON File Viewer
- Complete formatted hierarchical JSON output, search filter, copy-to-clipboard, and `.json` file download.

### 4. Consolidated Clinical Document (C-CDA) Viewer
- Dedicated visual section for 275 transactions rendering Patient Demographics, Allergies, Active Medications, Problem List / Diagnoses, Vital Signs, and Clinical Notes.

---

## 4. Workflow & Execution

When the user requests parsing or inspecting an EDI X12 transaction:

1. **Parse Input & Generate Dashboard**:
   ```bash
   python3 skills/x12-healthcare-parser/scripts/generate_visual_dashboard.py sample_data/sample_837_claim.x12 -o docs/x12_dashboard.html
   ```
2. **Review Output**:
   The script outputs both the structured JSON data and the standalone HTML dashboard.
3. **Open Dashboard**:
   Open the generated HTML dashboard in your browser:
   `docs/x12_dashboard.html`
