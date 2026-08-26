"""
Dashboard Generator Module for X12-to-JSON Parser.

Generates self-contained, interactive, responsive HTML/JS/CSS visual dashboards
for any parsed X12 healthcare transaction (837, 835, 270, 271, 277, 275, 278).
"""

import json
import os
from typing import Dict, Any, Optional, Union


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>__TITLE__ - [__TX_BADGE__]</title>
  <!-- Tailwind CSS via allowlisted CDN -->
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
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

    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: rgba(0, 0, 0, 0.05); }
    ::-webkit-scrollbar-thumb { background: rgba(100, 116, 139, 0.4); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(100, 116, 139, 0.7); }

    .badge-blue { background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }
    html.light .badge-blue { background: #eff6ff; color: #1d4ed8; border-color: #bfdbfe; }

    .badge-green { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    html.light .badge-green { background: #ecfdf5; color: #047857; border-color: #a7f3d0; }

    .badge-purple { background: rgba(168, 85, 247, 0.15); color: #c084fc; border: 1px solid rgba(168, 85, 247, 0.3); }
    html.light .badge-purple { background: #faf5ff; color: #7e22ce; border-color: #e9d5ff; }

    .badge-amber { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
    html.light .badge-amber { background: #fffbeb; color: #b45309; border-color: #fde68a; }

    .badge-rose { background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3); }
    html.light .badge-rose { background: #fff1f2; color: #be123c; border-color: #fecdd3; }

    .code-font { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
  </style>
</head>
<body class="min-h-screen p-3 md:p-6 antialiased">
  <div class="max-w-7xl mx-auto space-y-5">

    <!-- Top Header -->
    <header class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl p-4 md:p-6 shadow-sm flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
      <div class="flex items-center space-x-3">
        <div class="w-10 h-10 rounded-xl bg-blue-600/20 border border-blue-500/30 flex items-center justify-center text-blue-400">
          <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path>
          </svg>
        </div>
        <div>
          <div class="flex items-center space-x-2">
            <h1 class="text-xl font-bold text-[var(--app-foreground)] tracking-tight" id="dashboardTitle">__TITLE__</h1>
            <span class="text-xs px-2.5 py-0.5 rounded-full badge-blue font-bold" id="txBadge">__TX_BADGE__</span>
          </div>
          <p class="text-xs md:text-sm text-[var(--app-muted-foreground)]">Interactive parsed healthcare transaction dashboard & clinical inspector</p>
        </div>
      </div>

      <!-- Action Buttons & Theme Switcher -->
      <div class="flex items-center space-x-3 self-end md:self-center">
        <button onclick="openUploadModal()" class="px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm flex items-center space-x-1.5 transition-all">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"></path>
          </svg>
          <span>Parse Another X12 File</span>
        </button>

        <button id="themeToggle" class="p-2 rounded-lg bg-[var(--app-muted)] text-[var(--app-foreground)] border border-[var(--app-border)] hover:opacity-80 transition-all" title="Toggle Light/Dark Theme">
          <svg id="sunIcon" class="w-4 h-4 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path>
          </svg>
          <svg id="moonIcon" class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path>
          </svg>
        </button>
      </div>
    </header>

    <!-- Key Metrics Cards Container -->
    <div id="metricsBar" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      <!-- Dynamic Metric Cards Injected Here -->
    </div>

    <!-- Navigation Tabs -->
    <div class="border-b border-[var(--app-border)] flex space-x-2 overflow-x-auto pb-1" id="tabBar">
      <button onclick="switchTab('overview')" class="tab-btn active px-4 py-2 text-sm font-semibold border-b-2 border-blue-500 text-blue-400 whitespace-nowrap">
        📊 Transaction Details
      </button>
      <button onclick="switchTab('clinical')" id="clinicalTabBtn" class="tab-btn hidden px-4 py-2 text-sm font-semibold border-b-2 border-transparent text-[var(--app-muted-foreground)] hover:text-[var(--app-foreground)] whitespace-nowrap">
        🩺 C-CDA Clinical Payload
      </button>
      <button onclick="switchTab('json')" class="tab-btn px-4 py-2 text-sm font-semibold border-b-2 border-transparent text-[var(--app-muted-foreground)] hover:text-[var(--app-foreground)] whitespace-nowrap">
        🌳 Structured JSON
      </button>
      <button onclick="switchTab('raw_edi')" class="tab-btn px-4 py-2 text-sm font-semibold border-b-2 border-transparent text-[var(--app-muted-foreground)] hover:text-[var(--app-foreground)] whitespace-nowrap">
        📄 Raw X12 Text
      </button>
      <button onclick="switchTab('mapping_guide')" class="tab-btn px-4 py-2 text-sm font-semibold border-b-2 border-transparent text-[var(--app-muted-foreground)] hover:text-[var(--app-foreground)] whitespace-nowrap">
        📖 Field Mapping Spec
      </button>
    </div>

    <!-- TAB 1: TRANSACTION OVERVIEW & SPECIFIC DETAILS -->
    <div id="tab-overview" class="space-y-5 tab-content">
      <!-- Envelope & Interchange Header Card -->
      <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl p-5 shadow-sm space-y-4">
        <h2 class="text-sm font-bold text-[var(--app-foreground)] uppercase tracking-wider flex items-center space-x-2">
          <span class="w-2.5 h-2.5 rounded-full bg-blue-500"></span>
          <span>Interchange & Functional Group Envelopes</span>
        </h2>
        <div id="envelopeGrid" class="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
          <!-- Populated dynamically -->
        </div>
      </div>

      <!-- Business Entities Grid (Submitter, Receiver, Billing Provider, Subscriber, Patient) -->
      <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl p-5 shadow-sm space-y-4">
        <h2 class="text-sm font-bold text-[var(--app-foreground)] uppercase tracking-wider flex items-center space-x-2">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-500"></span>
          <span>Business Entities & Participants</span>
        </h2>
        <div id="entitiesGrid" class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <!-- Populated dynamically -->
        </div>
      </div>

      <!-- Transaction Specific Panel (Claims / Remittance / Status / Attachment) -->
      <div id="txSpecificPanel" class="space-y-4">
        <!-- Dynamic transaction specific tables injected here -->
      </div>
    </div>

    <!-- TAB 2: C-CDA CLINICAL PAYLOAD (IF PRESENT) -->
    <div id="tab-clinical" class="hidden space-y-5 tab-content">
      <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl p-5 shadow-sm space-y-4">
        <div class="flex items-center justify-between border-b border-[var(--app-border)] pb-3">
          <div>
            <h2 class="text-base font-bold text-purple-400" id="clinicalDocTitle">Consolidated Clinical Document (C-CDA)</h2>
            <p class="text-xs text-[var(--app-muted-foreground)]" id="clinicalDocMeta">HL7 R2.1 / R1.1 Structured XML Payload</p>
          </div>
          <span class="badge-purple px-2.5 py-1 rounded-full text-xs font-semibold">C-CDA R2.1</span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4" id="clinicalSectionsGrid">
          <!-- Clinical subsections (Allergies, Medications, Problems, Vitals, Notes) -->
        </div>
      </div>
    </div>

    <!-- TAB 3: STRUCTURED JSON TREE -->
    <div id="tab-json" class="hidden space-y-4 tab-content">
      <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl p-5 shadow-sm space-y-3">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-[var(--app-foreground)] uppercase tracking-wider">Complete Hierarchical JSON Output</span>
          <div class="flex items-center space-x-2">
            <button onclick="copyJsonOutput()" class="px-3 py-1 rounded-lg badge-green text-xs font-semibold hover:opacity-80">Copy JSON</button>
            <button onclick="downloadJsonFile()" class="px-3 py-1 rounded-lg badge-blue text-xs font-semibold hover:opacity-80">Download .json</button>
          </div>
        </div>
        <pre id="jsonTreeDisplay" class="bg-[var(--app-muted)]/40 border border-[var(--app-border)] rounded-xl p-4 code-font text-xs overflow-auto max-h-[600px] text-emerald-300"></pre>
      </div>
    </div>

    <!-- TAB 4: RAW X12 TEXT -->
    <div id="tab-raw_edi" class="hidden space-y-4 tab-content">
      <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl p-5 shadow-sm space-y-3">
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-[var(--app-foreground)] uppercase tracking-wider">Raw EDI X12 Transmission Stream</span>
          <button onclick="copyRawEdi()" class="px-3 py-1 rounded-lg badge-blue text-xs font-semibold hover:opacity-80">Copy EDI Text</button>
        </div>
        <pre id="rawEdiDisplay" class="bg-[var(--app-muted)]/40 border border-[var(--app-border)] rounded-xl p-4 code-font text-xs overflow-auto max-h-[600px] text-blue-300"></pre>
      </div>
    </div>

    <!-- TAB 5: FIELD MAPPING SPECIFICATION -->
    <div id="tab-mapping_guide" class="hidden space-y-4 tab-content">
      <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl p-5 shadow-sm space-y-4">
        <h2 class="text-sm font-bold text-[var(--app-foreground)] uppercase tracking-wider">EDI 5010 to JSON Semantic Key Reference</h2>
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="bg-[var(--app-muted)]/40 text-[var(--app-muted-foreground)] font-medium border-b border-[var(--app-border)]">
              <tr>
                <th class="p-2.5">Segment</th>
                <th class="p-2.5">JSON Field Name</th>
                <th class="p-2.5">Loop / Context</th>
                <th class="p-2.5">Healthcare Business Description</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-[var(--app-border)] text-[var(--app-foreground)]">
              <tr><td class="p-2.5 font-mono text-blue-400 font-bold">ISA</td><td class="p-2.5 font-mono text-emerald-400">interchange_control_header</td><td class="p-2.5">Interchange</td><td class="p-2.5 text-[var(--app-muted-foreground)]">Trading partner routing identifiers, delimiters, and interchange tracking number.</td></tr>
              <tr><td class="p-2.5 font-mono text-blue-400 font-bold">CLM</td><td class="p-2.5 font-mono text-emerald-400">claims[].total_claim_charge_amount</td><td class="p-2.5">Loop 2300 (837)</td><td class="p-2.5 text-[var(--app-muted-foreground)]">Submitted claim control number, total billed charges, and filing indicators.</td></tr>
              <tr><td class="p-2.5 font-mono text-blue-400 font-bold">CLP</td><td class="p-2.5 font-mono text-emerald-400">claims[].claim_payment_amount</td><td class="p-2.5">Loop 2100 (835)</td><td class="p-2.5 text-[var(--app-muted-foreground)]">Remittance claim adjudication, paid amounts, patient responsibility (copay/deductible).</td></tr>
              <tr><td class="p-2.5 font-mono text-blue-400 font-bold">CAS</td><td class="p-2.5 font-mono text-emerald-400">adjustments[].reason_code</td><td class="p-2.5">Loop 2100/2110 (835)</td><td class="p-2.5 text-[var(--app-muted-foreground)]">Contractual Obligations (CO) and CARC reason codes for claim balance reductions.</td></tr>
              <tr><td class="p-2.5 font-mono text-blue-400 font-bold">STC</td><td class="p-2.5 font-mono text-emerald-400">required_attachments[]</td><td class="p-2.5">Loop 2200D (277)</td><td class="p-2.5 text-[var(--app-muted-foreground)]">Pended claim notification with Category R0-R5 requesting clinical records.</td></tr>
              <tr><td class="p-2.5 font-mono text-purple-400 font-bold">BDS/BIN</td><td class="p-2.5 font-mono text-purple-400">attached_clinical_data</td><td class="p-2.5">Loop 2000 (275)</td><td class="p-2.5 text-[var(--app-muted-foreground)]">Embedded HL7 C-CDA XML clinical document containing meds, allergies, problems, vitals.</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- MODAL: PARSE ANOTHER X12 FILE -->
    <div id="uploadModal" class="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4 hidden">
      <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-4">
        <div class="flex items-center justify-between border-b border-[var(--app-border)] pb-3">
          <div class="flex items-center space-x-2">
            <span class="w-3 h-3 rounded-full bg-blue-500"></span>
            <h3 class="font-bold text-base text-[var(--app-foreground)]">Parse Custom EDI X12 File / Raw Text</h3>
          </div>
          <button onclick="closeUploadModal()" class="text-[var(--app-muted-foreground)] hover:text-[var(--app-foreground)] text-lg font-bold">&times;</button>
        </div>

        <div class="space-y-3">
          <!-- File Drop Zone -->
          <div id="dropZone" class="border-2 border-dashed border-[var(--app-border)] hover:border-blue-500 rounded-xl p-6 text-center cursor-pointer transition-colors bg-[var(--app-muted)]/20">
            <svg class="w-8 h-8 mx-auto text-blue-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
            </svg>
            <p class="text-xs font-semibold text-[var(--app-foreground)]">Drag & drop any .x12, .edi, or .txt file here, or <span class="text-blue-400 underline">browse</span></p>
            <p class="text-[11px] text-[var(--app-muted-foreground)] mt-1">Supports 837, 835, 270, 271, 277, 275 (C-CDA), 278 transactions</p>
            <input type="file" id="fileInput" class="hidden" accept=".x12,.edi,.txt">
          </div>

          <!-- Or Paste Raw EDI String -->
          <div>
            <label class="block text-xs font-semibold text-[var(--app-muted-foreground)] mb-1">Or paste raw EDI X12 text directly:</label>
            <textarea id="rawInputArea" rows="6" placeholder="ISA*00*          *00*          *ZZ*SUBMITTER ... ~" 
                      class="w-full bg-[var(--app-muted)]/40 text-[var(--app-foreground)] border border-[var(--app-border)] rounded-xl p-3 code-font text-xs focus:ring-1 focus:ring-blue-500 focus:outline-none"></textarea>
          </div>
        </div>

        <div class="flex items-center justify-end space-x-3 pt-2 border-t border-[var(--app-border)]">
          <button onclick="closeUploadModal()" class="px-4 py-2 rounded-lg border border-[var(--app-border)] text-xs text-[var(--app-muted-foreground)] hover:bg-[var(--app-muted)] transition-colors">Cancel</button>
          <button onclick="parseCustomX12()" class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold transition-all shadow-sm">Parse & Rebuild Dashboard</button>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <footer class="text-center text-xs text-[var(--app-muted-foreground)] pt-4 border-t border-[var(--app-border)]">
      EDI X12 (5010) & C-CDA R2.1 Real-time Parser &bull; Enterprise Canvas UI & Web Dashboard
    </footer>

  </div>

  <script>
    // Embedded Initial Parsed Data & Raw EDI Stream
    let CURRENT_DATA = __JSON_PAYLOAD__;
    let CURRENT_RAW_EDI = `__RAW_X12__`;

    function initDashboard() {
      renderMetrics(CURRENT_DATA);
      renderEnvelopes(CURRENT_DATA);
      renderEntities(CURRENT_DATA);
      renderTxSpecific(CURRENT_DATA);
      renderJsonTree(CURRENT_DATA);
      renderRawEdi(CURRENT_RAW_EDI);
    }

    function renderMetrics(data) {
      const bar = document.getElementById('metricsBar');
      bar.innerHTML = '';

      const summary = data.summary || {};
      const firstGroup = (data.functional_groups || [])[0] || {};
      const firstTx = (firstGroup.transaction_sets || [])[0] || {};
      const parsedTx = firstTx.parsed_transaction || {};
      const txType = firstTx.transaction_type || 'X12';

      // 1. Transaction Type Metric
      bar.innerHTML += `
        <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-xl p-3 flex flex-col justify-between">
          <span class="text-xs text-[var(--app-muted-foreground)] font-medium">Transaction Type</span>
          <span class="text-lg font-bold text-blue-400">${txType} ${firstTx.transaction_name || ''}</span>
          <span class="text-[11px] text-[var(--app-muted-foreground)]">Version ${firstGroup.version || '5010'}</span>
        </div>
      `;

      // 2. Total Segments Metric
      bar.innerHTML += `
        <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-xl p-3 flex flex-col justify-between">
          <span class="text-xs text-[var(--app-muted-foreground)] font-medium">Total Segments</span>
          <span class="text-lg font-bold text-[var(--app-foreground)]">${summary.total_segments_count || 0}</span>
          <span class="text-[11px] text-[var(--app-muted-foreground)]">${summary.total_transaction_sets_count || 1} Transaction Set(s)</span>
        </div>
      `;

      if (txType === '837') {
        const claims = parsedTx.claims || [];
        let totalCharge = claims.reduce((acc, c) => acc + (parseFloat(c.total_claim_charge_amount) || 0), 0);
        let totalLines = claims.reduce((acc, c) => acc + (c.service_lines || []).length, 0);

        bar.innerHTML += `
          <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-xl p-3 flex flex-col justify-between">
            <span class="text-xs text-[var(--app-muted-foreground)] font-medium">Total Claims</span>
            <span class="text-lg font-bold text-cyan-400">${claims.length}</span>
            <span class="text-[11px] text-[var(--app-muted-foreground)]">${totalLines} Service Line(s)</span>
          </div>
          <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-xl p-3 flex flex-col justify-between">
            <span class="text-xs text-[var(--app-muted-foreground)] font-medium">Total Billed Charges</span>
            <span class="text-lg font-bold text-emerald-400">$${totalCharge.toFixed(2)}</span>
            <span class="text-[11px] text-[var(--app-muted-foreground)]">Submitted Billed Total</span>
          </div>
        `;
      } else if (txType === '835') {
        const fin = parsedTx.financial_information || {};
        const claims = parsedTx.claims || [];
        bar.innerHTML += `
          <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-xl p-3 flex flex-col justify-between">
            <span class="text-xs text-[var(--app-muted-foreground)] font-medium">Payment Total</span>
            <span class="text-lg font-bold text-emerald-400">$${(parseFloat(fin.total_payment_amount) || 0).toFixed(2)}</span>
            <span class="text-[11px] text-[var(--app-muted-foreground)]">Method: ${fin.payment_method || 'ACH'}</span>
          </div>
          <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-xl p-3 flex flex-col justify-between">
            <span class="text-xs text-[var(--app-muted-foreground)] font-medium">Adjudicated Claims</span>
            <span class="text-lg font-bold text-amber-400">${claims.length}</span>
            <span class="text-[11px] text-[var(--app-muted-foreground)]">Remittance Details</span>
          </div>
        `;
      } else if (txType === '277') {
        const reqAtt = parsedTx.required_attachments || [];
        bar.innerHTML += `
          <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-xl p-3 flex flex-col justify-between">
            <span class="text-xs text-[var(--app-muted-foreground)] font-medium">Required Attachments</span>
            <span class="text-lg font-bold text-rose-400">${reqAtt.length} Flagged</span>
            <span class="text-[11px] text-[var(--app-muted-foreground)]">Action Required</span>
          </div>
        `;
      } else if (txType === '275') {
        const clin = parsedTx.attached_clinical_data || {};
        const meds = clin.medications || [];
        const allergies = clin.allergies || [];
        bar.innerHTML += `
          <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-xl p-3 flex flex-col justify-between">
            <span class="text-xs text-[var(--app-muted-foreground)] font-medium">Clinical C-CDA XML</span>
            <span class="text-lg font-bold text-purple-400">${meds.length} Meds</span>
            <span class="text-[11px] text-[var(--app-muted-foreground)]">${allergies.length} Allergies</span>
          </div>
        `;
      }
    }

    function renderEnvelopes(data) {
      const grid = document.getElementById('envelopeGrid');
      grid.innerHTML = '';
      const isa = data.interchange_control_header || {};
      const firstGroup = (data.functional_groups || [])[0] || {};
      const firstTx = (firstGroup.transaction_sets || [])[0] || {};

      const items = [
        { label: 'Sender ID (ISA06)', val: isa.interchange_sender_id || 'N/A' },
        { label: 'Receiver ID (ISA08)', val: isa.interchange_receiver_id || 'N/A' },
        { label: 'Control Number (ISA13)', val: isa.interchange_control_number || 'N/A' },
        { label: 'Interchange Date/Time', val: `${isa.interchange_date || ''} ${isa.interchange_time || ''}` },
        { label: 'Group Identifier (GS01)', val: firstGroup.functional_identifier_code || 'N/A' },
        { label: 'Group Control # (GS06)', val: firstGroup.group_control_number || 'N/A' },
        { label: 'Standard Version (GS08)', val: firstGroup.version || '005010' },
        { label: 'Set Control # (ST02)', val: firstTx.transaction_set_control_number || '0001' }
      ];

      items.forEach(it => {
        grid.innerHTML += `
          <div class="p-2.5 rounded-lg bg-[var(--app-muted)]/30 border border-[var(--app-border)]">
            <span class="text-[11px] text-[var(--app-muted-foreground)] block">${it.label}</span>
            <span class="font-mono font-semibold text-[var(--app-foreground)] truncate block">${it.val}</span>
          </div>
        `;
      });
    }

    function renderEntities(data) {
      const grid = document.getElementById('entitiesGrid');
      grid.innerHTML = '';

      const firstGroup = (data.functional_groups || [])[0] || {};
      const firstTx = (firstGroup.transaction_sets || [])[0] || {};
      const tx = firstTx.parsed_transaction || {};

      const entityKeys = [
        { title: 'Billing Provider', obj: tx.billing_provider || tx.payee || tx.service_provider, color: 'text-blue-400' },
        { title: 'Payer / Source', obj: tx.payer || tx.information_source, color: 'text-emerald-400' },
        { title: 'Subscriber / Member', obj: tx.subscriber || tx.insured, color: 'text-cyan-400' },
        { title: 'Patient', obj: tx.patient, color: 'text-purple-400' },
        { title: 'Submitter', obj: tx.submitter || tx.information_receiver, color: 'text-amber-400' }
      ];

      let count = 0;
      entityKeys.forEach(e => {
        if (e.obj && (e.obj.name_last_or_organization || e.obj.name || e.obj.identification_code)) {
          count++;
          const name = e.obj.name_last_or_organization || e.obj.name || `${e.obj.name_first || ''} ${e.obj.name_last || ''}`.trim();
          const idVal = e.obj.identification_code || 'N/A';
          const addr = e.obj.address || {};
          const geo = e.obj.geographic_location || {};
          const addrStr = addr.address_line_1 ? `${addr.address_line_1}, ${geo.city || ''} ${geo.state || ''} ${geo.postal_code || ''}` : 'Address on file';

          grid.innerHTML += `
            <div class="p-3 rounded-xl bg-[var(--app-muted)]/30 border border-[var(--app-border)] space-y-1">
              <span class="text-xs font-bold ${e.color}">${e.title}</span>
              <p class="font-semibold text-[var(--app-foreground)] truncate">${name || 'Unknown Entity'}</p>
              <p class="text-[11px] text-[var(--app-muted-foreground)] font-mono">ID: ${idVal}</p>
              <p class="text-[11px] text-[var(--app-muted-foreground)] truncate">${addrStr}</p>
            </div>
          `;
        }
      });

      if (count === 0) {
        grid.innerHTML = `<p class="text-xs text-[var(--app-muted-foreground)] col-span-3">No distinct entity loops identified in this transaction.</p>`;
      }
    }

    function renderTxSpecific(data) {
      const panel = document.getElementById('txSpecificPanel');
      panel.innerHTML = '';

      const firstGroup = (data.functional_groups || [])[0] || {};
      const firstTx = (firstGroup.transaction_sets || [])[0] || {};
      const tx = firstTx.parsed_transaction || {};
      const txType = firstTx.transaction_type;

      if (txType === '837') {
        const claims = tx.claims || [];
        let html = `
          <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl p-5 shadow-sm space-y-4">
            <h2 class="text-sm font-bold text-blue-400 uppercase tracking-wider">Submitted Health Claims & Service Lines</h2>
            <div class="space-y-4">
        `;

        claims.forEach((c, idx) => {
          const diags = (c.diagnoses || []).map(d => `<span class="badge-blue px-2 py-0.5 rounded text-[11px] font-mono">${d.diagnosis_type}: ${d.code}</span>`).join(' ');
          html += `
            <div class="border border-[var(--app-border)] rounded-xl p-4 bg-[var(--app-muted)]/20 space-y-3">
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[var(--app-border)] pb-2">
                <div>
                  <span class="font-bold text-sm text-[var(--app-foreground)]">Claim #${idx + 1}: ${c.claim_id}</span>
                  <span class="ml-2 text-xs text-[var(--app-muted-foreground)]">Date: ${c.dates && c.dates.service_date ? c.dates.service_date : 'N/A'}</span>
                </div>
                <span class="text-sm font-bold text-emerald-400 font-mono">$${(parseFloat(c.total_claim_charge_amount) || 0).toFixed(2)}</span>
              </div>
              <div>
                <span class="text-[11px] font-semibold text-[var(--app-muted-foreground)] block mb-1">Diagnoses (ICD-10):</span>
                <div class="flex flex-wrap gap-1.5">${diags || '<span class="text-xs text-[var(--app-muted-foreground)]">None</span>'}</div>
              </div>
              <div>
                <span class="text-[11px] font-semibold text-[var(--app-muted-foreground)] block mb-1">Service Lines:</span>
                <div class="overflow-x-auto">
                  <table class="w-full text-left text-xs">
                    <thead class="bg-[var(--app-muted)]/40 text-[var(--app-muted-foreground)] font-medium">
                      <tr><th class="p-2">Line #</th><th class="p-2">Procedure Code</th><th class="p-2">Charge</th><th class="p-2">Units</th></tr>
                    </thead>
                    <tbody class="divide-y divide-[var(--app-border)]">
                      ${(c.service_lines || []).map(sl => `
                        <tr>
                          <td class="p-2 font-mono">${sl.line_number}</td>
                          <td class="p-2 font-mono text-blue-400 font-bold">${(sl.procedure && (sl.procedure.procedure_code || sl.procedure.code)) || 'N/A'}</td>
                          <td class="p-2 font-mono text-emerald-400">$${(parseFloat(sl.charge_amount) || 0).toFixed(2)}</td>
                          <td class="p-2 font-mono">${sl.unit_count || 1}</td>
                        </tr>
                      `).join('')}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          `;
        });
        html += `</div></div>`;
        panel.innerHTML = html;

      }} else if (txType === '835') {
        const claims = tx.claims || [];
        let html = `
          <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl p-5 shadow-sm space-y-4">
            <h2 class="text-sm font-bold text-emerald-400 uppercase tracking-wider">Adjudicated Claims & Remittance Details</h2>
            <div class="space-y-4">
        `;
        claims.forEach((c, idx) => {
          html += `
            <div class="border border-[var(--app-border)] rounded-xl p-4 bg-[var(--app-muted)]/20 space-y-3">
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[var(--app-border)] pb-2">
                <div>
                  <span class="font-bold text-sm text-[var(--app-foreground)]">Claim: ${c.patient_control_number}</span>
                  <span class="ml-2 badge-green px-2 py-0.5 rounded text-[11px]">${c.claim_status_description || 'Processed'}</span>
                </div>
                <div class="text-right">
                  <span class="text-xs text-[var(--app-muted-foreground)]">Paid: </span>
                  <span class="text-sm font-bold text-emerald-400 font-mono">$${(parseFloat(c.claim_payment_amount) || 0).toFixed(2)}</span>
                </div>
              </div>
              <div class="grid grid-cols-2 md:grid-cols-3 gap-2 text-xs">
                <div><span class="text-[11px] text-[var(--app-muted-foreground)]">Submitted Charge:</span> <span class="font-mono text-[var(--app-foreground)]">$${(parseFloat(c.total_claim_charge_amount) || 0).toFixed(2)}</span></div>
                <div><span class="text-[11px] text-[var(--app-muted-foreground)]">Patient Responsibility:</span> <span class="font-mono text-amber-400">$${(parseFloat(c.patient_responsibility_amount) || 0).toFixed(2)}</span></div>
                <div><span class="text-[11px] text-[var(--app-muted-foreground)]">Payer Claim #:</span> <span class="font-mono text-[var(--app-foreground)]">${c.payer_claim_control_number || 'N/A'}</span></div>
              </div>
            </div>
          `;
        });
        html += `</div></div>`;
        panel.innerHTML = html;

      }} else if (txType === '277') {
        const reqAtt = tx.required_attachments || [];
        let html = `
          <div class="bg-[var(--app-card)] border border-[var(--app-border)] rounded-2xl p-5 shadow-sm space-y-4">
            <h2 class="text-sm font-bold text-rose-400 uppercase tracking-wider">Required Documentation & Status Notifications</h2>
            <div class="space-y-3">
        `;
        reqAtt.forEach(a => {
          html += `
            <div class="border border-rose-500/30 rounded-xl p-4 bg-rose-500/10 space-y-2">
              <div class="flex items-center justify-between">
                <span class="font-bold text-sm text-rose-400">${a.attachment_report_type_description || a.status_category_description || 'Documentation Required'}</span>
                <span class="badge-rose px-2 py-0.5 rounded text-xs font-mono">Code: ${a.attachment_report_type_code || a.status_category_code}</span>
              </div>
              <p class="text-xs text-[var(--app-foreground)]">Transmission Method: <code class="badge-blue px-1 rounded">${a.attachment_transmission_code || 'Electronic (EL)'}</code> &bull; Action: ${a.action_description || 'Pended / Action Required'}</p>
            </div>
          `;
        });
        html += `</div></div>`;
        panel.innerHTML = html;

      }} else if (txType === '275' || tx.attached_clinical_data) {
        renderClinicalTab(tx.attached_clinical_data);
      }
    }

    function renderClinicalTab(clin) {
      if (!clin || Object.keys(clin).length === 0) return;
      document.getElementById('clinicalTabBtn').classList.remove('hidden');

      const meta = clin.document_metadata || {};
      const pt = clin.patient_demographics || {};
      document.getElementById('clinicalDocTitle').textContent = meta.title || 'Clinical Document';
      document.getElementById('clinicalDocMeta').textContent = `Patient: ${(pt.name && pt.name.full_name) || 'N/A'} | Date: ${meta.effective_date || 'N/A'}`;

      const grid = document.getElementById('clinicalSectionsGrid');
      const meds = clin.medications || [];
      const allergies = clin.allergies || [];
      const probs = clin.problems_and_diagnoses || [];
      const notes = (clin.clinical_notes_and_evaluations && (clin.clinical_notes_and_evaluations.progress_note_medical_necessity_evaluation || clin.clinical_notes_and_evaluations.assessment_and_plan)) || 'No narrative note provided.';

      grid.innerHTML = `
        <!-- Medications -->
        <div class="p-4 rounded-xl bg-[var(--app-muted)]/20 border border-[var(--app-border)] space-y-2">
          <span class="font-bold text-xs text-purple-400 uppercase">Medications (${meds.length})</span>
          <div class="space-y-1.5 max-h-48 overflow-y-auto">
            ${meds.map(m => `<div class="text-xs p-1.5 rounded bg-[var(--app-muted)]/30"><span class="font-semibold text-[var(--app-foreground)]">${m.medication_name}</span> <span class="badge-purple text-[10px] px-1 rounded">${m.rxnorm_code || 'RxNorm'}</span></div>`).join('') || '<p class="text-xs text-[var(--app-muted-foreground)]">None recorded</p>'}
          </div>
        </div>

        <!-- Allergies -->
        <div class="p-4 rounded-xl bg-[var(--app-muted)]/20 border border-[var(--app-border)] space-y-2">
          <span class="font-bold text-xs text-rose-400 uppercase">Allergies (${allergies.length})</span>
          <div class="space-y-1.5 max-h-48 overflow-y-auto">
            ${allergies.map(a => `<div class="text-xs p-1.5 rounded bg-[var(--app-muted)]/30"><span class="font-semibold text-[var(--app-foreground)]">${a.substance}</span> - <span class="text-rose-400">${a.reaction || 'Adverse reaction'} (${a.severity || 'Moderate'})</span></div>`).join('') || '<p class="text-xs text-[var(--app-muted-foreground)]">None recorded</p>'}
          </div>
        </div>

        <!-- Problems & Diagnoses -->
        <div class="p-4 rounded-xl bg-[var(--app-muted)]/20 border border-[var(--app-border)] space-y-2">
          <span class="font-bold text-xs text-cyan-400 uppercase">Problems & Diagnoses (${probs.length})</span>
          <div class="space-y-1.5 max-h-48 overflow-y-auto">
            ${probs.map(p => `<div class="text-xs p-1.5 rounded bg-[var(--app-muted)]/30"><span class="font-semibold text-[var(--app-foreground)]">${p.problem_name}</span> <span class="badge-blue text-[10px] px-1 rounded">${p.code}</span></div>`).join('') || '<p class="text-xs text-[var(--app-muted-foreground)]">None recorded</p>'}
          </div>
        </div>

        <!-- Clinical Notes -->
        <div class="p-4 rounded-xl bg-[var(--app-muted)]/20 border border-[var(--app-border)] space-y-2">
          <span class="font-bold text-xs text-amber-400 uppercase">Clinical Notes & Justification</span>
          <p class="text-xs text-[var(--app-foreground)] leading-relaxed italic bg-[var(--app-muted)]/30 p-2.5 rounded-lg max-h-48 overflow-y-auto">
            ${notes}
          </p>
        </div>
      `;
    }

    function renderJsonTree(data) {
      document.getElementById('jsonTreeDisplay').textContent = JSON.stringify(data, null, 2);
    }

    function renderRawEdi(raw) {
      document.getElementById('rawEdiDisplay').textContent = raw || 'No raw EDI text supplied.';
    }

    function copyJsonOutput() {
      navigator.clipboard.writeText(document.getElementById('jsonTreeDisplay').textContent).then(() => alert('JSON copied to clipboard!'));
    }

    function downloadJsonFile() {
      const blob = new Blob([document.getElementById('jsonTreeDisplay').textContent], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'parsed_x12_output.json';
      a.click();
    }

    function copyRawEdi() {
      navigator.clipboard.writeText(document.getElementById('rawEdiDisplay').textContent).then(() => alert('Raw EDI copied to clipboard!'));
    }

    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active', 'border-blue-500', 'text-blue-400');
        btn.classList.add('border-transparent', 'text-[var(--app-muted-foreground)]');
      });
      event.currentTarget.classList.add('active', 'border-blue-500', 'text-blue-400');
      event.currentTarget.classList.remove('border-transparent', 'text-[var(--app-muted-foreground)]');

      document.querySelectorAll('.tab-content').forEach(c => c.classList.add('hidden'));
      const target = document.getElementById(`tab-${tabId}`);
      if (target) target.classList.remove('hidden');
    }

    function openUploadModal() {
      document.getElementById('uploadModal').classList.remove('hidden');
    }

    function closeUploadModal() {
      document.getElementById('uploadModal').classList.add('hidden');
    }

    // Theme Toggle Handler
    const themeToggleBtn = document.getElementById('themeToggle');
    const sunIcon = document.getElementById('sunIcon');
    const moonIcon = document.getElementById('moonIcon');

    themeToggleBtn.addEventListener('click', () => {
      const html = document.documentElement;
      if (html.classList.contains('light')) {
        html.classList.remove('light');
        html.classList.add('dark');
        sunIcon.classList.add('hidden');
        moonIcon.classList.remove('hidden');
      } else {
        html.classList.remove('dark');
        html.classList.add('light');
        moonIcon.classList.add('hidden');
        sunIcon.classList.remove('hidden');
      }
    });

    // Drag and Drop & File Upload handling
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');

    dropZone.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (re) => {
          document.getElementById('rawInputArea').value = re.target.result;
        };
        reader.readAsText(file);
      }
    });

    // Parse custom X12 text entered by user (via API or Client-side stream parsing)
    async function parseCustomX12() {
      const rawText = document.getElementById('rawInputArea').value.trim();
      if (!rawText) {
        alert('Please select a file or paste raw X12 content.');
        return;
      }

      try {
        // Try posting to local server if running
        const resp = await fetch('/v1/parse/x12', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ raw_x12: rawText })
        });

        if (resp.ok) {
          const parsed = await resp.json();
          CURRENT_DATA = parsed;
          CURRENT_RAW_EDI = rawText;
          initDashboard();
          closeUploadModal();
          switchTab('overview');
          return;
        }
      } catch (err) {
        console.warn('Backend server not directly reachable, attempting local stream fallback.', err);
      }

      alert('File loaded. For complete server-side parsing, ensure server is running: python3 -m x12_parser.api.server');
      closeUploadModal();
    }

    // Auto-detect system theme
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
      moonIcon.classList.add('hidden');
      sunIcon.classList.remove('hidden');
    }

    initDashboard();
  </script>
</body>
</html>
"""


def generate_html_dashboard(
    parsed_data: Dict[str, Any],
    raw_x12: str = "",
    title: str = "EDI X12 Parsed Transaction Dashboard"
) -> str:
    """
    Generate a complete, standalone HTML visual dashboard for any parsed X12 dataset.
    """
    json_payload = json.dumps(parsed_data, indent=2, default=str)
    raw_x12_clean = raw_x12.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    
    # Identify transaction types present
    tx_types = []
    for g in parsed_data.get("functional_groups", []):
        for tx in g.get("transaction_sets", []):
            tt = tx.get("transaction_type", "")
            if tt and tt not in tx_types:
                tx_types.append(tt)
    tx_badge = ", ".join(tx_types) if tx_types else "X12 5010"

    html = HTML_TEMPLATE.replace("__TITLE__", title)
    html = html.replace("__TX_BADGE__", tx_badge)
    html = html.replace("__JSON_PAYLOAD__", json_payload)
    html = html.replace("__RAW_X12__", raw_x12_clean)

    return html


def save_html_dashboard(
    parsed_data: Dict[str, Any],
    output_path: str,
    raw_x12: str = "",
    title: str = "EDI X12 Parsed Transaction Dashboard"
) -> str:
    """Generate and save HTML dashboard to specified filepath."""
    html_content = generate_html_dashboard(parsed_data, raw_x12=raw_x12, title=title)
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    return output_path
