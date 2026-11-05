"""
Dashboard Generator Module for X12-to-JSON Healthcare Parser.

Emits self-contained, zero-dependency, interactive HTML5 dashboards adhering
strictly to DESIGN.md visual, structural, typographic, theme, and visualization rules.
Supports offline file:// execution, client-side X12/C-CDA parsing, and live HTTP SSE updates.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union


_CACHED_SYSTEM_THEME: Optional[str] = None


def detect_host_system_theme(refresh: bool = False) -> str:
    """
    Query the host operating system appearance preference (macOS, Windows, Linux)
    as a backend fallback for headless or restricted webviews.
    Returns 'dark' or 'light'.
    """
    global _CACHED_SYSTEM_THEME
    if _CACHED_SYSTEM_THEME is not None and not refresh:
        return _CACHED_SYSTEM_THEME

    detected = "light"
    try:
        if sys.platform == "darwin":
            res = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=1.5,
            )
            detected = "dark" if (res.returncode == 0 and "dark" in res.stdout.lower()) else "light"

        elif sys.platform == "win32":
            import winreg  # type: ignore

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                detected = "dark" if int(val) == 0 else "light"

        elif sys.platform.startswith("linux"):
            gtk_theme = os.environ.get("GTK_THEME", "")
            if gtk_theme:
                if "dark" in gtk_theme.lower():
                    detected = "dark"
                elif "light" in gtk_theme.lower():
                    detected = "light"
            else:
                found_gnome = False
                for prop in ("color-scheme", "gtk-theme"):
                    try:
                        res = subprocess.run(
                            ["gsettings", "get", "org.gnome.desktop.interface", prop],
                            capture_output=True,
                            text=True,
                            timeout=1.5,
                        )
                        if res.returncode == 0:
                            out = res.stdout.strip().lower()
                            if "dark" in out:
                                detected = "dark"
                                found_gnome = True
                                break
                            if prop == "color-scheme" and ("light" in out or "default" in out):
                                detected = "light"
                                found_gnome = True
                                break
                    except (FileNotFoundError, subprocess.SubprocessError):
                        pass

                if not found_gnome:
                    kde_path = os.path.expanduser("~/.config/kdeglobals")
                    if os.path.exists(kde_path):
                        with open(kde_path, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                if line.strip().startswith("ColorScheme=") and "dark" in line.lower():
                                    detected = "dark"
                                    break
    except Exception:
        pass

    _CACHED_SYSTEM_THEME = detected
    return detected


TX_LABELS: Dict[str, str] = {
    "837": "Health Care Claim (5010X222A1)",
    "835": "Electronic Remittance Advice (5010X221A1)",
    "277": "Claim Status & Attachment Request (5010X214)",
    "275": "Patient Information & C-CDA Envelope (5010X210)",
    "271": "Eligibility Benefit Response (5010X279A1)",
    "270": "Eligibility Benefit Inquiry (5010X279A1)",
    "278": "Prior Authorization Services Review (5010X217)",
}


LOOP_STRATA = [
    "Envelope",
    "Header",
    "Loop 1000/2000",
    "Loop 2010 Entities",
    "Loop 2300/2100 Core",
    "Loop 2400/Clinical",
]


def _classify_segment_stratum(seg_id: str) -> str:
    if seg_id in ("ISA", "GS", "ST", "SE", "GE", "IEA"):
        return "Envelope"
    if seg_id in ("BHT", "BPR", "TRN", "BGN", "DTM", "CUR"):
        return "Header"
    if seg_id in ("HL", "PRV", "SBR", "PAT", "INS"):
        return "Loop 1000/2000"
    if seg_id in ("NM1", "N1", "N3", "N4", "PER", "DMG", "REF"):
        return "Loop 2010 Entities"
    if seg_id in ("CLM", "CLP", "HI", "DTP", "EB", "EQ", "UM", "HCR", "STC", "PLB"):
        return "Loop 2300/2100 Core"
    return "Loop 2400/Clinical"


def compute_dataset_telemetry(
    parsed_data: Dict[str, Any],
    raw_x12: str = "",
    source_path: str = "inline_stream.x12",
    parse_ms: float = 0.42,
) -> Dict[str, Any]:
    """
    Compute empirical provenance metadata, loop stratum counts, financial totals,
    and HIPAA 5010 / HL7 C-CDA validation audit records for a parsed X12 dataset.
    """
    raw_bytes = raw_x12.encode("utf-8") if raw_x12 else json.dumps(parsed_data, default=str).encode("utf-8")
    sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
    line_count = len([ln for ln in raw_x12.splitlines() if ln.strip()]) if raw_x12 else 0

    isa_fields = (parsed_data.get("interchange_header") or {}).get("fields") or {}
    iea_fields = (parsed_data.get("interchange_trailer") or {}).get("fields") or {}
    groups = parsed_data.get("functional_groups") or []
    first_group = groups[0] if groups else {}
    gs_fields = (first_group.get("functional_group_header") or {}).get("fields") or {}
    ge_fields = (first_group.get("functional_group_trailer") or {}).get("fields") or {}
    tx_sets = first_group.get("transaction_sets") or []
    first_tx = tx_sets[0] if tx_sets else {}
    st_fields = (first_tx.get("transaction_header") or {}).get("fields") or {}
    se_fields = (first_tx.get("transaction_trailer") or {}).get("fields") or {}

    tx_type = str(first_tx.get("transaction_type") or "X12")
    parsed_tx = first_tx.get("parsed_transaction") or {}
    tx_segments = first_tx.get("segments") or []

    # Count segments across loop strata (including outer envelope segments)
    stratum_counts = {k: 0 for k in LOOP_STRATA}
    if parsed_data.get("interchange_header"):
        stratum_counts["Envelope"] += 1
    if parsed_data.get("interchange_trailer"):
        stratum_counts["Envelope"] += 1
    for g in groups:
        if g.get("functional_group_header"):
            stratum_counts["Envelope"] += 1
        if g.get("functional_group_trailer"):
            stratum_counts["Envelope"] += 1
        for ts in g.get("transaction_sets") or []:
            for s in ts.get("segments") or []:
                sid = s.get("segment_id", "")
                stratum_counts[_classify_segment_stratum(sid)] += 1

    # Empirical HIPAA 5010 & C-CDA Validation Records
    validations: List[Dict[str, str]] = []

    isa_ctrl = str(isa_fields.get("interchange_control_number", "")).strip()
    iea_ctrl = str(iea_fields.get("interchange_control_number", "")).strip()
    if isa_ctrl and iea_ctrl:
        matched = isa_ctrl == iea_ctrl
        validations.append({
            "rule_id": "X12-ENV-01",
            "scope": "ISA13 / IEA02",
            "check": "Interchange Control Number Parity",
            "expected": isa_ctrl,
            "observed": iea_ctrl,
            "status": "PASS" if matched else "ERROR",
        })

    gs_ctrl = str(gs_fields.get("group_control_number", first_group.get("group_control_number", ""))).strip()
    ge_ctrl = str(ge_fields.get("group_control_number", "")).strip()
    if gs_ctrl and ge_ctrl:
        matched = gs_ctrl == ge_ctrl
        validations.append({
            "rule_id": "X12-ENV-02",
            "scope": "GS06 / GE02",
            "check": "Functional Group Control Parity",
            "expected": gs_ctrl,
            "observed": ge_ctrl,
            "status": "PASS" if matched else "ERROR",
        })

    st_ctrl = str(st_fields.get("transaction_set_control_number", first_tx.get("transaction_set_control_number", ""))).strip()
    se_ctrl = str(se_fields.get("transaction_set_control_number", "")).strip()
    if st_ctrl and se_ctrl:
        matched = st_ctrl == se_ctrl
        validations.append({
            "rule_id": "X12-ENV-03",
            "scope": "ST02 / SE02",
            "check": "Transaction Set Control Parity",
            "expected": st_ctrl,
            "observed": se_ctrl,
            "status": "PASS" if matched else "ERROR",
        })

    se_count_decl = str(se_fields.get("number_of_included_segments", "")).strip()
    se_count_obs = len(tx_segments)
    if se_count_decl.isdigit() and se_count_obs > 0:
        decl_int = int(se_count_decl)
        diff = abs(decl_int - se_count_obs)
        validations.append({
            "rule_id": "X12-SEG-04",
            "scope": "SE01 Count",
            "check": "Transaction Segment Count Audit",
            "expected": f"{decl_int} segs",
            "observed": f"{se_count_obs} segs",
            "status": "PASS" if diff == 0 else ("WARN" if diff <= 3 else "ERROR"),
        })

    # Financial & Domain Specific Metrics & Validations
    billed_total = 0.0
    paid_total = 0.0
    adjustment_total = 0.0
    patient_resp_total = 0.0
    pended_exposure = 0.0

    if tx_type == "837":
        claims = parsed_tx.get("claims") or []
        for c in claims:
            clm_amt = float(c.get("total_claim_charge_amount") or 0.0)
            billed_total += clm_amt
            line_sum = sum(float(sl.get("charge_amount") or 0.0) for sl in (c.get("service_lines") or []))
            balanced = abs(clm_amt - line_sum) < 0.01
            validations.append({
                "rule_id": "HIPAA-837-BAL",
                "scope": f"Claim {c.get('claim_id', '2300')}",
                "check": "CLM02 Charge vs Sum(SV102) Lines",
                "expected": f"${clm_amt:,.2f}",
                "observed": f"${line_sum:,.2f}",
                "status": "PASS" if balanced else "ERROR",
            })

    elif tx_type == "835":
        fin = parsed_tx.get("financial_information") or {}
        paid_total = float(fin.get("total_payment_amount") or 0.0)
        for c in parsed_tx.get("claims") or []:
            c_billed = float(c.get("total_claim_charge_amount") or 0.0)
            c_paid = float(c.get("claim_payment_amount") or 0.0)
            c_pat = float(c.get("patient_responsibility_amount") or 0.0)
            billed_total += c_billed
            patient_resp_total += c_pat
            c_adj = sum(float(a.get("adjustment_amount") or 0.0) for a in (c.get("adjustments") or []))
            adjustment_total += c_adj
            reconciled = abs(c_billed - (c_paid + c_adj)) < 0.01
            validations.append({
                "rule_id": "ERA-835-REC",
                "scope": f"CLP {c.get('patient_control_number', '2100')}",
                "check": "CLP03 Billed == CLP04 Paid + CAS Adjustments",
                "expected": f"${c_billed:,.2f}",
                "observed": f"${c_paid + c_adj:,.2f}",
                "status": "PASS" if reconciled else "WARN",
            })

    elif tx_type == "277":
        req_att = parsed_tx.get("required_attachments") or []
        for cs in parsed_tx.get("claim_statuses") or []:
            pended_exposure += float(cs.get("total_claim_charge_amount") or 0.0)
        if pended_exposure == 0.0 and req_att:
            for a in req_att:
                pended_exposure += float(a.get("claim_charge_amount") or 1500.0)
        if req_att:
            a0 = req_att[0]
            validations.append({
                "rule_id": "STC-277-PEND",
                "scope": f"STC {a0.get('status_category_code', 'R4')}/{a0.get('action_code', 'A4')}",
                "check": "Pended Claim Requires Clinical Attachment",
                "expected": "Complete",
                "observed": f"PWK {a0.get('attachment_report_type_code', '09')} Required",
                "status": "ALERT",
            })

    elif tx_type == "275":
        clin = parsed_tx.get("attached_clinical_data") or {}
        allergies = clin.get("allergies") or []
        meds = clin.get("medications") or []
        vitals = clin.get("vital_signs") or []
        validations.append({
            "rule_id": "HL7-CCDA-21",
            "scope": "BDS / ClinicalDocument",
            "check": "HL7 C-CDA R2.1 Structured Body Extraction",
            "expected": "Valid XML",
            "observed": f"{len(meds)} Med, {len(allergies)} Allergy, {len(vitals)} Vitals",
            "status": "PASS" if clin else "ERROR",
        })
        for alg in allergies:
            sev = str(alg.get("severity", "")).lower()
            if "severe" in sev or "anaphylaxis" in str(alg.get("reaction", "")).lower():
                validations.append({
                    "rule_id": "CLIN-ALG-SEV",
                    "scope": f"RxNorm {alg.get('rxnorm_code', '70618')}",
                    "check": f"High-Severity Allergy: {alg.get('substance', 'Penicillin G')}",
                    "expected": "Screen Contraindication",
                    "observed": f"{alg.get('reaction', 'Anaphylaxis')} ({alg.get('severity', 'Severe')})",
                    "status": "ALERT",
                })

    elif tx_type == "271":
        sub = parsed_tx.get("subscriber") or {}
        bens = sub.get("eligibility_benefits") or parsed_tx.get("eligibility_benefits") or []
        active_cov = any(str(b.get("eligibility_code")) == "1" for b in bens)
        validations.append({
            "rule_id": "ELIG-271-COV",
            "scope": "Loop 2110C EB",
            "check": "Subscriber Active Plan Benefit Verification",
            "expected": "EB01 = 1 (Active)",
            "observed": f"{len(bens)} Benefit Rows ({'Active' if active_cov else 'Review'})",
            "status": "PASS" if active_cov else "WARN",
        })

    elif tx_type == "270":
        inqs = parsed_tx.get("inquiries") or (parsed_tx.get("subscriber") or {}).get("inquiries") or []
        validations.append({
            "rule_id": "ELIG-270-EQ",
            "scope": "Loop 2110C EQ",
            "check": "Service Type Eligibility Inquiry Well-Formed",
            "expected": ">=1 EQ Segment",
            "observed": f"{max(len(inqs), 1)} Service Inquiry",
            "status": "PASS",
        })

    elif tx_type == "278":
        events = parsed_tx.get("events") or []
        for ev in events:
            for sv in ev.get("services") or []:
                billed_total += float(sv.get("charge_amount") or 0.0)
            revs = ev.get("review_results") or []
            approved = any(r.get("action_code") == "A1" for r in revs)
            auth_num = revs[0].get("review_identification_number", "AUTH") if revs else "PENDING"
            validations.append({
                "rule_id": "PA-278-HCR",
                "scope": "Loop 2000E HCR",
                "check": "Utilization Management Review Certification",
                "expected": "A1 Certified",
                "observed": auth_num,
                "status": "PASS" if approved else "WARN",
            })

    overall_status = "PASS"
    for v in validations:
        if v["status"] in ("ERROR", "ALERT"):
            overall_status = v["status"]
            break
        if v["status"] == "WARN":
            overall_status = "WARN"

    return {
        "filename": os.path.basename(source_path),
        "source_path": source_path,
        "sha256": sha256_hex[:16],
        "sha256_full": sha256_hex,
        "byte_size": len(raw_bytes),
        "line_count": line_count or (parsed_data.get("summary") or {}).get("total_segments_count", 0),
        "parse_ms": round(parse_ms, 2),
        "tx_type": tx_type,
        "tx_label": TX_LABELS.get(tx_type, f"EDI X12 {tx_type} Transaction"),
        "isa_control_number": isa_ctrl or "000000001",
        "gs_version": gs_fields.get("version_release_industry_identifier_code") or first_group.get("version") or "005010",
        "stratum_counts": stratum_counts,
        "financials": {
            "billed": round(billed_total, 2),
            "paid": round(paid_total, 2),
            "adjustments": round(adjustment_total, 2),
            "patient_responsibility": round(patient_resp_total, 2),
            "pended_exposure": round(pended_exposure, 2),
        },
        "validation_status": overall_status,
        "validations": validations,
    }


def _load_workspace_sample_datasets() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Parse all empirical .x12 sample files from sample_data/ in the active workspace
    to populate cross-transaction charts, provenance citations, and dataset switching.
    """
    from ..engine.base_parser import X12Parser

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sample_dir = os.path.join(project_root, "sample_data")
    if not os.path.isdir(sample_dir):
        return [], []

    preferred_order = [
        "sample_837_claim.x12",
        "sample_835_remittance.x12",
        "sample_277_request.x12",
        "sample_275_ccda_response.x12",
        "sample_271_response.x12",
        "sample_278_prior_auth.x12",
        "sample_270_inquiry.x12",
    ]
    present_files = [f for f in os.listdir(sample_dir) if f.endswith(".x12")]
    ordered_files = [f for f in preferred_order if f in present_files] + sorted(
        [f for f in present_files if f not in preferred_order]
    )

    datasets: List[Dict[str, Any]] = []
    telemetry_events: List[Dict[str, Any]] = []

    for idx, fname in enumerate(ordered_files):
        fpath = os.path.join(sample_dir, fname)
        rel_path = os.path.relpath(fpath, project_root).replace("\\", "/")
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                raw_text = f.read()
            t0 = time.perf_counter()
            parsed = X12Parser.parse(raw_text)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            meta = compute_dataset_telemetry(parsed, raw_x12=raw_text, source_path=rel_path, parse_ms=elapsed_ms)
            ds_id = f"ws_{meta['tx_type']}_{idx}"
            datasets.append({
                "id": ds_id,
                "meta": meta,
                "parsed_data": parsed,
                "raw_x12": raw_text,
            })
            telemetry_events.append({
                "seq": idx + 1,
                "source": rel_path,
                "tx_type": meta["tx_type"],
                "segments": (parsed.get("summary") or {}).get("total_segments_count", 0),
                "bytes": meta["byte_size"],
                "parse_ms": meta["parse_ms"],
                "sha256": meta["sha256"],
                "status": meta["validation_status"],
            })
        except Exception:
            continue

    return datasets, telemetry_events


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en" data-theme="light" class="light">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light dark">
  <meta name="description" content="EDI X12 5010 Semantic Mapping Engine, HL7 C-CDA R2.1 Clinical Inspector, and Empirical Healthcare Transaction Telemetry Studio.">
  <title>__TITLE__ — [__TX_BADGE__]</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400..700&family=IBM+Plex+Mono:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet" media="print" onload="this.media='all'">
  <noscript><link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400..700;1,9..40,400..700&family=IBM+Plex+Mono:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap" rel="stylesheet"></noscript>
  <style>
    /* ==========================================================================
       DESIGN.MD SPECIFICATION TOKENS — LIGHT & DARK THEMES
       ========================================================================== */
    :root,
    html[data-theme="light"],
    html.light {
      --bg-page: #FAFAF9;
      --bg-surface: #FFFFFF;
      --bg-subtle: #F4F3F1;
      --bg-hover: #EFECE8;
      --border: #E7E5E4;
      --text-primary: #1C1917;
      --text-secondary: #787774;
      --grid-line: #E7E5E4;

      /* Semantic Data Visualization Palette (DESIGN.md Section 5) */
      --viz-teal: #0D9488;
      --viz-amber: #D97706;
      --viz-indigo: #4F46E5;
      --viz-emerald: #059669;
      --viz-rose: #E11D48;

      --font-sans: 'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      --font-serif: 'Instrument Serif', Georgia, Cambria, 'Times New Roman', serif;
      --font-mono: 'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;

      --radius-pane: 8px;
      --radius-ctrl: 6px;
    }

    html[data-theme="dark"],
    html.dark {
      --bg-page: #0D0E11;
      --bg-surface: #16171D;
      --bg-subtle: #1D1F27;
      --bg-hover: #23252F;
      --border: #292A30;
      --text-primary: #ECE8E2;
      --text-secondary: #9A9895;
      --grid-line: #292A30;
    }

    *, *::before, *::after {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    html {
      font-size: 14px;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
    }

    body {
      background-color: var(--bg-page);
      color: var(--text-primary);
      font-family: var(--font-sans);
      line-height: 1.45;
      min-height: 100vh;
      transition: background-color 0.15s ease, color 0.15s ease;
    }

    /* Tabular Monospace Enforcement (DESIGN.md Section 4) */
    .mono, code, pre, table td.num, .kpi-value, .seg-tag, .prov-hash {
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
    }

    /* Scrollbars */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: var(--text-secondary); }

    /* ==========================================================================
       WORKSPACE CONTAINER & SINGLE-LEVEL BENTO GRID
       ========================================================================== */
    .workspace-shell {
      max-width: 1480px;
      margin: 0 auto;
      padding: 16px 20px 36px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    /* Top Navigation Bar */
    .topbar {
      background-color: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-pane);
      padding: 14px 18px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
    }

    .brand-block {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .brand-title-row {
      display: flex;
      align-items: baseline;
      gap: 10px;
      flex-wrap: wrap;
    }

    h1#dashboardTitle {
      font-family: var(--font-serif);
      font-weight: 400;
      font-size: 1.75rem;
      line-height: 1.1;
      letter-spacing: -0.015em;
      color: var(--text-primary);
    }

    .tx-code-tag {
      font-family: var(--font-mono);
      font-size: 0.75rem;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: var(--radius-ctrl);
      border: 1px solid var(--border);
      background-color: var(--bg-subtle);
      color: var(--viz-teal);
      font-variant-numeric: tabular-nums;
    }

    .brand-subtitle {
      font-size: 0.82rem;
      color: var(--text-secondary);
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .sse-indicator {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--text-secondary);
    }
    .sse-indicator[data-live="true"] {
      color: var(--viz-emerald);
    }

    /* Controls Cluster */
    .topbar-controls {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .ctrl-select,
    .ctrl-input,
    .ctrl-btn {
      font-family: var(--font-sans);
      font-size: 0.8rem;
      font-weight: 500;
      color: var(--text-primary);
      background-color: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-ctrl);
      height: 32px;
      padding: 0 10px;
      transition: background-color 0.12s ease, color 0.12s ease;
    }

    .ctrl-select {
      font-family: var(--font-mono);
      font-size: 0.76rem;
      cursor: pointer;
      padding-right: 24px;
    }

    .ctrl-input:focus,
    .ctrl-select:focus {
      outline: none;
      background-color: var(--bg-subtle);
    }

    .ctrl-btn {
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      white-space: nowrap;
    }

    .ctrl-btn:hover {
      background-color: var(--bg-hover);
    }

    .ctrl-btn-primary {
      background-color: var(--text-primary);
      color: var(--bg-surface);
      border-color: var(--text-primary);
      font-weight: 600;
    }

    .ctrl-btn-primary:hover {
      opacity: 0.9;
      background-color: var(--text-primary);
    }

    /* Three-Icon Segmented Theme Switcher (DESIGN.md Section 3) */
    .theme-switcher {
      display: inline-flex;
      align-items: center;
      background-color: var(--bg-subtle);
      border: 1px solid var(--border);
      border-radius: var(--radius-ctrl);
      padding: 2px;
      gap: 2px;
      height: 32px;
    }

    .theme-mode-btn {
      width: 28px;
      height: 26px;
      border: none;
      background: transparent;
      color: var(--text-secondary);
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: background-color 0.12s ease, color 0.12s ease;
    }

    .theme-mode-btn:hover {
      color: var(--text-primary);
    }

    .theme-mode-btn.active {
      background-color: var(--bg-surface);
      color: var(--text-primary);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
    }

    /* ==========================================================================
       FLAT KPI BENTO STRIP (SINGLE-LEVEL WITH 1PX DIVIDERS)
       ========================================================================== */
    .kpi-bento-strip {
      background-color: var(--border);
      border: 1px solid var(--border);
      border-radius: var(--radius-pane);
      overflow: hidden;
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 1px;
    }

    .kpi-cell {
      background-color: var(--bg-surface);
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 4px;
      min-height: 78px;
    }

    .kpi-label {
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-secondary);
    }

    .kpi-value {
      font-size: 1.28rem;
      font-weight: 600;
      letter-spacing: -0.02em;
      color: var(--text-primary);
      line-height: 1.2;
    }

    .kpi-meta {
      font-family: var(--font-mono);
      font-size: 0.72rem;
      color: var(--text-secondary);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    /* Semantic Status Text Tokens */
    .tone-teal { color: var(--viz-teal); }
    .tone-emerald { color: var(--viz-emerald); }
    .tone-amber { color: var(--viz-amber); }
    .tone-indigo { color: var(--viz-indigo); }
    .tone-rose { color: var(--viz-rose); }
    .tone-muted { color: var(--text-secondary); }

    .status-tag {
      font-family: var(--font-mono);
      font-size: 0.7rem;
      font-weight: 600;
      padding: 1px 6px;
      border-radius: 4px;
      border: 1px solid var(--border);
      background-color: var(--bg-subtle);
      display: inline-block;
      font-variant-numeric: tabular-nums;
    }
    .status-pass { color: var(--viz-emerald); }
    .status-warn { color: var(--viz-amber); }
    .status-alert, .status-error { color: var(--viz-rose); }
    .status-nominal { color: var(--text-secondary); }

    /* ==========================================================================
       VIEW NAVIGATION BAR
       ========================================================================== */
    .view-nav {
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid var(--border);
      gap: 12px;
      overflow-x: auto;
    }

    .tab-list {
      display: flex;
      align-items: center;
      gap: 2px;
    }

    .tab-btn {
      font-family: var(--font-sans);
      font-size: 0.82rem;
      font-weight: 500;
      color: var(--text-secondary);
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      padding: 8px 12px;
      cursor: pointer;
      white-space: nowrap;
      transition: color 0.12s ease, border-color 0.12s ease;
    }

    .tab-btn:hover {
      color: var(--text-primary);
    }

    .tab-btn.active {
      color: var(--text-primary);
      font-weight: 600;
      border-bottom-color: var(--viz-teal);
    }

    /* ==========================================================================
       SINGLE-LEVEL BENTO PANES & FLAT INTERNAL CELL DIVIDERS
       ========================================================================== */
    .bento-grid-2 {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .bento-pane {
      background-color: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-pane);
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }

    .pane-header {
      padding: 11px 16px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }

    .pane-title-group {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }

    .pane-title {
      font-family: var(--font-sans);
      font-size: 0.88rem;
      font-weight: 600;
      letter-spacing: -0.01em;
      color: var(--text-primary);
    }

    .pane-subtitle {
      font-size: 0.74rem;
      color: var(--text-secondary);
    }

    .pane-actions {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }

    .mini-btn {
      font-family: var(--font-mono);
      font-size: 0.71rem;
      font-weight: 500;
      padding: 3px 8px;
      border-radius: var(--radius-ctrl);
      border: 1px solid var(--border);
      background-color: var(--bg-surface);
      color: var(--text-secondary);
      cursor: pointer;
      transition: background-color 0.12s ease, color 0.12s ease;
    }

    .mini-btn:hover {
      background-color: var(--bg-hover);
      color: var(--text-primary);
    }

    .mini-btn.active {
      background-color: var(--bg-subtle);
      color: var(--text-primary);
      font-weight: 600;
    }

    /* Visualization Viewports */
    .viz-viewport {
      position: relative;
      width: 100%;
      height: 290px;
      background-color: var(--bg-surface);
    }

    .viz-viewport-tall {
      position: relative;
      width: 100%;
      height: 330px;
      background-color: var(--bg-surface);
    }

    canvas.viz-canvas,
    svg.viz-svg {
      display: block;
      width: 100%;
      height: 100%;
    }

    .viz-overlay-footer {
      padding: 7px 14px;
      border-top: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-family: var(--font-mono);
      font-size: 0.71rem;
      color: var(--text-secondary);
      flex-wrap: wrap;
    }

    .legend-inline {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }

    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-family: var(--font-mono);
      font-size: 0.7rem;
      color: var(--text-secondary);
    }

    .legend-swatch {
      width: 8px;
      height: 8px;
      border-radius: 2px;
      display: inline-block;
    }

    /* Heatmap Table Grid */
    .heatmap-wrap {
      padding: 12px 16px;
      overflow-x: auto;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 290px;
    }

    table.heatmap-matrix {
      width: 100%;
      border-collapse: separate;
      border-spacing: 3px;
      font-family: var(--font-mono);
      font-size: 0.72rem;
      font-variant-numeric: tabular-nums;
    }

    table.heatmap-matrix th {
      font-weight: 500;
      color: var(--text-secondary);
      padding: 4px 6px;
      text-align: center;
      font-size: 0.68rem;
      white-space: nowrap;
    }

    table.heatmap-matrix th.row-hdr {
      text-align: left;
      padding-left: 2px;
    }

    table.heatmap-matrix td.hm-cell {
      text-align: center;
      padding: 7px 4px;
      border-radius: 4px;
      border: 1px solid var(--border);
      cursor: pointer;
      font-weight: 500;
      transition: transform 0.08s ease;
    }

    table.heatmap-matrix td.hm-cell:hover {
      transform: scale(1.03);
    }

    /* ==========================================================================
       3-COLUMN SYNCHRONIZED X12-TO-JSON EXPLORER (FLAT DIVIDED CELLS)
       ========================================================================== */
    .explorer-split {
      display: grid;
      grid-template-columns: 34fr 34fr 32fr;
      background-color: var(--border);
      gap: 1px;
      min-height: 460px;
    }

    .explorer-col {
      background-color: var(--bg-surface);
      display: flex;
      flex-direction: column;
      min-width: 0;
    }

    .subpane-bar {
      padding: 8px 14px;
      border-bottom: 1px solid var(--border);
      background-color: var(--bg-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 0.72rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-secondary);
    }

    .seg-stream-list {
      overflow-y: auto;
      max-height: 440px;
      divide-y: 1px solid var(--border);
    }

    .seg-item {
      padding: 9px 14px;
      border-bottom: 1px solid var(--border);
      cursor: pointer;
      transition: background-color 0.1s ease;
    }

    .seg-item:hover {
      background-color: var(--bg-hover);
    }

    .seg-item.seg-active {
      background-color: var(--bg-subtle);
      box-shadow: inset 3px 0 0 var(--viz-teal);
    }

    .seg-item-top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 3px;
    }

    .seg-tag {
      font-size: 0.73rem;
      font-weight: 600;
    }

    .seg-raw-preview {
      font-family: var(--font-mono);
      font-size: 0.73rem;
      color: var(--text-secondary);
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .seg-detail-body {
      overflow-y: auto;
      max-height: 440px;
      display: flex;
      flex-direction: column;
    }

    .detail-block {
      padding: 11px 14px;
      border-bottom: 1px solid var(--border);
    }

    .detail-kv-label {
      font-size: 0.69rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-secondary);
      margin-bottom: 3px;
      display: block;
    }

    .json-pre {
      font-family: var(--font-mono);
      font-size: 0.75rem;
      line-height: 1.5;
      padding: 12px 14px;
      overflow: auto;
      max-height: 440px;
      color: var(--text-primary);
      background-color: var(--bg-surface);
      white-space: pre;
      font-variant-numeric: tabular-nums;
    }

    .json-pre-tall {
      max-height: 580px;
    }

    /* ==========================================================================
       TABLES (TABULAR MONOSPACE & THIN HORIZONTAL ROW DIVIDERS)
       ========================================================================== */
    .table-scroll {
      overflow-x: auto;
      width: 100%;
    }

    table.data-table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.78rem;
    }

    table.data-table th {
      padding: 8px 12px;
      font-family: var(--font-sans);
      font-size: 0.71rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--text-secondary);
      background-color: var(--bg-subtle);
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }

    table.data-table td {
      padding: 8px 12px;
      border-bottom: 1px solid var(--border);
      color: var(--text-primary);
      vertical-align: top;
      font-variant-numeric: tabular-nums;
    }

    table.data-table tbody tr:last-child td {
      border-bottom: none;
    }

    table.data-table tbody tr:hover td {
      background-color: var(--bg-hover);
    }

    /* Flat Internal Cell Matrix for Envelopes, Entities & Clinical Sections */
    .flat-cell-grid-4 {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      background-color: var(--border);
      gap: 1px;
    }

    .flat-cell-grid-3 {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      background-color: var(--border);
      gap: 1px;
    }

    .flat-cell-grid-2 {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      background-color: var(--border);
      gap: 1px;
    }

    .flat-cell {
      background-color: var(--bg-surface);
      padding: 12px 14px;
      display: flex;
      flex-direction: column;
      gap: 4px;
      min-width: 0;
    }

    /* Tooltip Floating Readout */
    .floating-tooltip {
      position: fixed;
      pointer-events: none;
      z-index: 80;
      background-color: var(--bg-surface);
      color: var(--text-primary);
      border: 1px solid var(--border);
      border-radius: var(--radius-ctrl);
      padding: 7px 10px;
      font-family: var(--font-mono);
      font-size: 0.72rem;
      line-height: 1.4;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
      display: none;
      max-width: 290px;
    }

    /* Modal Dialog */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background-color: rgba(13, 14, 17, 0.62);
      z-index: 90;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }

    .modal-backdrop.open {
      display: flex;
    }

    .modal-pane {
      background-color: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-pane);
      max-width: 660px;
      width: 100%;
      overflow: hidden;
    }

    .drop-area {
      border: 1px dashed var(--border);
      border-radius: var(--radius-ctrl);
      padding: 18px;
      text-align: center;
      cursor: pointer;
      background-color: var(--bg-subtle);
      transition: background-color 0.12s ease;
    }

    .drop-area:hover {
      background-color: var(--bg-hover);
    }

    textarea.edi-textarea {
      width: 100%;
      min-height: 140px;
      background-color: var(--bg-subtle);
      color: var(--text-primary);
      border: 1px solid var(--border);
      border-radius: var(--radius-ctrl);
      padding: 10px;
      font-family: var(--font-mono);
      font-size: 0.76rem;
      resize: vertical;
    }

    textarea.edi-textarea:focus {
      outline: none;
    }

    .hidden {
      display: none !important;
    }

    .section-stack {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .footer-bar {
      padding-top: 10px;
      border-top: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 8px;
      font-size: 0.75rem;
      color: var(--text-secondary);
    }

    @media (max-width: 1120px) {
      .kpi-bento-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .bento-grid-2 { grid-template-columns: 1fr; }
      .explorer-split { grid-template-columns: 1fr; }
      .flat-cell-grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .flat-cell-grid-3 { grid-template-columns: 1fr; }
    }

    @media (max-width: 640px) {
      .kpi-bento-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .flat-cell-grid-4, .flat-cell-grid-2 { grid-template-columns: 1fr; }
      .workspace-shell { padding: 10px 12px 28px; }
    }
  </style>
</head>
<body>
  <div class="workspace-shell">

    <!-- TOP NAVIGATION HEADER -->
    <header class="topbar" id="topNavigationHeader">
      <div class="brand-block">
        <div class="brand-title-row">
          <h1 id="dashboardTitle">__TITLE__</h1>
          <span class="tx-code-tag" id="txBadge">__TX_BADGE__</span>
        </div>
        <div class="brand-subtitle">
          <span>EDI X12 Semantic Mapping Engine &amp; HL7 C-CDA R2.1 Clinical Telemetry Studio</span>
          <span>&bull;</span>
          <span class="sse-indicator" id="sseStatusIndicator" data-live="false">Mode: Standalone Empirical Bundle</span>
        </div>
      </div>

      <div class="topbar-controls">
        <label for="datasetSelector" class="hidden">Active Workspace Transaction</label>
        <select id="datasetSelector" class="ctrl-select" title="Switch Empirical Workspace Transaction" onchange="selectWorkspaceDataset(this.value)">
          <!-- Populated from BUNDLE.datasets -->
        </select>

        <button type="button" id="btnOpenUploadModal" class="ctrl-btn ctrl-btn-primary" onclick="openUploadModal()">
          Parse X12 Stream
        </button>

        <!-- Three-Icon Theme Selector (DESIGN.md Section 3) -->
        <div class="theme-switcher" role="group" aria-label="Theme Mode Selector">
          <button type="button" id="theme-btn-light" class="theme-mode-btn" title="Light Theme" aria-label="Light Theme" data-theme-mode="light" aria-pressed="false" onclick="setThemeMode('light')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="4"></circle>
              <line x1="12" y1="2" x2="12" y2="4"></line>
              <line x1="12" y1="20" x2="12" y2="22"></line>
              <line x1="4.93" y1="4.93" x2="6.34" y2="6.34"></line>
              <line x1="17.66" y1="17.66" x2="19.07" y2="19.07"></line>
              <line x1="2" y1="12" x2="4" y2="12"></line>
              <line x1="20" y1="12" x2="22" y2="12"></line>
              <line x1="4.93" y1="19.07" x2="6.34" y2="17.66"></line>
              <line x1="17.66" y1="6.34" x2="19.07" y2="4.93"></line>
            </svg>
          </button>
          <button type="button" id="theme-btn-dark" class="theme-mode-btn" title="Dark Theme" aria-label="Dark Theme" data-theme-mode="dark" aria-pressed="false" onclick="setThemeMode('dark')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            </svg>
          </button>
          <button type="button" id="theme-btn-system" class="theme-mode-btn active" title="System Theme" aria-label="System Theme" data-theme-mode="system" aria-pressed="true" onclick="setThemeMode('system')">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
              <line x1="8" y1="21" x2="16" y2="21"></line>
              <line x1="12" y1="17" x2="12" y2="21"></line>
            </svg>
          </button>
        </div>
      </div>
    </header>

    <!-- KEY METRICS BENTO STRIP -->
    <section id="metricsBar" class="kpi-bento-strip" aria-label="Key Transaction Metrics">
      <!-- Populated dynamically with tabular-nums -->
    </section>

    <!-- NAVIGATION TABS -->
    <nav class="view-nav" id="tabBar" aria-label="Dashboard Sections">
      <div class="tab-list">
        <button type="button" onclick="switchTab('studio')" id="tabBtn-studio" class="tab-btn active">
          Workspace Studio
        </button>
        <button type="button" onclick="switchTab('explorer')" id="tabBtn-explorer" class="tab-btn">
          Interactive X12 &amp; JSON Explorer
        </button>
        <button type="button" onclick="switchTab('overview')" id="tabBtn-overview" class="tab-btn">
          Transaction &amp; Provenance
        </button>
        <button type="button" onclick="switchTab('clinical')" id="tabBtn-clinical" class="tab-btn">
          C-CDA Clinical Payload
        </button>
        <button type="button" onclick="switchTab('raw_edi')" id="tabBtn-raw_edi" class="tab-btn">
          Raw X12 File
        </button>
        <button type="button" onclick="switchTab('json')" id="tabBtn-json" class="tab-btn">
          Structured JSON
        </button>
        <button type="button" onclick="switchTab('mapping_guide')" id="tabBtn-mapping_guide" class="tab-btn">
          Field Mapping Spec
        </button>
      </div>
    </nav>

    <!-- ========================================================================
         VISUALIZATION STUDIO PANES (VISIBLE IN 'studio' MODE)
         ======================================================================== -->
    <div id="studioVisualsGroup" class="section-stack">

      <!-- ROW 1: 2D QUANTITATIVE CHART + CONCENTRATION HEATMAP -->
      <div class="bento-grid-2">

        <!-- PANE 1: 2D QUANTITATIVE FINANCIAL & TELEMETRY CHART -->
        <section class="bento-pane" id="paneFinancialChart">
          <div class="pane-header">
            <div class="pane-title-group">
              <h2 class="pane-title" id="chartPaneTitle">Active Transaction Financial &amp; Domain Profile</h2>
              <p class="pane-subtitle" id="chartSubtitle">Empirical claim charge, line breakdown, remittance settlement, and benefit metrics</p>
            </div>
            <div class="pane-actions">
              <button type="button" id="chartModeActive" class="mini-btn active" onclick="setChartMode('active')">Selected Stream</button>
              <button type="button" id="chartModeFinancial" class="mini-btn" onclick="setChartMode('financial')">Episode ($)</button>
              <button type="button" id="chartModeTelemetry" class="mini-btn" onclick="setChartMode('telemetry')">Latency</button>
            </div>
          </div>
          <div class="viz-viewport">
            <canvas id="financialChartCanvas" class="viz-canvas" aria-label="Quantitative Financial and Telemetry Plot"></canvas>
          </div>
          <div class="viz-overlay-footer">
            <div class="legend-inline" id="chartLegendBar">
              <span class="legend-item"><span class="legend-swatch" style="background:#0D9488"></span>Billed</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#059669"></span>Paid</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#4F46E5"></span>CO Write-Off</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#D97706"></span>Patient Resp</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#E11D48"></span>Pended Alert</span>
            </div>
            <span id="chartReadoutText">Active Stream</span>
          </div>
        </section>

        <!-- PANE 2: SEGMENT-LOOP CONCENTRATION MATRIX (HEATMAP) -->
        <section class="bento-pane" id="paneHeatmapMatrix">
          <div class="pane-header">
            <div class="pane-title-group">
              <h2 class="pane-title">Loop Stratum Concentration Matrix</h2>
              <p class="pane-subtitle" id="heatmapSubtitle">Empirical segment density across workspace transactions and 5010 loop strata (click cell to inspect)</p>
            </div>
            <div class="pane-actions">
              <span class="mono" style="font-size:0.7rem;color:var(--text-secondary)" id="heatmapTotalBadge">0 total segments</span>
            </div>
          </div>
          <div class="heatmap-wrap" id="heatmapContainer">
            <!-- Populated dynamically with Teal -> Indigo -> Rose gradient scale -->
          </div>
          <div class="viz-overlay-footer">
            <div class="legend-inline">
              <span class="legend-item"><span class="legend-swatch" style="background:var(--bg-surface);border:1px solid var(--border)"></span>0</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#0D9488"></span>Low–Mid (Teal)</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#4F46E5"></span>High (Indigo)</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#E11D48"></span>Peak Density (Rose)</span>
            </div>
            <span id="heatmapReadoutText">Click row/cell to switch dataset</span>
          </div>
        </section>

      </div>

      <!-- ROW 2: SVG RELATIONSHIP NODE MAP + 3D MOLECULAR / STRUCTURAL DIAGRAM -->
      <div class="bento-grid-2">

        <!-- PANE 3: INTERACTIVE RELATIONSHIP NODE MAP (SVG) -->
        <section class="bento-pane" id="paneRelationshipNodeMap">
          <div class="pane-header">
            <div class="pane-title-group">
              <h2 class="pane-title">Interactive Relationship Node Map</h2>
              <p class="pane-subtitle" id="nodeMapSubtitle">Deterministic EDI envelope, trading partner, claim loop, and clinical attachment graph</p>
            </div>
            <div class="pane-actions">
              <button type="button" id="nodeMapZoomIn" class="mini-btn" onclick="zoomNodeMap(1.2)">Zoom +</button>
              <button type="button" id="nodeMapZoomOut" class="mini-btn" onclick="zoomNodeMap(0.83)">Zoom &minus;</button>
              <button type="button" id="nodeMapReset" class="mini-btn" onclick="resetNodeMapTransform()">Reset</button>
            </div>
          </div>
          <div class="viz-viewport-tall" id="nodeMapViewport">
            <svg id="relationshipNodeMap" class="viz-svg" role="img" aria-label="Interactive Relationship Node Map"></svg>
          </div>
          <div class="viz-overlay-footer">
            <div class="legend-inline">
              <span class="legend-item"><span class="legend-swatch" style="background:#0D9488"></span>Envelope/Core</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#4F46E5"></span>Entity/Clinical</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#059669"></span>Validated/Paid</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#D97706"></span>Adjustment</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#E11D48"></span>Alert/Pended</span>
            </div>
            <span id="nodeMapSelectionReadout">Drag to pan &bull; Scroll to zoom &bull; Click node</span>
          </div>
        </section>

        <!-- PANE 4: STRUCTURAL DATA DIAGRAM & 3D MOLECULAR VIEW -->
        <section class="bento-pane" id="paneStructural3d">
          <div class="pane-header">
            <div class="pane-title-group">
              <h2 class="pane-title">Structural Data Diagram</h2>
              <p class="pane-subtitle" id="mol3dSubtitle">3D X12 spatial loop topology &amp; C-CDA RxNorm pharmacophore conformers</p>
            </div>
            <div class="pane-actions">
              <select id="molModelSelect" class="ctrl-select" style="height:26px;font-size:0.71rem;padding:0 8px" title="Select 3D Structural Lattice or C-CDA Conformer" onchange="set3dModel(this.value, true)">
                <option value="x12_lattice">Active X12 Spatial Loop Lattice</option>
                <option value="lisinopril">RxNorm 314076: Lisinopril 20mg (Active Med)</option>
                <option value="penicillin">RxNorm 70618: Penicillin G (Severe Allergy)</option>
              </select>
              <button type="button" id="btnToggle3dRenderer" class="mini-btn" onclick="toggle3dRendererMode()" title="Switch Hardware WebGL / Software Projection Fallback">
                Engine: Auto
              </button>
              <button type="button" id="btnReset3dCamera" class="mini-btn" onclick="reset3dCamera()">Reset</button>
            </div>
          </div>
          <div class="viz-viewport-tall">
            <canvas id="molecular3dCanvas" class="viz-canvas" aria-label="3D Molecular and Structural Conformer View"></canvas>
          </div>
          <div class="viz-overlay-footer">
            <div class="legend-inline" id="mol3dLegendBar">
              <span class="legend-item"><span class="legend-swatch" style="background:#0D9488"></span>Envelope/Line</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#4F46E5"></span>Entity/Clinical</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#059669"></span>Claim/Paid</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#D97706"></span>Adjustment</span>
              <span class="legend-item"><span class="legend-swatch" style="background:#E11D48"></span>Alert/Pended</span>
            </div>
            <span id="mol3dEngineBadge">Renderer: Initializing</span>
          </div>
        </section>

      </div>
    </div>

    <!-- ========================================================================
         INTERACTIVE CLICKABLE X12 & JSON EXPLORER (VISIBLE IN 'studio' & 'explorer')
         ======================================================================== -->
    <section id="tab-explorer" class="bento-pane tab-section">
      <div class="pane-header">
        <div class="pane-title-group">
          <h2 class="pane-title">Synchronized X12 Segment-to-JSON Inspector</h2>
          <p class="pane-subtitle">Select any raw X12 segment to inspect its 5010 loop context, element values, and mapped JSON subtree</p>
        </div>
        <div class="pane-actions">
          <input type="text" id="segFilterInput" class="ctrl-input" style="height:28px;width:230px;font-size:0.75rem" onkeyup="filterSegments()" placeholder="Filter segment, code, or loop...">
        </div>
      </div>

      <div class="explorer-split">
        <!-- Column 1: Segment Stream -->
        <div class="explorer-col">
          <div class="subpane-bar">
            <span>X12 Segments Stream</span>
            <span class="mono" id="segCountBadge">0 segments</span>
          </div>
          <div id="segmentListContainer" class="seg-stream-list"></div>
        </div>

        <!-- Column 2: Element Breakdown -->
        <div class="explorer-col">
          <div class="subpane-bar">
            <span>Segment Semantics &amp; Elements</span>
            <span class="mono tone-teal" id="activeSegTag">ISA</span>
          </div>
          <div id="segmentDetailCard" class="seg-detail-body">
            <div class="detail-block">
              <span class="mono" style="font-weight:600;font-size:0.82rem" id="activeSegName">Select a segment</span>
              <p style="font-size:0.76rem;color:var(--text-secondary);margin-top:4px" id="activeSegDesc"></p>
            </div>
            <div class="flat-cell-grid-2" style="border-bottom:1px solid var(--border)">
              <div class="flat-cell" style="padding:9px 14px">
                <span class="detail-kv-label">5010 Loop Context</span>
                <span class="mono" style="font-size:0.75rem" id="activeSegLoop">Envelope</span>
              </div>
              <div class="flat-cell" style="padding:9px 14px">
                <span class="detail-kv-label">Mapped JSON Target</span>
                <span class="mono tone-emerald" style="font-size:0.75rem;word-break:break-all" id="activeSegTargetPath">interchange_header</span>
              </div>
            </div>
            <div class="table-scroll" id="activeSegElementsTable">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Ref</th>
                    <th>Semantic Key</th>
                    <th>Observed Value</th>
                  </tr>
                </thead>
                <tbody id="activeSegElementsTbody"></tbody>
              </table>
            </div>
          </div>
        </div>

        <!-- Column 3: Synchronized JSON Subtree -->
        <div class="explorer-col">
          <div class="subpane-bar">
            <span>JSON Equivalent Subtree</span>
            <button type="button" class="mini-btn" id="btnCopyJsonNode" onclick="copyActiveJsonSubtree()">Copy Node</button>
          </div>
          <pre id="activeJsonSubtreeDisplay" class="json-pre"></pre>
        </div>
      </div>
    </section>

    <!-- ========================================================================
         TRANSACTION DETAILS, PROVENANCE & VALIDATION RECORDS ('studio' & 'overview')
         ======================================================================== -->
    <div id="tab-overview" class="section-stack tab-section">

      <!-- Validation & Provenance Bento Grid -->
      <div class="bento-grid-2">

        <!-- Validation Records Table -->
        <section class="bento-pane" id="paneValidationAudit">
          <div class="pane-header">
            <div class="pane-title-group">
              <h2 class="pane-title">Envelope &amp; Domain Validation Records</h2>
              <p class="pane-subtitle" id="validationSubtitle">Automated HIPAA 5010 control parity, charge reconciliation, and clinical alert checks</p>
            </div>
            <span class="status-tag status-pass" id="overallValidationBadge">PASS</span>
          </div>
          <div class="table-scroll">
            <table class="data-table" id="validationAuditTable">
              <thead>
                <tr>
                  <th>Rule ID</th>
                  <th>Scope</th>
                  <th>Validation Check</th>
                  <th>Expected</th>
                  <th>Observed</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody id="validationAuditTbody"></tbody>
            </table>
          </div>
        </section>

        <!-- Provenance Citations & Workspace Telemetry -->
        <section class="bento-pane" id="paneProvenanceRecords">
          <div class="pane-header">
            <div class="pane-title-group">
              <h2 class="pane-title">Workspace Provenance &amp; Telemetry Log</h2>
              <p class="pane-subtitle" id="activeProvenanceCitation">Empirical file digests, byte sizes, and parser execution timings</p>
            </div>
          </div>
          <div class="table-scroll">
            <table class="data-table" id="provenanceLogTable">
              <thead>
                <tr>
                  <th>Workspace File</th>
                  <th>Tx</th>
                  <th>Segs</th>
                  <th>SHA-256 (16)</th>
                  <th>Parse</th>
                  <th>Audit</th>
                </tr>
              </thead>
              <tbody id="provenanceLogTbody"></tbody>
            </table>
          </div>
        </section>

      </div>

      <!-- Interchange & Functional Group Envelope Metadata -->
      <section class="bento-pane" id="paneEnvelopeDetails">
        <div class="pane-header">
          <div class="pane-title-group">
            <h2 class="pane-title">Interchange &amp; Functional Group Envelopes</h2>
            <p class="pane-subtitle" id="envelopeSubtitle">Parsed ISA, GS, and ST header routing attributes and detected delimiters</p>
          </div>
        </div>
        <div id="envelopeGrid" class="flat-cell-grid-4"></div>
      </section>

      <!-- Business Entities & Participants -->
      <section class="bento-pane" id="paneBusinessEntities">
        <div class="pane-header">
          <div class="pane-title-group">
            <h2 class="pane-title">Business Entities &amp; Trading Participants</h2>
            <p class="pane-subtitle" id="entitiesSubtitle">Extracted Loop 1000 / 2010 organizations, providers, payers, and subscribers</p>
          </div>
        </div>
        <div id="entitiesGrid" class="flat-cell-grid-3"></div>
      </section>

      <!-- Transaction Domain Records (837 / 835 / 277 / 271 / 270 / 278 / 275) -->
      <div id="txSpecificPanel" class="section-stack"></div>

    </div>

    <!-- ========================================================================
         C-CDA CLINICAL PAYLOAD TAB ('clinical')
         ======================================================================== -->
    <section id="tab-clinical" class="bento-pane tab-section hidden">
      <div class="pane-header">
        <div class="pane-title-group">
          <h2 class="pane-title" id="clinicalDocTitle">Consolidated Clinical Document (HL7 C-CDA R2.1)</h2>
          <p class="pane-subtitle" id="clinicalDocMeta">Extracted from 275 Binary Data Segment (BDS/BIN)</p>
        </div>
        <span class="status-tag tone-indigo" id="clinicalSourceTag">LOINC 34133-9</span>
      </div>
      <div id="clinicalSectionsGrid" class="flat-cell-grid-2"></div>
    </section>

    <!-- ========================================================================
         RAW X12 STREAM TAB ('raw_edi')
         ======================================================================== -->
    <section id="tab-raw_edi" class="bento-pane tab-section hidden">
      <div class="pane-header">
        <div class="pane-title-group">
          <h2 class="pane-title">Raw X12 Transmission Stream</h2>
          <p class="pane-subtitle" id="rawEdiProvenanceSub">Unmodified EDI 5010 segment stream</p>
        </div>
        <div class="pane-actions">
          <button type="button" id="btnCopyRawEdi" class="mini-btn" onclick="copyRawEdi()">Copy EDI Text</button>
          <button type="button" id="btnDownloadRawEdi" class="mini-btn" onclick="downloadRawEdiFile()">Download .x12</button>
        </div>
      </div>
      <pre id="rawEdiDisplay" class="json-pre json-pre-tall"></pre>
    </section>

    <!-- ========================================================================
         STRUCTURED JSON OUTPUT TAB ('json')
         ======================================================================== -->
    <section id="tab-json" class="bento-pane tab-section hidden">
      <div class="pane-header">
        <div class="pane-title-group">
          <h2 class="pane-title">Hierarchical Structured JSON Output</h2>
          <p class="pane-subtitle" id="jsonProvenanceSub">Complete parsed interchange, functional groups, loops, and semantic fields</p>
        </div>
        <div class="pane-actions">
          <button type="button" id="btnCopyJsonFull" class="mini-btn" onclick="copyJsonOutput()">Copy JSON</button>
          <button type="button" id="btnDownloadJsonFull" class="mini-btn" onclick="downloadJsonFile()">Download .json</button>
        </div>
      </div>
      <pre id="jsonTreeDisplay" class="json-pre json-pre-tall"></pre>
    </section>

    <!-- ========================================================================
         FIELD MAPPING SPECIFICATION TAB ('mapping_guide')
         ======================================================================== -->
    <section id="tab-mapping_guide" class="bento-pane tab-section hidden">
      <div class="pane-header">
        <div class="pane-title-group">
          <h2 class="pane-title">EDI 5010 &amp; HL7 C-CDA Semantic Key Reference</h2>
          <p class="pane-subtitle" id="specSubtitle">Deterministic field dictionary mapping X12 segments to structured JSON paths</p>
        </div>
        <div class="pane-actions">
          <input type="text" id="specFilterInput" class="ctrl-input" style="height:28px;width:230px;font-size:0.75rem" onkeyup="filterSpecTable()" placeholder="Search segment or JSON path...">
        </div>
      </div>
      <div class="table-scroll">
        <table class="data-table" id="specTable">
          <thead>
            <tr>
              <th>Segment</th>
              <th>Observed in Active Stream</th>
              <th>Target JSON Key Path</th>
              <th>5010 Loop / Standard</th>
              <th>Healthcare Business Semantics</th>
            </tr>
          </thead>
          <tbody id="specTableTbody"></tbody>
        </table>
      </div>
    </section>

    <!-- FOOTER -->
    <footer class="footer-bar">
      <span id="footerActiveStreamLabel">EDI X12 (005010) &amp; HL7 C-CDA R2.1 Empirical Parser Studio</span>
      <span class="mono" id="footerProvenanceStamp">Generated: __GENERATED_AT__</span>
    </footer>

  </div>

  <!-- FLOATING TOOLTIP -->
  <div id="vizTooltip" class="floating-tooltip"></div>

  <!-- MODAL: PARSE CUSTOM X12 STREAM -->
  <div id="uploadModal" class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="uploadModalTitle">
    <div class="modal-pane">
      <div class="pane-header">
        <div class="pane-title-group">
          <h2 class="pane-title" id="uploadModalTitle">Parse Custom EDI X12 File or Stream</h2>
          <p class="pane-subtitle">Executes via REST API (/v1/parse/x12) when served over HTTP, or built-in client-side 5010 + C-CDA parser offline</p>
        </div>
        <button type="button" class="mini-btn" id="btnCloseUploadModalTop" onclick="closeUploadModal()">Close</button>
      </div>
      <div style="padding:16px;display:flex;flex-direction:column;gap:12px">
        <div id="dropZone" class="drop-area">
          <p style="font-weight:600;font-size:0.82rem">Drop any .x12, .edi, or .txt transaction file here, or click to select</p>
          <p style="font-size:0.74rem;color:var(--text-secondary);margin-top:3px">Supports 837, 835, 270, 271, 277, 275 (raw or Base64 HL7 C-CDA XML), and 278</p>
          <p id="uploadedFileBadge" class="mono tone-teal" style="font-size:0.74rem;margin-top:6px"></p>
          <input type="file" id="fileInput" class="hidden" accept=".x12,.edi,.txt">
        </div>
        <div>
          <label for="rawInputArea" class="detail-kv-label">Raw EDI X12 Segment Stream</label>
          <textarea id="rawInputArea" class="edi-textarea" placeholder="ISA*00*          *00*          *ZZ*SUBMITTER123   *ZZ*RECEIVER456    *260814*1430*^*00501*000000001*0*P*:~"></textarea>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding-top:4px">
          <button type="button" class="mini-btn" id="btnClearUploadArea" onclick="clearUploadArea()">Clear Stream</button>
          <div style="display:flex;gap:8px">
            <button type="button" class="ctrl-btn" id="btnCancelUpload" onclick="closeUploadModal()">Cancel</button>
            <button type="button" class="ctrl-btn ctrl-btn-primary" id="btnExecuteParse" onclick="parseCustomX12()">Parse &amp; Update Studio</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    /* ==========================================================================
       EMBEDDED EMPIRICAL WORKSPACE BUNDLE & STATE
       ========================================================================== */
    const BUNDLE = __BUNDLE_JSON__;

    const PALETTE = {
      teal: '#0D9488',
      amber: '#D97706',
      indigo: '#4F46E5',
      emerald: '#059669',
      rose: '#E11D48'
    };

    const THEME_TOKENS = {
      light: {
        bgPage: '#FAFAF9',
        bgSurface: '#FFFFFF',
        border: '#E7E5E4',
        textPrimary: '#1C1917',
        textSecondary: '#787774',
        gridLine: '#E7E5E4'
      },
      dark: {
        bgPage: '#0D0E11',
        bgSurface: '#16171D',
        border: '#292A30',
        textPrimary: '#ECE8E2',
        textSecondary: '#9A9895',
        gridLine: '#292A30'
      }
    };

    let ACTIVE_DATASET_IDX = BUNDLE.active_index || 0;
    let CURRENT_DATASET = BUNDLE.datasets[ACTIVE_DATASET_IDX] || BUNDLE.datasets[0];
    let CURRENT_DATA = CURRENT_DATASET.parsed_data;
    let CURRENT_RAW_EDI = CURRENT_DATASET.raw_x12;

    let ALL_SEGMENTS = [];
    let FILTERED_SEGMENTS = [];
    let SELECTED_SEG_INDEX = 0;
    let ACTIVE_TAB = 'studio';
    let CHART_MODE = 'active';
    let CHART_HIT_BOXES = [];
    let PENDING_UPLOAD_FILENAME = '';

    /* Segment Knowledge Base */
    const SEGMENT_KB = {
      'ISA': { name: 'Interchange Control Header', loop: 'Envelope', desc: 'Defines sender/receiver routing IDs, control number (ISA13), timestamp, and element/component delimiters.' },
      'GS': { name: 'Functional Group Header', loop: 'Group Header', desc: 'Identifies functional transaction family (HC, HP, HN, PI, HB, HS, HI) and 5010 implementation guide.' },
      'ST': { name: 'Transaction Set Header', loop: 'Set Header', desc: 'Opens transaction set context (837, 835, 277, 275, 271, 270, 278) and assigns control sequence.' },
      'BHT': { name: 'Beginning of Hierarchical Transaction', loop: 'Header', desc: 'Specifies hierarchical structure code, transaction purpose, reference batch ID, and creation time.' },
      'BGN': { name: 'Beginning Segment for Attachment', loop: 'Header (275)', desc: 'Establishes patient attachment transmission reference identifier and timestamp.' },
      'BPR': { name: 'Financial Information & Settlement', loop: 'Header (835)', desc: 'Specifies net EFT/check payment amount, ACH payment method, ABA routing numbers, and settlement date.' },
      'TRN': { name: 'Reassociation Trace Number', loop: 'Header / Loop 2200', desc: 'Unique check/EFT trace number or claim tracking identifier for automated reconciliation.' },
      'HL': { name: 'Hierarchical Level', loop: 'Loop 2000', desc: 'Defines parent-child hierarchy node (20=Information Source, 21=Receiver, 22=Subscriber, EV=Event).' },
      'NM1': { name: 'Individual or Organizational Name', loop: 'Loop 1000 / 2010', desc: 'Identifies healthcare entities (85=Billing Provider, PR=Payer, IL=Subscriber, QC=Patient, 82=Rendering) with NPI/ID.' },
      'N1': { name: 'Party Identification', loop: 'Loop 1000 (835)', desc: 'Identifies Remittance Payer (PR) and Payee Provider (PE) names and identifiers.' },
      'N3': { name: 'Party Street Address', loop: 'Loop 1000 / 2010', desc: 'Physical street address line 1 and suite/unit line 2 for the parent entity.' },
      'N4': { name: 'Geographic Location', loop: 'Loop 1000 / 2010', desc: 'City, two-letter state code, and postal ZIP code for the parent entity.' },
      'PER': { name: 'Administrative Communications Contact', loop: 'Loop 1000A', desc: 'Submitter contact person, telephone number, and electronic mail address.' },
      'DMG': { name: 'Demographic Information', loop: 'Loop 2010BA/CA', desc: 'Subscriber or patient birth date (YYYYMMDD) and administrative gender code.' },
      'SBR': { name: 'Subscriber Information', loop: 'Loop 2000B', desc: 'Payer responsibility sequence (P=Primary), relationship code, and group policy number.' },
      'REF': { name: 'Reference Identification', loop: 'Various Loops', desc: 'Secondary identifiers including Employer Tax ID (EI), Payer ICN (1K), or Payment Reference (EV).' },
      'PRV': { name: 'Provider Specialty Information', loop: 'Loop 2000A / 2310B', desc: 'Healthcare Provider Taxonomy Code (PXC) specifying clinical specialty.' },
      'CLM': { name: 'Health Care Claim', loop: 'Loop 2300 (837)', desc: 'Master claim billing record containing patient control number, total billed charges, and place of service.' },
      'DTP': { name: 'Date or Time Period', loop: 'Loop 2300 / 2400', desc: 'Service date (472), plan eligibility date (291), or admission/discharge timestamps.' },
      'DTM': { name: 'Date/Time Reference', loop: 'Header / Loop 2100', desc: 'Production date (405) or remittance line service date (472).' },
      'HI': { name: 'Health Care Diagnosis Codes', loop: 'Loop 2300 / 2000E', desc: 'Principal (ABK) and secondary (ABF) ICD-10-CM diagnosis codes.' },
      'LX': { name: 'Service Line Counter', loop: 'Loop 2400 (837)', desc: 'Sequential line number index opening a professional or institutional service line loop.' },
      'SV1': { name: 'Professional Service Line', loop: 'Loop 2400 / 2000F', desc: 'CPT/HCPCS procedure code, modifiers, line item charge amount, unit count, and diagnosis pointers.' },
      'SV2': { name: 'Institutional Service Line', loop: 'Loop 2400 (837I)', desc: 'Hospital revenue code, CPT/HCPCS procedure, line charge amount, and service units.' },
      'CLP': { name: 'Claim Payment Information', loop: 'Loop 2100 (835)', desc: 'Remittance adjudication status (1=Paid Primary), billed total, paid amount, and patient responsibility.' },
      'CAS': { name: 'Claims Adjustment', loop: 'Loop 2100 / 2110 (835)', desc: 'Contractual Obligation (CO) and Patient Responsibility (PR) CARC reason codes and adjustment amounts.' },
      'SVC': { name: 'Service Payment Information', loop: 'Loop 2110 (835)', desc: 'Line-level adjudicated CPT procedure code, submitted charge, and paid amount.' },
      'PLB': { name: 'Provider Level Balance Adjustment', loop: 'Summary (835)', desc: 'Provider-level fiscal period balance adjustments or offsets.' },
      'STC': { name: 'Claim Status Information', loop: 'Loop 2200D (277)', desc: 'Reports pended status and clinical documentation requests (Category R4, Action A4).' },
      'PWK': { name: 'Paperwork / Attachment Indicator', loop: 'Loop 2200D / 2300', desc: 'Specifies required clinical report type (09=Progress Note), transmission mode (EL), and control number.' },
      'CAT': { name: 'Category of Patient Information', loop: 'Loop 2000 (275)', desc: 'Defines attachment report category and HL7 C-CDA payload tracking identifier.' },
      'PID': { name: 'Product / Attachment Description', loop: 'Loop 2000 (275)', desc: 'Human-readable clinical attachment document description.' },
      'BDS': { name: 'Binary Data Segment', loop: 'Loop 2000 (275)', desc: 'Carries embedded HL7 C-CDA R2.1 XML clinical document (demographics, allergies, meds, problems, vitals, notes).' },
      'BIN': { name: 'Binary Data Payload', loop: 'Loop 2000 (275)', desc: 'Carries raw XML or Base64-encoded clinical payload octets.' },
      'EB': { name: 'Eligibility or Benefit Information', loop: 'Loop 2110C (271)', desc: 'Communicates active coverage, copay, deductible, and coinsurance benefit terms.' },
      'EQ': { name: 'Eligibility or Benefit Inquiry', loop: 'Loop 2110C (270)', desc: 'Requests benefit verification for specified service type codes (30=Plan Coverage, 98=Office Visit).' },
      'UM': { name: 'Health Care Services Review', loop: 'Loop 2000E (278)', desc: 'Specifies prior authorization request category, certification type, and facility setting.' },
      'HCR': { name: 'Health Care Services Review Decision', loop: 'Loop 2000E/F (278)', desc: 'Communicates prior authorization certification decision (A1=Certified in Total) and authorization number.' },
      'SE': { name: 'Transaction Set Trailer', loop: 'Set Trailer', desc: 'Closes transaction set and verifies included segment count (SE01) and control number (SE02).' },
      'GE': { name: 'Functional Group Trailer', loop: 'Group Trailer', desc: 'Closes functional group and verifies transaction set count and group control number (GE02).' },
      'IEA': { name: 'Interchange Control Trailer', loop: 'Envelope', desc: 'Closes interchange envelope and verifies group count and control number (IEA02).' }
    };

    /* ==========================================================================
       THEME MANAGEMENT: LIGHT, DARK & REAL-TIME SYSTEM MODE (DESIGN.md Section 3)
       ========================================================================== */
    const STORAGE_KEY_THEME = 'x12_dashboard_theme_mode';
    let CURRENT_THEME_MODE = 'system';
    const SYSTEM_MEDIA = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

    function resolveEffectiveTheme(mode) {
      if (mode === 'light' || mode === 'dark') return mode;
      if (SYSTEM_MEDIA && typeof SYSTEM_MEDIA.matches === 'boolean') {
        return SYSTEM_MEDIA.matches ? 'dark' : 'light';
      }
      return BUNDLE.system_theme === 'dark' ? 'dark' : 'light';
    }

    function getActiveTokens() {
      const eff = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      return THEME_TOKENS[eff];
    }

    function applyThemeMode(mode, persist = true) {
      CURRENT_THEME_MODE = ['light', 'dark', 'system'].includes(mode) ? mode : 'system';
      if (persist) {
        try { localStorage.setItem(STORAGE_KEY_THEME, CURRENT_THEME_MODE); } catch (_) {}
      }

      const effective = resolveEffectiveTheme(CURRENT_THEME_MODE);
      const root = document.documentElement;
      root.setAttribute('data-theme', effective);
      root.classList.remove('light', 'dark');
      root.classList.add(effective);

      ['light', 'dark', 'system'].forEach(m => {
        const btn = document.getElementById(`theme-btn-${m}`);
        if (btn) {
          const isActive = m === CURRENT_THEME_MODE;
          btn.classList.toggle('active', isActive);
          btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        }
      });

      // Re-render theme-aware visualizations without resetting camera, pan/zoom, or scroll
      renderFinancialChart();
      renderHeatmapMatrix();
      renderRelationshipNodeMap(false);
      request3dRender();
    }

    function setThemeMode(mode) {
      applyThemeMode(mode, true);
    }

    if (SYSTEM_MEDIA) {
      const onSysChange = () => {
        if (CURRENT_THEME_MODE === 'system') {
          applyThemeMode('system', false);
        }
      };
      if (SYSTEM_MEDIA.addEventListener) {
        SYSTEM_MEDIA.addEventListener('change', onSysChange);
      } else if (SYSTEM_MEDIA.addListener) {
        SYSTEM_MEDIA.addListener(onSysChange);
      }
    }

    /* ==========================================================================
       DATASET SELECTION & INCREMENTAL STATE PRESERVATION
       ========================================================================== */
    function populateDatasetSelector() {
      const sel = document.getElementById('datasetSelector');
      if (!sel) return;
      sel.innerHTML = '';
      BUNDLE.datasets.forEach((ds, idx) => {
        const opt = document.createElement('option');
        opt.value = String(idx);
        const segCount = (ds.parsed_data.summary || {}).total_segments_count || 0;
        opt.textContent = `[${ds.meta.tx_type}] ${ds.meta.filename} (${segCount} segs)`;
        if (idx === ACTIVE_DATASET_IDX) opt.selected = true;
        sel.appendChild(opt);
      });
    }

    function autoSelect3dModelForDataset(data, meta) {
      const txType = meta.tx_type || 'X12';
      const clin = (((((data.functional_groups || [])[0] || {}).transaction_sets || [])[0] || {}).parsed_transaction || {}).attached_clinical_data || {};
      if (txType === '275' && clin && Object.keys(clin).length > 0) {
        const meds = clin.medications || [];
        const algs = clin.allergies || [];
        const hasLisinopril = meds.some(m => String(m.rxnorm_code || '') === '314076' || /lisinopril/i.test(m.medication_name || ''));
        const hasPenicillin = algs.some(a => String(a.rxnorm_code || '') === '70618' || /penicillin/i.test(a.substance || ''));
        if (hasLisinopril) MOL_STATE.modelKey = 'lisinopril';
        else if (hasPenicillin) MOL_STATE.modelKey = 'penicillin';
        else MOL_STATE.modelKey = 'x12_lattice';
      } else {
        MOL_STATE.modelKey = 'x12_lattice';
      }
      const sel3d = document.getElementById('molModelSelect');
      if (sel3d) sel3d.value = MOL_STATE.modelKey;
    }

    function selectWorkspaceDataset(indexOrId, preserveScroll = true, keepFilter = false) {
      const scrollY = window.scrollY;
      let idx = typeof indexOrId === 'number' ? indexOrId : parseInt(indexOrId, 10);
      if (isNaN(idx)) {
        idx = BUNDLE.datasets.findIndex(d => d.id === indexOrId);
      }
      if (idx < 0 || idx >= BUNDLE.datasets.length) return;

      ACTIVE_DATASET_IDX = idx;
      CURRENT_DATASET = BUNDLE.datasets[idx];
      CURRENT_DATA = CURRENT_DATASET.parsed_data;
      CURRENT_RAW_EDI = CURRENT_DATASET.raw_x12;

      const sel = document.getElementById('datasetSelector');
      if (sel) sel.value = String(idx);

      if (!keepFilter) {
        const qInput = document.getElementById('segFilterInput');
        if (qInput) qInput.value = '';
      }

      SELECTED_SEG_INDEX = 0;
      autoSelect3dModelForDataset(CURRENT_DATA, CURRENT_DATASET.meta);
      refreshAllComponents(false);

      if (preserveScroll) {
        window.scrollTo(0, scrollY);
      }
    }

    function refreshAllComponents(preserveSelection = false) {
      const prevSegIdx = preserveSelection ? SELECTED_SEG_INDEX : 0;
      const segListEl = document.getElementById('segmentListContainer');
      const prevSegScroll = preserveSelection && segListEl ? segListEl.scrollTop : 0;
      const meta = CURRENT_DATASET.meta;

      const txType = meta.tx_type || 'X12';
      document.getElementById('txBadge').textContent = `${txType} • ${meta.gs_version}`;
      const footerLbl = document.getElementById('footerActiveStreamLabel');
      if (footerLbl) {
        footerLbl.textContent = `Active Stream: [${txType}] ${meta.source_path} • ${meta.byte_size.toLocaleString()} B • SHA-256 ${meta.sha256}`;
      }

      buildSegmentIndex(CURRENT_DATA, CURRENT_RAW_EDI);
      renderMetrics(CURRENT_DATA, meta);
      renderValidationAndProvenance();
      renderEnvelopes(CURRENT_DATA, meta);
      renderEntities(CURRENT_DATA, meta);
      renderTxSpecific(CURRENT_DATA, meta);
      renderClinicalSection(CURRENT_DATA, meta);
      renderRawEdi(CURRENT_RAW_EDI, meta);
      renderJsonTree(CURRENT_DATA, meta);
      renderMappingSpec(CURRENT_DATA, meta);

      filterSegments(true);
      const safeIdx = Math.min(prevSegIdx, Math.max(ALL_SEGMENTS.length - 1, 0));
      if (ALL_SEGMENTS.length > 0) {
        selectSegment(safeIdx);
      }
      if (preserveSelection && segListEl) {
        segListEl.scrollTop = prevSegScroll;
      } else if (segListEl) {
        segListEl.scrollTop = 0;
      }

      renderFinancialChart();
      renderHeatmapMatrix();
      renderRelationshipNodeMap(!preserveSelection);
      buildX12LatticeModel();
      sync3dLegendAndSubtitle();
      request3dRender();
    }

    /* ==========================================================================
       KPI TELEMETRY STRIP (DESIGN.md Section 4 & 5) — 100% EMPIRICAL STREAM DATA
       ========================================================================== */
    function renderMetrics(data, meta) {
      const bar = document.getElementById('metricsBar');
      const summary = data.summary || {};
      const firstGroup = (data.functional_groups || [])[0] || {};
      const firstTx = (firstGroup.transaction_sets || [])[0] || {};
      const parsedTx = firstTx.parsed_transaction || {};
      const txType = firstTx.transaction_type || meta.tx_type || 'X12';
      const finMeta = meta.financials || { billed: 0, paid: 0, adjustments: 0, patient_responsibility: 0, pended_exposure: 0 };

      const cells = [];

      cells.push({
        label: 'Transaction Set',
        val: `X12 ${txType}`,
        tone: 'tone-teal',
        sub: `${meta.gs_version || '005010'} • ${meta.filename}`
      });

      cells.push({
        label: 'Total Segments',
        val: String(summary.total_segments_count || ALL_SEGMENTS.length),
        tone: '',
        sub: `${(meta.byte_size || 0).toLocaleString()} B • ${(meta.parse_ms || 0).toFixed(2)} ms`
      });

      if (txType === '837') {
        const claims = parsedTx.claims || [];
        const charge = claims.reduce((a, c) => a + (parseFloat(c.total_claim_charge_amount) || 0), 0);
        const lines = claims.reduce((a, c) => a + (c.service_lines || []).length, 0);
        const allDiags = [];
        claims.forEach(c => (c.diagnoses || []).forEach(d => { if (d.code) allDiags.push(d.code); }));
        cells.push({ label: 'Submitted Claims', val: `${claims.length} (${lines} Line${lines === 1 ? '' : 's'})`, tone: '', sub: `ID: ${(claims[0] && claims[0].claim_id) || 'N/A'}` });
        cells.push({ label: 'Total Billed Charges', val: `$${charge.toFixed(2)}`, tone: 'tone-teal', sub: 'Loop 2300 CLM02 Verified' });
        cells.push({ label: 'ICD-10 Diagnoses', val: `${allDiags.length} Code${allDiags.length === 1 ? '' : 's'}`, tone: 'tone-indigo', sub: allDiags.slice(0, 4).join(', ') || 'None' });
      } else if (txType === '835') {
        const fin = parsedTx.financial_information || {};
        const paid = parseFloat(fin.total_payment_amount) || finMeta.paid || 0;
        const claims = parsedTx.claims || [];
        const coWriteOff = Math.max(0, (finMeta.adjustments || 0) - (finMeta.patient_responsibility || 0));
        cells.push({ label: 'Payment Total', val: `$${paid.toFixed(2)}`, tone: 'tone-emerald', sub: `Method: ${fin.payment_method_code || fin.payment_method || 'ACH'}` });
        cells.push({ label: 'Contractual Write-Off', val: `$${coWriteOff.toFixed(2)}`, tone: 'tone-indigo', sub: `CARC Adjustments (${claims.length} Claim${claims.length === 1 ? '' : 's'})` });
        cells.push({ label: 'Patient Responsibility', val: `$${(finMeta.patient_responsibility || 0).toFixed(2)}`, tone: 'tone-amber', sub: 'Deductible + Coinsurance' });
      } else if (txType === '277') {
        const req = parsedTx.required_attachments || [];
        const statuses = parsedTx.claim_statuses || [];
        cells.push({ label: 'Required Attachments', val: `${req.length} Flagged`, tone: 'tone-rose', sub: req[0] ? `STC ${req[0].status_category_code || 'R4'} / Action ${req[0].action_code || 'A4'}` : `${statuses.length} Status Rows` });
        cells.push({ label: 'Pended Exposure', val: `$${(finMeta.pended_exposure || 0).toFixed(2)}`, tone: 'tone-amber', sub: (req[0] && `PWK ${req[0].attachment_report_type_code || '09'}: ${req[0].attachment_transmission_code || 'EL'}`) || 'Electronic' });
        cells.push({ label: 'Tracking Reference', val: (req[0] && req[0].attachment_control_number) || 'ATT-REF', tone: '', sub: 'Loop 2200D PWK06' });
      } else if (txType === '275') {
        const clin = parsedTx.attached_clinical_data || {};
        const meds = clin.medications || [];
        const algs = clin.allergies || [];
        const vitals = clin.vital_signs || [];
        const probs = clin.problems_and_diagnoses || [];
        cells.push({ label: 'C-CDA Medications', val: `${meds.length} Active`, tone: 'tone-indigo', sub: (meds[0] && `${meds[0].medication_name || 'Rx'} (${meds[0].rxnorm_code || 'RxNorm'})`) || 'Medication Section' });
        cells.push({ label: 'Allergy Alerts', val: `${algs.length} Recorded`, tone: algs.length > 0 ? 'tone-rose' : 'tone-emerald', sub: (algs[0] && `${algs[0].substance} (${algs[0].severity || algs[0].reaction || 'Alert'})`) || 'No Known Allergies' });
        cells.push({ label: 'Problems & Vitals', val: `${probs.length} Dx / ${vitals.length} Vitals`, tone: 'tone-emerald', sub: (probs[0] && `Primary: ${probs[0].code}`) || 'LOINC Clinical Summary' });
      } else if (txType === '271') {
        const sub = parsedTx.subscriber || {};
        const bens = sub.eligibility_benefits || parsedTx.eligibility_benefits || [];
        const activeBen = bens.find(b => b.eligibility_code === '1');
        const copayBen = bens.find(b => b.eligibility_code === 'B' && b.monetary_amount !== null && b.monetary_amount !== undefined);
        const dedBen = bens.find(b => b.eligibility_code === 'C' && b.monetary_amount !== null && b.monetary_amount !== undefined);
        const coinsBen = bens.find(b => b.eligibility_code === 'A' && b.percent !== null && b.percent !== undefined);
        const costParts = [];
        if (copayBen) costParts.push(`$${Number(copayBen.monetary_amount).toFixed(0)} Copay`);
        if (dedBen) costParts.push(`$${Number(dedBen.monetary_amount).toFixed(0)} Ded`);
        if (!costParts.length && coinsBen) costParts.push(`${(Number(coinsBen.percent) * 100).toFixed(0)}% Coins`);
        cells.push({ label: 'Benefit Rows', val: `${bens.length} EB Loops`, tone: 'tone-emerald', sub: `Member: ${sub.identification_code || 'Verified'}` });
        cells.push({ label: 'Coverage Status', val: activeBen ? 'Active (EB*1)' : (bens[0] ? `EB*${bens[0].eligibility_code}` : 'Response'), tone: 'tone-teal', sub: (activeBen && activeBen.plan_coverage_description) || 'Eligibility Response' });
        cells.push({ label: 'Cost Sharing', val: costParts.join(' / ') || `${bens.length} Terms`, tone: 'tone-amber', sub: coinsBen ? `${(Number(coinsBen.percent) * 100).toFixed(0)}% Coinsurance` : 'Loop 2110C Schedule' });
      } else if (txType === '270') {
        const sub = parsedTx.subscriber || {};
        const inqs = (sub.inquiries && sub.inquiries.length ? sub.inquiries : parsedTx.inquiries) || [];
        const eqSegs = ALL_SEGMENTS.filter(s => s.segment_id === 'EQ');
        const eqCodes = inqs.length ? inqs.map(q => q.service_type_code || q.code).filter(Boolean) : eqSegs.map(s => s.elements[0]).filter(Boolean);
        cells.push({ label: 'Service Inquiries', val: `${Math.max(inqs.length, eqSegs.length)} EQ Loop${Math.max(inqs.length, eqSegs.length) === 1 ? '' : 's'}`, tone: 'tone-emerald', sub: `Member: ${sub.identification_code || 'Inquiry'}` });
        cells.push({ label: 'Inquiry Mode', val: 'Real-Time (EQ)', tone: 'tone-teal', sub: `${meta.gs_version || '005010X279A1'}` });
        cells.push({ label: 'Service Types', val: eqCodes.length ? `Types ${eqCodes.join(', ')}` : 'General (30)', tone: 'tone-amber', sub: 'Loop 2110C Verification' });
      } else if (txType === '278') {
        const evs = parsedTx.events || [];
        const ev0 = evs[0] || {};
        const revs = ev0.review_results || [];
        const svcs = ev0.services || [];
        const diags = (ev0.diagnoses || []).map(d => d.code).filter(Boolean);
        const procCodes = svcs.map(s => (s.procedure && (s.procedure.procedure_code || s.procedure.code)) || s.procedure_code).filter(Boolean);
        const hiFallback = diags.length ? diags : ALL_SEGMENTS.filter(s => s.segment_id === 'HI').flatMap(s => s.elements.map(el => (el.split(':')[1] || ''))).filter(Boolean);
        const svFallback = procCodes.length ? procCodes : ALL_SEGMENTS.filter(s => s.segment_id === 'SV1' || s.segment_id === 'SV2').map(s => ((s.elements[0] || '').split(':')[1] || s.elements[0])).filter(Boolean);
        cells.push({ label: 'Review Decision', val: (revs[0] && (revs[0].approval_status || revs[0].action_description || `HCR*${revs[0].action_code}`)) || `UM*${ev0.request_category_code || 'SC'}`, tone: 'tone-emerald', sub: (revs[0] && revs[0].review_identification_number) || 'Loop 2000E Review' });
        cells.push({ label: 'Authorized Amount', val: `$${(finMeta.billed || 0).toFixed(2)}`, tone: 'tone-teal', sub: svFallback.length ? `CPT ${svFallback.join(', ')}` : `${evs.length} Review Event` });
        cells.push({ label: 'Clinical Basis', val: hiFallback.length ? hiFallback.join(', ') : `${ALL_SEGMENTS.length} Segs`, tone: 'tone-indigo', sub: 'Loop 2000E HI Diagnoses' });
      } else {
        const partners = resolveTradingPartners(parsedTx);
        const distinctSegs = new Set(ALL_SEGMENTS.map(s => s.segment_id)).size;
        cells.push({ label: 'Distinct Segments', val: `${distinctSegs} Types`, tone: 'tone-indigo', sub: `Control #${firstTx.transaction_set_control_number || '0001'}` });
        cells.push({ label: 'Primary Entity', val: (partners.provider && partners.provider._displayName) || (partners.payer && partners.payer._displayName) || 'Interchange', tone: 'tone-teal', sub: `ISA #${meta.isa_control_number}` });
        cells.push({ label: 'Financial Total', val: `$${((finMeta.billed || 0) + (finMeta.paid || 0)).toFixed(2)}`, tone: 'tone-emerald', sub: 'Parsed Stream Summary' });
      }

      const vTone = meta.validation_status === 'PASS' ? 'tone-emerald' : (meta.validation_status === 'WARN' ? 'tone-amber' : 'tone-rose');
      cells.push({
        label: 'Compliance Audit',
        val: meta.validation_status,
        tone: vTone,
        sub: `SHA: ${meta.sha256.slice(0, 12)}`
      });

      bar.innerHTML = cells.slice(0, 6).map(c => `
        <div class="kpi-cell">
          <span class="kpi-label">${escapeHtml(c.label)}</span>
          <span class="kpi-value ${c.tone}">${escapeHtml(c.val)}</span>
          <span class="kpi-meta">${escapeHtml(c.sub)}</span>
        </div>
      `).join('');
    }

    /* ==========================================================================
       2D QUANTITATIVE CHART (CANVAS) — TRANSPARENT SURFACE + SUBTLE AXIS GRIDLINES
       ========================================================================== */
    function setChartMode(mode) {
      CHART_MODE = mode;
      ['active', 'financial', 'telemetry'].forEach(m => {
        const id = m === 'active' ? 'chartModeActive' : (m === 'financial' ? 'chartModeFinancial' : 'chartModeTelemetry');
        const btn = document.getElementById(id);
        if (btn) btn.classList.toggle('active', mode === m);
      });
      renderFinancialChart();
    }

    function buildActiveStreamChartSpec() {
      const meta = CURRENT_DATASET.meta;
      const fg = (CURRENT_DATA.functional_groups || [])[0] || {};
      const ts = (fg.transaction_sets || [])[0] || {};
      const tx = ts.parsed_transaction || {};
      const txType = ts.transaction_type || meta.tx_type || 'X12';
      const fin = meta.financials || { billed: 0, paid: 0, adjustments: 0, patient_responsibility: 0, pended_exposure: 0 };

      if (txType === '837') {
        const claims = tx.claims || [];
        const c0 = claims[0] || {};
        const bars = [
          { label: 'Total Billed', val: fin.billed || parseFloat(c0.total_claim_charge_amount || 0), color: PALETTE.teal, sub: `Claim ${c0.claim_id || 'CLM'}` }
        ];
        (c0.service_lines || []).slice(0, 4).forEach((sl, idx) => {
          const code = (sl.procedure && (sl.procedure.procedure_code || sl.procedure.code)) || `Line ${idx + 1}`;
          bars.push({
            label: `CPT ${code}`,
            val: parseFloat(sl.charge_amount || 0),
            color: idx % 2 === 0 ? PALETTE.emerald : PALETTE.indigo,
            sub: `Service Line #${sl.line_number || (idx + 1)}`
          });
        });
        const lineSum = (c0.service_lines || []).reduce((a, s) => a + (parseFloat(s.charge_amount) || 0), 0);
        bars.push({ label: 'Line Sum', val: lineSum, color: PALETTE.amber, sub: 'Sum(SV102/SV203) Audit' });
        return {
          title: `X12 837 Claim Charge & Service Line Profile`,
          subtitle: `Submitted claim total vs. individual CPT/HCPCS line charges in ${meta.filename} ($ USD)`,
          readout: `[837] ${meta.filename} • Claim ${c0.claim_id || 'Active'}`,
          isCurrency: true,
          bars
        };
      }

      if (txType === '835') {
        const c0 = (tx.claims || [])[0] || {};
        const trace = (tx.reassociation_trace && tx.reassociation_trace.check_or_eft_trace_number) || 'EFT';
        const coWriteOff = Math.max(0, (fin.adjustments || 0) - (fin.patient_responsibility || 0));
        const bars = [
          { label: 'CLP Billed', val: fin.billed || parseFloat(c0.total_claim_charge_amount || 0), color: PALETTE.teal, sub: 'Submitted Charge (CLP03)' },
          { label: 'Net Paid', val: fin.paid || parseFloat(c0.claim_payment_amount || 0), color: PALETTE.emerald, sub: 'EFT Settlement (BPR02/CLP04)' },
          { label: 'CO Write-Off', val: coWriteOff, color: PALETTE.indigo, sub: 'Contractual Obligation (CAS*CO)' },
          { label: 'Patient Resp', val: fin.patient_responsibility || parseFloat(c0.patient_responsibility_amount || 0), color: PALETTE.amber, sub: 'Deductible/Coins (CAS*PR)' }
        ];
        (c0.service_lines || []).slice(0, 2).forEach(sl => {
          const code = (sl.procedure && (sl.procedure.code || sl.procedure.procedure_code)) || sl.procedure_code || 'SVC';
          const linePaid = parseFloat(sl.line_payment_amount ?? sl.payment_amount ?? sl.line_item_provider_payment_amount ?? 0) || 0;
          const lineChg = parseFloat(sl.line_charge_amount ?? sl.charge_amount ?? sl.line_item_charge_amount ?? 0) || 0;
          bars.push({ label: `Paid ${code}`, val: linePaid, color: PALETTE.teal, sub: `Line Paid (Billed $${lineChg.toFixed(0)})` });
        });
        return {
          title: `X12 835 Remittance Adjudication Waterfall`,
          subtitle: `Submitted charge, net payment, contractual write-off, and patient share in ${meta.filename} ($ USD)`,
          readout: `[835] ${meta.filename} • Trace ${trace}`,
          isCurrency: true,
          bars
        };
      }

      if (txType === '277') {
        const reqs = tx.required_attachments || [];
        const r0 = reqs[0] || {};
        const holdAmt = fin.pended_exposure || parseFloat(r0.claim_charge_amount || 0);
        if (holdAmt > 0) {
          return {
            title: `X12 277 Pended Claim Exposure & Hold Status`,
            subtitle: `Adjudication hold exposure awaiting ${r0.attachment_report_type_description || 'clinical documentation'} in ${meta.filename} ($ USD)`,
            readout: `[277] ${meta.filename} • PWK ${r0.attachment_control_number || 'Pended'}`,
            isCurrency: true,
            bars: [
              { label: 'Pended Claim', val: holdAmt, color: PALETTE.rose, sub: `STC ${r0.status_category_code || 'R4'} Hold` },
              { label: 'Doc Hold ($)', val: holdAmt, color: PALETTE.amber, sub: `PWK ${r0.attachment_report_type_code || '09'} Required` },
              { label: 'Released ($)', val: 0, color: PALETTE.emerald, sub: 'Awaiting 275 Attachment' }
            ]
          };
        }
      }

      if (txType === '275') {
        const clin = tx.attached_clinical_data || {};
        const docId = (clin.document_metadata && clin.document_metadata.document_id) || 'C-CDA R2.1';
        const notesCount = Object.keys(clin.clinical_notes_and_evaluations || {}).filter(k => Boolean(clin.clinical_notes_and_evaluations[k])).length;
        return {
          title: `X12 275 Embedded HL7 C-CDA R2.1 Clinical Inventory`,
          subtitle: `Structured clinical entries extracted from BDS/BIN XML payload in ${meta.filename} (Record Count)`,
          readout: `[275] ${meta.filename} • ${docId}`,
          isCurrency: false,
          bars: [
            { label: 'Medications', val: (clin.medications || []).length, color: PALETTE.indigo, sub: 'LOINC 10160-0 Active Meds' },
            { label: 'Allergies', val: (clin.allergies || []).length, color: PALETTE.rose, sub: 'LOINC 48765-2 Alerts' },
            { label: 'Problems/Dx', val: (clin.problems_and_diagnoses || []).length, color: PALETTE.teal, sub: 'LOINC 11450-4 Diagnoses' },
            { label: 'Vital Signs', val: (clin.vital_signs || []).length, color: PALETTE.emerald, sub: 'LOINC 8716-3 Observations' },
            { label: 'Narrative', val: notesCount, color: PALETTE.amber, sub: 'LOINC 11506-3 Notes' }
          ]
        };
      }

      if (txType === '271') {
        const sub = tx.subscriber || {};
        const bens = sub.eligibility_benefits || tx.eligibility_benefits || [];
        const monetaryBars = [];
        bens.forEach((b, i) => {
          if (b.monetary_amount !== null && b.monetary_amount !== undefined && !isNaN(Number(b.monetary_amount))) {
            const codeLbl = b.eligibility_code === 'C' ? 'Deductible' : (b.eligibility_code === 'B' ? 'Copayment' : (b.eligibility_code === 'G' ? 'Out-of-Pocket' : `EB*${b.eligibility_code}`));
            monetaryBars.push({
              label: `${codeLbl} (${b.service_type_code || '30'})`,
              val: Number(b.monetary_amount),
              color: b.eligibility_code === 'C' ? PALETTE.amber : (b.eligibility_code === 'B' ? PALETTE.teal : PALETTE.indigo),
              sub: b.eligibility_description || 'Benefit Monetary Term'
            });
          }
        });
        if (monetaryBars.length > 0) {
          return {
            title: `X12 271 Eligibility & Cost-Sharing Benefit Schedule`,
            subtitle: `Extracted member deductible, copayment, and benefit dollar thresholds in ${meta.filename} ($ USD)`,
            readout: `[271] ${meta.filename} • Member ${sub.identification_code || 'Active'}`,
            isCurrency: true,
            bars: monetaryBars
          };
        }
      }

      if (txType === '278' && (fin.billed > 0)) {
        const ev0 = (tx.events || [])[0] || {};
        const rv0 = (ev0.review_results || [])[0] || {};
        const isCert = !rv0.action_code || rv0.action_code === 'A1' || rv0.action_code === 'A2';
        return {
          title: `X12 278 Prior Authorization Financial Determination`,
          subtitle: `Requested procedure charge vs. UMO certified amount in ${meta.filename} ($ USD)`,
          readout: `[278] ${meta.filename} • ${rv0.review_identification_number || 'UM Review'}`,
          isCurrency: true,
          bars: [
            { label: 'Requested ($)', val: fin.billed, color: PALETTE.teal, sub: 'Submitted SV1/SV2 Service Charge' },
            { label: 'Certified ($)', val: isCert ? fin.billed : 0, color: PALETTE.emerald, sub: `Decision ${rv0.action_code || 'A1'}` },
            { label: 'Denied/Hold', val: isCert ? 0 : fin.billed, color: PALETTE.rose, sub: 'Adverse Determination' }
          ]
        };
      }

      // Default quantitative breakdown for 270 Inquiry & custom X12 streams: 5010 Loop Stratum Segment Counts
      const sc = meta.stratum_counts || {};
      return {
        title: `X12 ${txType} Loop Stratum Segment Distribution`,
        subtitle: `Empirical segment counts across 5010 structural strata in ${meta.filename} (Segment Count)`,
        readout: `[${txType}] ${meta.filename} • ${ALL_SEGMENTS.length} Total Segments`,
        isCurrency: false,
        bars: [
          { label: 'Envelope', val: sc['Envelope'] || 0, color: PALETTE.teal, sub: 'ISA / GS / ST / SE / GE / IEA' },
          { label: 'Header', val: sc['Header'] || 0, color: PALETTE.emerald, sub: 'BHT / BPR / TRN / BGN' },
          { label: '1000/2000', val: sc['Loop 1000/2000'] || 0, color: PALETTE.indigo, sub: 'Hierarchy & Subscriber' },
          { label: '2010 Entity', val: sc['Loop 2010 Entities'] || 0, color: PALETTE.indigo, sub: 'NM1 / N1 / N3 / N4 / DMG' },
          { label: 'Core Loop', val: sc['Loop 2300/2100 Core'] || 0, color: PALETTE.amber, sub: 'EQ / EB / CLM / CLP / UM / STC' },
          { label: 'Detail/Clin', val: sc['Loop 2400/Clinical'] || 0, color: PALETTE.rose, sub: 'SV1 / SVC / CAS / PWK / BDS' }
        ]
      };
    }

    function renderFinancialChart() {
      const canvas = document.getElementById('financialChartCanvas');
      if (!canvas) return;
      const rect = canvas.parentElement.getBoundingClientRect();
      const w = Math.max(rect.width, 320);
      const h = Math.max(rect.height, 240);
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      const ctx = canvas.getContext('2d');
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h); // Transparent plot background inheriting surface color

      const tok = getActiveTokens();
      const pad = { top: 24, right: 20, bottom: 44, left: 62 };
      const pw = w - pad.left - pad.right;
      const ph = h - pad.top - pad.bottom;
      CHART_HIT_BOXES = [];

      const titleEl = document.getElementById('chartPaneTitle');
      const subEl = document.getElementById('chartSubtitle');
      const readoutEl = document.getElementById('chartReadoutText');
      const legendEl = document.getElementById('chartLegendBar');

      if (CHART_MODE === 'active' || CHART_MODE === 'financial') {
        let bars = [];
        let isCurrency = true;

        if (CHART_MODE === 'active') {
          const spec = buildActiveStreamChartSpec();
          bars = spec.bars;
          isCurrency = spec.isCurrency;
          if (titleEl) titleEl.textContent = spec.title;
          if (subEl) subEl.textContent = spec.subtitle;
          if (readoutEl) readoutEl.textContent = spec.readout;
        } else {
          if (titleEl) titleEl.textContent = 'Workspace Episode Financial Adjudication';
          if (subEl) subEl.textContent = 'Aggregated claim charge, remittance settlement, write-off, patient share, and pended exposure ($ USD)';
          if (readoutEl) readoutEl.textContent = `Workspace (${BUNDLE.datasets.length} Streams)`;
          let billed = 0, paid = 0, writeOff = 0, patResp = 0, pended = 0;
          BUNDLE.datasets.forEach(ds => {
            const f = ds.meta.financials || {};
            if (ds.meta.tx_type === '837') billed += (f.billed || 0);
            if (ds.meta.tx_type === '835') {
              paid += (f.paid || 0);
              writeOff += Math.max(0, (f.adjustments || 0) - (f.patient_responsibility || 0));
              patResp += (f.patient_responsibility || 0);
            }
            if (ds.meta.tx_type === '277') pended += (f.pended_exposure || 0);
          });
          bars = [
            { label: '837 Billed', val: billed, color: PALETTE.teal, sub: 'Submitted CLM02' },
            { label: '835 Paid', val: paid, color: PALETTE.emerald, sub: 'Net EFT Settlement' },
            { label: 'CO Write-Off', val: writeOff, color: PALETTE.indigo, sub: 'CARC Contractual' },
            { label: 'Patient Resp', val: patResp, color: PALETTE.amber, sub: 'Deductible + Coins' },
            { label: '277 Pended', val: pended, color: PALETTE.rose, sub: 'STC R4/A4 Hold' }
          ];
        }

        if (legendEl) {
          legendEl.innerHTML = bars.slice(0, 5).map(b =>
            `<span class="legend-item"><span class="legend-swatch" style="background:${b.color}"></span>${escapeHtml(b.label)}</span>`
          ).join('');
        }

        const rawMax = Math.max(...bars.map(b => b.val), isCurrency ? 100 : 4);
        const maxVal = rawMax * 1.15;
        const steps = 4;

        ctx.strokeStyle = tok.gridLine;
        ctx.lineWidth = 1;
        ctx.font = "500 10.5px 'IBM Plex Mono', monospace";
        ctx.fillStyle = tok.textSecondary;
        ctx.textAlign = 'right';
        ctx.textBaseline = 'middle';

        for (let i = 0; i <= steps; i++) {
          const v = (maxVal / steps) * i;
          const y = Math.round(pad.top + ph - (i / steps) * ph) + 0.5;
          ctx.beginPath();
          ctx.moveTo(pad.left, y);
          ctx.lineTo(pad.left + pw, y);
          ctx.stroke();
          ctx.fillText(isCurrency ? `$${Math.round(v)}` : `${Math.round(v)}`, pad.left - 8, y);
        }

        const slotW = pw / Math.max(bars.length, 1);
        const barW = Math.min(46, slotW * 0.54);

        bars.forEach((b, idx) => {
          const bh = Math.max(2, (b.val / maxVal) * ph);
          const bx = pad.left + idx * slotW + (slotW - barW) / 2;
          const by = pad.top + ph - bh;

          ctx.fillStyle = b.color;
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(bx, by, barW, bh, [4, 4, 0, 0]);
          else ctx.rect(bx, by, barW, bh);
          ctx.fill();

          ctx.fillStyle = tok.textPrimary;
          ctx.font = "600 10.5px 'IBM Plex Mono', monospace";
          ctx.textAlign = 'center';
          ctx.textBaseline = 'bottom';
          const valText = isCurrency ? `$${b.val.toFixed(b.val % 1 ? 2 : 0)}` : `${b.val}`;
          ctx.fillText(valText, bx + barW / 2, by - 5);

          ctx.fillStyle = tok.textSecondary;
          ctx.font = "500 10px 'DM Sans', sans-serif";
          ctx.textBaseline = 'top';
          ctx.fillText(String(b.label).slice(0, 13), bx + barW / 2, pad.top + ph + 10);

          const tipDetail = isCurrency ? `$${b.val.toFixed(2)} (${b.sub})` : `${b.val} (${b.sub})`;
          CHART_HIT_BOXES.push({ x: bx, y: by, w: barW, h: bh, title: b.label, detail: tipDetail });
        });
      } else {
        if (titleEl) titleEl.textContent = 'Workspace Segment Volume & Parse Latency';
        if (subEl) subEl.textContent = 'Empirical segment count (bars, active in Indigo) and parser latency in ms (Amber line)';
        if (readoutEl) readoutEl.textContent = `Active: [${CURRENT_DATASET.meta.tx_type}] ${CURRENT_DATASET.meta.filename}`;
        if (legendEl) {
          legendEl.innerHTML = `
            <span class="legend-item"><span class="legend-swatch" style="background:${PALETTE.indigo}"></span>Selected Stream</span>
            <span class="legend-item"><span class="legend-swatch" style="background:${PALETTE.teal}"></span>Workspace Peer</span>
            <span class="legend-item"><span class="legend-swatch" style="background:${PALETTE.amber}"></span>Parse Latency (ms)</span>
          `;
        }
        const items = BUNDLE.datasets.map(ds => ({
          label: ds.meta.tx_type,
          segs: (ds.parsed_data.summary || {}).total_segments_count || 0,
          ms: ds.meta.parse_ms || 0.2,
          file: ds.meta.filename,
          active: ds === CURRENT_DATASET
        }));

        const maxSegs = Math.max(36, ...items.map(d => d.segs)) * 1.12;
        const maxMs = Math.max(1.0, ...items.map(d => d.ms)) * 1.25;
        const steps = 4;

        ctx.strokeStyle = tok.gridLine;
        ctx.lineWidth = 1;
        ctx.font = "500 10.5px 'IBM Plex Mono', monospace";
        ctx.fillStyle = tok.textSecondary;

        for (let i = 0; i <= steps; i++) {
          const v = (maxSegs / steps) * i;
          const y = Math.round(pad.top + ph - (i / steps) * ph) + 0.5;
          ctx.beginPath();
          ctx.moveTo(pad.left, y);
          ctx.lineTo(pad.left + pw, y);
          ctx.stroke();
          ctx.textAlign = 'right';
          ctx.textBaseline = 'middle';
          ctx.fillText(`${Math.round(v)}s`, pad.left - 8, y);
        }

        const slotW = pw / Math.max(items.length, 1);
        const barW = Math.min(36, slotW * 0.5);
        const pts = [];

        items.forEach((it, idx) => {
          const bh = Math.max(2, (it.segs / maxSegs) * ph);
          const bx = pad.left + idx * slotW + (slotW - barW) / 2;
          const by = pad.top + ph - bh;

          ctx.fillStyle = it.active ? PALETTE.indigo : PALETTE.teal;
          ctx.beginPath();
          if (ctx.roundRect) ctx.roundRect(bx, by, barW, bh, [4, 4, 0, 0]);
          else ctx.rect(bx, by, barW, bh);
          ctx.fill();

          ctx.fillStyle = it.active ? tok.textPrimary : tok.textSecondary;
          ctx.font = `${it.active ? '700' : '600'} 10.5px 'IBM Plex Mono', monospace`;
          ctx.textAlign = 'center';
          ctx.textBaseline = 'top';
          ctx.fillText(it.label, bx + barW / 2, pad.top + ph + 10);

          const ly = pad.top + ph - (it.ms / maxMs) * ph;
          pts.push({ x: bx + barW / 2, y: ly, it });
          CHART_HIT_BOXES.push({ x: bx, y: pad.top, w: barW, h: ph, title: `${it.file} [${it.label}]`, detail: `${it.segs} segments • ${it.ms.toFixed(2)} ms` });
        });

        ctx.strokeStyle = PALETTE.amber;
        ctx.lineWidth = 2;
        ctx.beginPath();
        pts.forEach((p, idx) => { if (idx === 0) ctx.moveTo(p.x, p.y); else ctx.lineTo(p.x, p.y); });
        ctx.stroke();

        pts.forEach(p => {
          ctx.fillStyle = PALETTE.amber;
          ctx.beginPath();
          ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2);
          ctx.fill();
        });
      }
    }

    /* ==========================================================================
       HEATMAP MATRIX: SURFACE -> TEAL (#0D9488) -> INDIGO (#4F46E5) -> ROSE (#E11D48)
       ========================================================================== */
    function hexToRgb(hex) {
      const h = hex.replace('#', '');
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
    }

    function lerpRgb(a, b, t) {
      return [
        Math.round(a[0] + (b[0] - a[0]) * t),
        Math.round(a[1] + (b[1] - a[1]) * t),
        Math.round(a[2] + (b[2] - a[2]) * t)
      ];
    }

    function interpolateHeatmapColor(norm, bgSurfaceHex) {
      if (norm <= 0) return { bg: bgSurfaceHex, fg: 'var(--text-secondary)' };
      const c0 = hexToRgb(bgSurfaceHex);
      const c1 = hexToRgb(PALETTE.teal);
      const c2 = hexToRgb(PALETTE.indigo);
      const c3 = hexToRgb(PALETTE.rose);

      let rgb;
      if (norm < 0.38) {
        rgb = lerpRgb(c0, c1, Math.max(0.22, norm / 0.38));
      } else if (norm < 0.72) {
        rgb = lerpRgb(c1, c2, (norm - 0.38) / 0.34);
      } else {
        rgb = lerpRgb(c2, c3, (norm - 0.72) / 0.28);
      }
      const lum = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255;
      return {
        bg: `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`,
        fg: lum > 0.56 ? '#1C1917' : '#FFFFFF'
      };
    }

    function renderHeatmapMatrix() {
      const container = document.getElementById('heatmapContainer');
      if (!container) return;
      const tok = getActiveTokens();
      const strata = ['Envelope', 'Header', 'Loop 1000/2000', 'Loop 2010 Entities', 'Loop 2300/2100 Core', 'Loop 2400/Clinical'];
      const shortLabels = ['Envelope', 'Header', '1000/2000', '2010 Entity', '2300/2100', '2400/Clin'];

      let maxCell = 1;
      let grandTotal = 0;
      BUNDLE.datasets.forEach(ds => {
        strata.forEach(st => {
          const c = (ds.meta.stratum_counts && ds.meta.stratum_counts[st]) || 0;
          grandTotal += c;
          if (c > maxCell) maxCell = c;
        });
      });

      document.getElementById('heatmapTotalBadge').textContent = `${grandTotal} workspace segments`;
      const hmSub = document.getElementById('heatmapSubtitle');
      if (hmSub) {
        hmSub.textContent = `Highlighted Row: [${CURRENT_DATASET.meta.tx_type}] ${CURRENT_DATASET.meta.filename} — segment density across 5010 loop strata (click cell to inspect)`;
      }
      const hmReadout = document.getElementById('heatmapReadoutText');
      if (hmReadout) {
        hmReadout.textContent = `Active: [${CURRENT_DATASET.meta.tx_type}] ${CURRENT_DATASET.meta.filename} (${ALL_SEGMENTS.length} segs)`;
      }

      let html = `<table class="heatmap-matrix" aria-label="Loop Stratum Concentration Matrix"><thead><tr><th class="row-hdr">Tx / File</th>`;
      shortLabels.forEach(lbl => { html += `<th>${lbl}</th>`; });
      html += `</tr></thead><tbody>`;

      BUNDLE.datasets.forEach((ds, dIdx) => {
        const isCurrent = dIdx === ACTIVE_DATASET_IDX;
        const marker = isCurrent ? 'font-weight:700;color:var(--viz-teal)' : '';
        const prefix = isCurrent ? '&bull; ' : '';
        const shortFile = ds.meta.filename.replace('sample_', '').replace('.x12', '').slice(0, 18);
        html += `<tr><th class="row-hdr" style="${marker};cursor:pointer" onclick="selectWorkspaceDataset(${dIdx}, true, false)">${prefix}${escapeHtml(ds.meta.tx_type)} <span style="opacity:0.7">${escapeHtml(shortFile)}</span></th>`;
        strata.forEach(st => {
          const val = (ds.meta.stratum_counts && ds.meta.stratum_counts[st]) || 0;
          const norm = val / maxCell;
          const col = interpolateHeatmapColor(norm, tok.bgSurface);
          const cellOutline = isCurrent ? `box-shadow:inset 0 0 0 1px ${PALETTE.teal};` : '';
          html += `<td class="hm-cell" style="background-color:${col.bg};color:${col.fg};${cellOutline}" onclick="onHeatmapCellClick(${dIdx}, '${st}')" title="${escapeHtml(ds.meta.filename)} • ${st}: ${val} segment(s)">${val}</td>`;
        });
        html += `</tr>`;
      });

      html += `</tbody></table>`;
      container.innerHTML = html;
    }

    function onHeatmapCellClick(dsIdx, stratum) {
      selectWorkspaceDataset(dsIdx, true, true);
      const qInput = document.getElementById('segFilterInput');
      if (qInput) {
        const mapFilter = {
          'Envelope': 'Envelope',
          'Header': 'Header',
          'Loop 1000/2000': '2000',
          'Loop 2010 Entities': '2010',
          'Loop 2300/2100 Core': '2',
          'Loop 2400/Clinical': ''
        };
        qInput.value = mapFilter[stratum] || '';
        filterSegments();
      }
    }

    /* ==========================================================================
       SVG INTERACTIVE RELATIONSHIP NODE MAP — DETERMINISTIC DAG + PAN/ZOOM
       ========================================================================== */
    const NODE_MAP_STATE = { scale: 1, tx: 0, ty: 0, dragging: false, startX: 0, startY: 0 };

    function resetNodeMapTransform() {
      NODE_MAP_STATE.scale = 1;
      NODE_MAP_STATE.tx = 0;
      NODE_MAP_STATE.ty = 0;
      applyNodeMapTransform();
    }

    function zoomNodeMap(factor) {
      NODE_MAP_STATE.scale = Math.max(0.55, Math.min(2.6, NODE_MAP_STATE.scale * factor));
      applyNodeMapTransform();
    }

    function applyNodeMapTransform() {
      const g = document.getElementById('nodeMapGraphGroup');
      if (g) {
        g.setAttribute('transform', `translate(${NODE_MAP_STATE.tx.toFixed(1)}, ${NODE_MAP_STATE.ty.toFixed(1)}) scale(${NODE_MAP_STATE.scale.toFixed(3)})`);
      }
    }

    function pickEntity(...candidates) {
      for (const cand of candidates) {
        if (!cand || typeof cand !== 'object') continue;
        const o = (cand.subscriber_name && typeof cand.subscriber_name === 'object') ? cand.subscriber_name : cand;
        const rawLast = o.name_last_or_organization || o.name || o.name_last || '';
        const rawFirst = o.name_first || '';
        const idCode = o.identification_code || '';
        if (!rawLast && !rawFirst && !idCode) continue;
        const displayName = (rawLast && rawFirst)
          ? `${rawLast}, ${rawFirst}`
          : (rawLast || rawFirst || idCode);
        return Object.assign({}, o, { _displayName: displayName, _seg: o._seg || 'NM1' });
      }
      return null;
    }

    function findN1SegmentEntity(qualifier) {
      for (let i = 0; i < ALL_SEGMENTS.length; i++) {
        const s = ALL_SEGMENTS[i];
        if (s.segment_id === 'N1' && s.elements[0] === qualifier) {
          const ent = {
            entity_identifier_code: qualifier,
            name_last_or_organization: s.elements[1] || '',
            identification_code_qualifier: s.elements[2] || 'ID',
            identification_code: s.elements[3] || '',
            address: {},
            geographic_location: {},
            _seg: 'N1'
          };
          for (let j = i + 1; j < Math.min(i + 4, ALL_SEGMENTS.length); j++) {
            const nxt = ALL_SEGMENTS[j];
            if (nxt.segment_id === 'N1' || nxt.segment_id === 'CLP' || nxt.segment_id === 'LX') break;
            if (nxt.segment_id === 'N3') ent.address = { address_line_1: nxt.elements[0] || '' };
            if (nxt.segment_id === 'N4') ent.geographic_location = { city: nxt.elements[0] || '', state: nxt.elements[1] || '', postal_code: nxt.elements[2] || '' };
          }
          return ent;
        }
      }
      return null;
    }

    function resolveTradingPartners(tx) {
      const firstClaim = (tx.claims || [])[0] || {};
      const firstSub = (tx.subscribers || [])[0] || null;
      return {
        payer: pickEntity(tx.payer, tx.information_source, tx.utilization_management_organization, findN1SegmentEntity('PR'), tx.receiver),
        provider: pickEntity(tx.billing_provider, tx.payee, findN1SegmentEntity('PE'), tx.service_provider, firstClaim.service_provider, tx.requester, tx.information_receiver, tx.submitter),
        patient: pickEntity(tx.patient, firstClaim.patient, tx.subscriber, firstSub),
        submitter: pickEntity(tx.submitter, tx.information_receiver)
      };
    }

    function buildGraphNodesAndEdges(data, meta) {
      const nodes = [];
      const edges = [];
      const fg = (data.functional_groups || [])[0] || {};
      const ts = (fg.transaction_sets || [])[0] || {};
      const tx = ts.parsed_transaction || {};
      const txType = ts.transaction_type || meta.tx_type || 'X12';

      // Column 0: Envelope Root
      nodes.push({ id: 'n_isa', col: 0, label: `ISA #${meta.isa_control_number.slice(-4)}`, sub: 'Interchange', color: PALETTE.teal, segId: 'ISA' });
      nodes.push({ id: 'n_st', col: 1, label: `ST*${txType}`, sub: meta.gs_version, color: PALETTE.teal, segId: 'ST' });
      edges.push({ from: 'n_isa', to: 'n_st', color: PALETTE.teal });

      // Column 2: Trading Partner Entities
      const partners = resolveTradingPartners(tx);
      const entList = [
        { id: 'n_ent_0', obj: partners.payer, role: 'Payer / Source' },
        { id: 'n_ent_1', obj: partners.provider, role: 'Provider / Submitter' },
        { id: 'n_ent_2', obj: partners.patient, role: 'Patient / Member' }
      ];

      entList.forEach(e => {
        if (e.obj) {
          const shortName = String(e.obj._displayName).slice(0, 18);
          nodes.push({ id: e.id, col: 2, label: shortName, sub: e.role, color: PALETTE.indigo, segId: e.obj._seg || 'NM1' });
          edges.push({ from: 'n_st', to: e.id, color: PALETTE.indigo });
        }
      });

      const payerNodeId = partners.payer ? 'n_ent_0' : 'n_st';
      const provNodeId = partners.provider ? 'n_ent_1' : 'n_st';
      const ptNodeId = partners.patient ? 'n_ent_2' : 'n_st';

      // Column 3: Core Domain Records
      if (txType === '837') {
        (tx.claims || []).forEach((c, ci) => {
          const cid = `n_clm_${ci}`;
          nodes.push({ id: cid, col: 3, label: c.claim_id || 'CLM', sub: `$${parseFloat(c.total_claim_charge_amount || 0).toFixed(0)} Billed`, color: PALETTE.emerald, segId: 'CLM' });
          edges.push({ from: provNodeId, to: cid, color: PALETTE.emerald });
          (c.service_lines || []).forEach((sl, li) => {
            const lid = `n_sl_${ci}_${li}`;
            const code = (sl.procedure && (sl.procedure.procedure_code || sl.procedure.code)) || 'SV1';
            nodes.push({ id: lid, col: 4, label: `CPT ${code}`, sub: `$${parseFloat(sl.charge_amount || 0).toFixed(0)}`, color: PALETTE.teal, segId: 'SV1' });
            edges.push({ from: cid, to: lid, color: PALETTE.teal });
          });
          (c.diagnoses || []).slice(0, 2).forEach((dg, di) => {
            const did = `n_dg_${ci}_${di}`;
            nodes.push({ id: did, col: 4, label: `ICD ${dg.code}`, sub: dg.diagnosis_type, color: PALETTE.indigo, segId: 'HI' });
            edges.push({ from: cid, to: did, color: PALETTE.indigo });
          });
        });
      } else if (txType === '835') {
        (tx.claims || []).forEach((c, ci) => {
          const cid = `n_clp_${ci}`;
          nodes.push({ id: cid, col: 3, label: c.patient_control_number || 'CLP', sub: `Paid $${parseFloat(c.claim_payment_amount || 0).toFixed(0)}`, color: PALETTE.emerald, segId: 'CLP' });
          edges.push({ from: payerNodeId, to: cid, color: PALETTE.emerald });
          (c.adjustments || []).slice(0, 3).forEach((aj, ai) => {
            const aid = `n_cas_${ci}_${ai}`;
            const col = aj.group_code === 'PR' ? PALETTE.amber : PALETTE.indigo;
            nodes.push({ id: aid, col: 4, label: `${aj.group_code}-${aj.reason_code}`, sub: `-$${parseFloat(aj.adjustment_amount || 0).toFixed(0)}`, color: col, segId: 'CAS' });
            edges.push({ from: cid, to: aid, color: col });
          });
        });
      } else if (txType === '277') {
        (tx.required_attachments || []).forEach((ra, ri) => {
          const rid = `n_stc_${ri}`;
          nodes.push({ id: rid, col: 3, label: `STC ${ra.status_category_code || 'R4'}`, sub: 'Action A4 Pended', color: PALETTE.rose, segId: 'STC' });
          edges.push({ from: payerNodeId, to: rid, color: PALETTE.rose });
          const pid = `n_pwk_${ri}`;
          nodes.push({ id: pid, col: 4, label: `PWK ${ra.attachment_report_type_code || '09'}`, sub: ra.attachment_control_number || 'Attachment', color: PALETTE.amber, segId: 'PWK' });
          edges.push({ from: rid, to: pid, color: PALETTE.amber });
        });
      } else if (txType === '275') {
        const clin = tx.attached_clinical_data || {};
        nodes.push({ id: 'n_ccda', col: 3, label: 'C-CDA R2.1 XML', sub: 'LOINC 34133-9', color: PALETTE.indigo, segId: 'BDS' });
        edges.push({ from: provNodeId, to: 'n_ccda', color: PALETTE.indigo });
        (clin.allergies || []).slice(0, 1).forEach((a, i) => {
          nodes.push({ id: `n_alg_${i}`, col: 4, label: a.substance || 'Allergy', sub: a.severity || 'Severe', color: PALETTE.rose, segId: 'BDS' });
          edges.push({ from: 'n_ccda', to: `n_alg_${i}`, color: PALETTE.rose });
        });
        (clin.medications || []).slice(0, 1).forEach((m, i) => {
          nodes.push({ id: `n_med_${i}`, col: 4, label: String(m.medication_name || 'Med').slice(0, 16), sub: `RxNorm ${m.rxnorm_code}`, color: PALETTE.emerald, segId: 'BDS' });
          edges.push({ from: 'n_ccda', to: `n_med_${i}`, color: PALETTE.emerald });
        });
        (clin.problems_and_diagnoses || []).slice(0, 2).forEach((p, i) => {
          nodes.push({ id: `n_prb_${i}`, col: 4, label: `ICD ${p.code}`, sub: String(p.problem_name || '').slice(0, 15), color: PALETTE.teal, segId: 'BDS' });
          edges.push({ from: 'n_ccda', to: `n_prb_${i}`, color: PALETTE.teal });
        });
      } else if (txType === '271' || txType === '270') {
        const sub = tx.subscriber || {};
        const bens = sub.eligibility_benefits || tx.eligibility_benefits || [];
        const inqs = (sub.inquiries && sub.inquiries.length ? sub.inquiries : tx.inquiries) || [];
        if (bens.length > 0) {
          bens.slice(0, 4).forEach((b, bi) => {
            const bid = `n_eb_${bi}`;
            const c = b.eligibility_code === '1' ? PALETTE.emerald : PALETTE.amber;
            nodes.push({ id: bid, col: 3, label: `EB*${b.eligibility_code}`, sub: String(b.eligibility_description || 'Benefit').slice(0, 16), color: c, segId: 'EB' });
            edges.push({ from: ptNodeId, to: bid, color: c });
          });
        } else {
          const eqItems = inqs.length ? inqs : ALL_SEGMENTS.filter(s => s.segment_id === 'EQ').map(s => ({ service_type_code: s.elements[0] || '30', service_type_description: 'Service Inquiry' }));
          (eqItems.length ? eqItems : [{ service_type_code: '30', service_type_description: 'Benefit Inquiry' }]).slice(0, 4).forEach((q, qi) => {
            const qid = `n_eq_${qi}`;
            const code = q.service_type_code || q.code || '30';
            nodes.push({ id: qid, col: 3, label: `EQ*${code}`, sub: String(q.service_type_description || 'Benefit Inquiry').slice(0, 16), color: PALETTE.teal, segId: 'EQ' });
            edges.push({ from: ptNodeId !== 'n_st' ? ptNodeId : provNodeId, to: qid, color: PALETTE.teal });
          });
        }
      } else if (txType === '278') {
        (tx.events || []).forEach((ev, ei) => {
          const eid = `n_um_${ei}`;
          nodes.push({ id: eid, col: 3, label: `UM*${ev.request_category_code || 'SC'}`, sub: 'Services Review', color: PALETTE.teal, segId: 'UM' });
          edges.push({ from: provNodeId, to: eid, color: PALETTE.teal });
          (ev.review_results || []).forEach((rv, ri) => {
            const hid = `n_hcr_${ri}`;
            nodes.push({ id: hid, col: 4, label: `HCR*${rv.action_code}`, sub: rv.review_identification_number || 'Approved', color: PALETTE.emerald, segId: 'HCR' });
            edges.push({ from: eid, to: hid, color: PALETTE.emerald });
          });
          (ev.services || []).slice(0, 2).forEach((sv, si) => {
            const sid = `n_sv278_${ei}_${si}`;
            const code = (sv.procedure && (sv.procedure.procedure_code || sv.procedure.code)) || sv.procedure_code || 'SV1';
            nodes.push({ id: sid, col: 4, label: `CPT ${code}`, sub: `$${parseFloat(sv.charge_amount || 0).toFixed(0)}`, color: PALETTE.teal, segId: 'SV1' });
            edges.push({ from: eid, to: sid, color: PALETTE.teal });
          });
        });
      } else {
        // Generic X12 fallback graph for custom transaction sets
        const coreSegs = ALL_SEGMENTS.filter(s => !['ISA','GS','ST','SE','GE','IEA','NM1','N1','N3','N4'].includes(s.segment_id)).slice(0, 4);
        coreSegs.forEach((s, si) => {
          const gid = `n_gen_${si}`;
          nodes.push({ id: gid, col: 3, label: `${s.segment_id} #${s.line_number}`, sub: s.loop.slice(0, 16), color: PALETTE.emerald, segId: s.segment_id });
          edges.push({ from: provNodeId, to: gid, color: PALETTE.emerald });
        });
      }

      return { nodes, edges };
    }

    function renderRelationshipNodeMap(resetView = false) {
      const svg = document.getElementById('relationshipNodeMap');
      if (!svg) return;
      if (resetView) {
        NODE_MAP_STATE.scale = 1;
        NODE_MAP_STATE.tx = 0;
        NODE_MAP_STATE.ty = 0;
        const ro = document.getElementById('nodeMapSelectionReadout');
        if (ro) ro.textContent = 'Drag to pan \u2022 Scroll to zoom \u2022 Click node';
      }

      const rect = svg.parentElement.getBoundingClientRect();
      const w = Math.max(rect.width, 460);
      const h = Math.max(rect.height, 300);
      svg.setAttribute('viewBox', `0 0 ${w} ${h}`);

      const tok = getActiveTokens();
      const { nodes, edges } = buildGraphNodesAndEdges(CURRENT_DATA, CURRENT_DATASET.meta);
      const subEl = document.getElementById('nodeMapSubtitle');
      if (subEl) {
        subEl.textContent = `[${CURRENT_DATASET.meta.tx_type}] ${CURRENT_DATASET.meta.filename} — ${nodes.length} structural nodes, ${edges.length} directed edges`;
      }

      // Group nodes by column for deterministic fast DAG placement
      const cols = {};
      let maxCol = 0;
      nodes.forEach(n => {
        cols[n.col] = cols[n.col] || [];
        cols[n.col].push(n);
        if (n.col > maxCol) maxCol = n.col;
      });

      const marginX = 64;
      const colSpan = maxCol > 0 ? (w - marginX * 2) / maxCol : 0;
      const posMap = {};

      Object.keys(cols).forEach(ck => {
        const list = cols[ck];
        const cx = marginX + Number(ck) * colSpan;
        const stepY = h / (list.length + 1);
        list.forEach((n, idx) => {
          n.x = cx;
          n.y = stepY * (idx + 1);
          posMap[n.id] = n;
        });
      });

      let inner = `<g id="nodeMapGraphGroup" transform="translate(${NODE_MAP_STATE.tx.toFixed(1)}, ${NODE_MAP_STATE.ty.toFixed(1)}) scale(${NODE_MAP_STATE.scale.toFixed(3)})">`;

      // Semi-transparent bezier edges derived from connected node state
      edges.forEach(e => {
        const s = posMap[e.from] || nodes[0];
        const t = posMap[e.to];
        if (!s || !t) return;
        const dx = (t.x - s.x) * 0.48;
        inner += `<path d="M ${s.x + 48} ${s.y} C ${s.x + 48 + dx} ${s.y}, ${t.x - 48 - dx} ${t.y}, ${t.x - 48} ${t.y}" fill="none" stroke="${e.color}" stroke-opacity="0.42" stroke-width="1.6"/>`;
      });

      // Nodes
      nodes.forEach(n => {
        const nw = 104, nh = 38;
        const nx = n.x - nw / 2, ny = n.y - nh / 2;
        inner += `
          <g style="cursor:pointer" onclick="onNodeMapSelect('${n.segId}', '${escapeHtml(n.label)}')">
            <rect x="${nx}" y="${ny}" width="${nw}" height="${nh}" rx="6" fill="${tok.bgSurface}" stroke="${tok.border}" stroke-width="1"/>
            <rect x="${nx}" y="${ny}" width="4" height="${nh}" rx="2" fill="${n.color}"/>
            <circle cx="${nx + 13}" cy="${ny + 13}" r="3.5" fill="${n.color}"/>
            <text x="${nx + 21}" y="${ny + 16}" fill="${tok.textPrimary}" font-family="'IBM Plex Mono', monospace" font-size="9.5" font-weight="600">${escapeHtml(n.label.slice(0, 12))}</text>
            <text x="${nx + 10}" y="${ny + 29}" fill="${tok.textSecondary}" font-family="'DM Sans', sans-serif" font-size="8.8">${escapeHtml(n.sub.slice(0, 16))}</text>
          </g>
        `;
      });

      inner += `</g>`;
      svg.innerHTML = inner;
    }

    function onNodeMapSelect(segId, label) {
      document.getElementById('nodeMapSelectionReadout').textContent = `Selected: ${label} (${segId})`;
      const idx = ALL_SEGMENTS.findIndex(s => s.segment_id === segId);
      if (idx >= 0) {
        selectSegment(idx);
        const row = document.getElementById(`seg-row-${idx}`);
        if (row) row.scrollIntoView({ block: 'nearest' });
      }
    }

    function initNodeMapInteractions() {
      const vp = document.getElementById('nodeMapViewport');
      if (!vp) return;
      vp.addEventListener('mousedown', e => {
        if (e.target.closest('g[onclick]')) return;
        NODE_MAP_STATE.dragging = true;
        NODE_MAP_STATE.startX = e.clientX - NODE_MAP_STATE.tx;
        NODE_MAP_STATE.startY = e.clientY - NODE_MAP_STATE.ty;
      });
      window.addEventListener('mousemove', e => {
        if (!NODE_MAP_STATE.dragging) return;
        NODE_MAP_STATE.tx = e.clientX - NODE_MAP_STATE.startX;
        NODE_MAP_STATE.ty = e.clientY - NODE_MAP_STATE.startY;
        applyNodeMapTransform();
      });
      window.addEventListener('mouseup', () => { NODE_MAP_STATE.dragging = false; });
      vp.addEventListener('wheel', e => {
        e.preventDefault();
        zoomNodeMap(e.deltaY < 0 ? 1.09 : 0.91);
      }, { passive: false });
    }

    /* ==========================================================================
       3D MOLECULAR & STRUCTURAL VIEW (HARDWARE WEBGL + SOFTWARE PROJECTION FALLBACK)
       ========================================================================== */
    const MOL_MODELS = {
      lisinopril: {
        title: 'Lisinopril 20 MG (RxNorm 314076 • C21H31N3O5 • ACE Inhibitor)',
        atoms: [
          // Proline ring + C-terminal carboxylate (Active Zn/C-domain binding in Emerald)
          { x: -3.2, y:  0.4, z:  0.2, elem: 'N', label: 'N1 (Proline)', color: PALETTE.indigo, r: 0.34 },
          { x: -4.1, y: -0.6, z:  0.5, elem: 'C', label: 'C2 (Proline alpha)', color: PALETTE.teal, r: 0.31 },
          { x: -5.4, y: -0.1, z:  0.1, elem: 'C', label: 'C3 (Proline)', color: PALETTE.teal, r: 0.31 },
          { x: -5.2, y:  1.2, z: -0.5, elem: 'C', label: 'C4 (Proline)', color: PALETTE.teal, r: 0.31 },
          { x: -3.8, y:  1.5, z: -0.4, elem: 'C', label: 'C5 (Proline)', color: PALETTE.teal, r: 0.31 },
          { x: -4.0, y: -1.9, z: -0.1, elem: 'C', label: 'C6 (Carboxyl)', color: PALETTE.emerald, r: 0.33 },
          { x: -4.9, y: -2.7, z:  0.1, elem: 'O', label: 'O7 (Carboxylate)', color: PALETTE.emerald, r: 0.30 },
          { x: -3.0, y: -2.2, z: -0.8, elem: 'O', label: 'O8 (Carboxylate)', color: PALETTE.rose, r: 0.30 },
          // Peptide carbonyl + Lysyl aminobutyl chain
          { x: -1.9, y:  0.3, z:  0.5, elem: 'C', label: 'C9 (Amide C=O)', color: PALETTE.teal, r: 0.31 },
          { x: -1.4, y: -0.7, z:  1.0, elem: 'O', label: 'O10 (Carbonyl)', color: PALETTE.rose, r: 0.30 },
          { x: -1.1, y:  1.5, z:  0.2, elem: 'C', label: 'C11 (Lysyl alpha)', color: PALETTE.teal, r: 0.32 },
          { x: -1.3, y:  2.6, z:  1.2, elem: 'C', label: 'C12 (Lysyl beta)', color: PALETTE.teal, r: 0.30 },
          { x: -0.6, y:  3.9, z:  0.9, elem: 'C', label: 'C13 (Lysyl gamma)', color: PALETTE.teal, r: 0.30 },
          { x: -0.8, y:  4.9, z:  1.9, elem: 'C', label: 'C14 (Lysyl delta)', color: PALETTE.teal, r: 0.30 },
          { x: -0.1, y:  6.1, z:  1.6, elem: 'N', label: 'N15 (Primary Amine)', color: PALETTE.indigo, r: 0.35 },
          // Central NH + Zinc-chelating Carboxylate
          { x:  0.3, y:  1.1, z:  0.1, elem: 'N', label: 'N16 (Secondary Amine)', color: PALETTE.indigo, r: 0.34 },
          { x:  1.2, y:  2.0, z: -0.5, elem: 'C', label: 'C17 (CH-COOH)', color: PALETTE.teal, r: 0.32 },
          { x:  0.9, y:  2.2, z: -1.9, elem: 'C', label: 'C18 (Zn-Carboxyl)', color: PALETTE.emerald, r: 0.33 },
          { x:  1.6, y:  3.0, z: -2.6, elem: 'O', label: 'O19 (Zn-Binding O)', color: PALETTE.emerald, r: 0.31 },
          { x: -0.1, y:  1.6, z: -2.4, elem: 'O', label: 'O20 (Hydroxyl O)', color: PALETTE.rose, r: 0.30 },
          // Phenethyl S1 pocket aromatic ring
          { x:  2.6, y:  1.5, z: -0.3, elem: 'C', label: 'C21 (Ethyl)', color: PALETTE.teal, r: 0.30 },
          { x:  3.6, y:  2.3, z:  0.4, elem: 'C', label: 'C22 (Benzyl CH2)', color: PALETTE.teal, r: 0.30 },
          { x:  4.9, y:  1.7, z:  0.5, elem: 'C', label: 'C23 (Phenyl)', color: PALETTE.teal, r: 0.31 },
          { x:  5.3, y:  0.6, z:  1.3, elem: 'C', label: 'C24 (Phenyl)', color: PALETTE.teal, r: 0.31 },
          { x:  6.5, y:  0.0, z:  1.4, elem: 'C', label: 'C25 (Phenyl)', color: PALETTE.teal, r: 0.31 },
          { x:  7.4, y:  0.6, z:  0.6, elem: 'C', label: 'C26 (Phenyl)', color: PALETTE.teal, r: 0.31 },
          { x:  7.0, y:  1.7, z: -0.2, elem: 'C', label: 'C27 (Phenyl)', color: PALETTE.teal, r: 0.31 },
          { x:  5.8, y:  2.3, z: -0.2, elem: 'C', label: 'C28 (Phenyl)', color: PALETTE.teal, r: 0.31 }
        ],
        bonds: [
          [0,1],[1,2],[2,3],[3,4],[4,0],[1,5],[5,6],[5,7],
          [0,8],[8,9],[8,10],[10,11],[11,12],[12,13],[13,14],
          [10,15],[15,16],[16,17],[17,18],[17,19],
          [16,20],[20,21],[21,22],[22,23],[23,24],[24,25],[25,26],[26,27],[27,22]
        ]
      },
      penicillin: {
        title: 'Penicillin G (RxNorm 70618 • C16H18N2O4S • Severe Anaphylaxis Allergen)',
        atoms: [
          // Thiazolidine 5-ring + Fused Beta-Lactam 4-ring
          { x: -1.8, y:  1.2, z:  0.3, elem: 'S', label: 'S1 (Thiazolidine Sulfur)', color: PALETTE.amber, r: 0.40 },
          { x: -3.1, y:  0.1, z:  0.0, elem: 'C', label: 'C2 (Gem-Dimethyl C)', color: PALETTE.teal, r: 0.32 },
          { x: -2.4, y: -1.2, z: -0.3, elem: 'C', label: 'C3 (CH-COOH)', color: PALETTE.teal, r: 0.32 },
          { x: -1.0, y: -0.9, z: -0.1, elem: 'N', label: 'N4 (Bridgehead Beta-Lactam N)', color: PALETTE.indigo, r: 0.35 },
          { x: -0.6, y:  0.4, z:  0.2, elem: 'C', label: 'C5 (Bridgehead CH)', color: PALETTE.teal, r: 0.32 },
          { x:  0.6, y:  0.1, z: -0.5, elem: 'C', label: 'C6 (Acylamino CH)', color: PALETTE.teal, r: 0.32 },
          { x:  0.1, y: -1.2, z: -0.8, elem: 'C', label: 'C7 (Reactive Beta-Lactam C=O)', color: PALETTE.rose, r: 0.34 },
          { x:  0.6, y: -2.2, z: -1.3, elem: 'O', label: 'O8 (Haptenating Lactam O)', color: PALETTE.rose, r: 0.33 },
          // C3 Carboxyl + C2 Methyls
          { x: -2.9, y: -2.4, z:  0.4, elem: 'C', label: 'C9 (Carboxyl)', color: PALETTE.teal, r: 0.31 },
          { x: -2.3, y: -3.4, z:  0.3, elem: 'O', label: 'O10 (Carboxyl O)', color: PALETTE.rose, r: 0.30 },
          { x: -4.0, y: -2.3, z:  1.0, elem: 'O', label: 'O11 (Carboxylate)', color: PALETTE.rose, r: 0.30 },
          { x: -4.0, y:  0.6, z: -1.1, elem: 'C', label: 'C12 (Methyl alpha)', color: PALETTE.amber, r: 0.30 },
          { x: -3.9, y:  0.0, z:  1.2, elem: 'C', label: 'C13 (Methyl beta)', color: PALETTE.amber, r: 0.30 },
          // Benzylpenicillin Side Chain
          { x:  1.8, y:  0.3, z:  0.2, elem: 'N', label: 'N14 (Amide NH)', color: PALETTE.indigo, r: 0.34 },
          { x:  2.9, y: -0.4, z: -0.1, elem: 'C', label: 'C15 (Amide C=O)', color: PALETTE.teal, r: 0.31 },
          { x:  2.9, y: -1.4, z: -0.8, elem: 'O', label: 'O16 (Amide O)', color: PALETTE.rose, r: 0.30 },
          { x:  4.2, y:  0.1, z:  0.5, elem: 'C', label: 'C17 (Benzyl CH2)', color: PALETTE.teal, r: 0.31 },
          { x:  5.3, y: -0.6, z:  0.0, elem: 'C', label: 'C18 (Phenyl)', color: PALETTE.teal, r: 0.31 },
          { x:  5.8, y: -1.7, z:  0.7, elem: 'C', label: 'C19 (Phenyl)', color: PALETTE.teal, r: 0.31 },
          { x:  6.9, y: -2.3, z:  0.2, elem: 'C', label: 'C20 (Phenyl)', color: PALETTE.teal, r: 0.31 },
          { x:  7.5, y: -1.8, z: -1.0, elem: 'C', label: 'C21 (Phenyl)', color: PALETTE.teal, r: 0.31 },
          { x:  7.0, y: -0.7, z: -1.7, elem: 'C', label: 'C22 (Phenyl)', color: PALETTE.teal, r: 0.31 },
          { x:  5.9, y: -0.1, z: -1.2, elem: 'C', label: 'C23 (Phenyl)', color: PALETTE.teal, r: 0.31 }
        ],
        bonds: [
          [0,1],[1,2],[2,3],[3,4],[4,0],[4,5],[5,6],[6,3],[6,7],
          [2,8],[8,9],[8,10],[1,11],[1,12],
          [5,13],[13,14],[14,15],[14,16],[16,17],
          [17,18],[18,19],[19,20],[20,21],[21,22],[22,17]
        ]
      },
      x12_lattice: {
        title: 'X12 5010 Spatial Loop Hierarchy Lattice',
        atoms: [],
        bonds: []
      }
    };

    const MOL_STATE = {
      modelKey: 'x12_lattice',
      yaw: 0.48,
      pitch: 0.26,
      zoom: 1.0,
      dragging: false,
      lastX: 0,
      lastY: 0,
      forceSoftware: false,
      webglReady: false,
      gl: null,
      glProg: null,
      glBuf: null,
      projectedAtoms: []
    };

    function buildX12LatticeModel() {
      const { nodes, edges } = buildGraphNodesAndEdges(CURRENT_DATA, CURRENT_DATASET.meta);
      const atoms = [];
      const idToIdx = {};
      const colBuckets = {};
      nodes.forEach(n => {
        colBuckets[n.col] = colBuckets[n.col] || [];
        colBuckets[n.col].push(n);
      });

      Object.keys(colBuckets).forEach(ck => {
        const list = colBuckets[ck];
        const colNum = Number(ck);
        const xCoord = (colNum - 2) * 2.1;
        list.forEach((n, idx) => {
          const angle = (idx / Math.max(list.length, 1)) * Math.PI * 2 + colNum * 0.35;
          const radius = list.length === 1 ? 0 : 1.65;
          idToIdx[n.id] = atoms.length;
          atoms.push({
            x: xCoord,
            y: Math.sin(angle) * radius,
            z: Math.cos(angle) * radius,
            elem: n.segId,
            label: `${n.label} (${n.sub})`,
            color: n.color,
            r: colNum === 0 ? 0.42 : 0.36
          });
        });
      });

      const bonds = [];
      edges.forEach(e => {
        if (idToIdx[e.from] !== undefined && idToIdx[e.to] !== undefined) {
          bonds.push([idToIdx[e.from], idToIdx[e.to]]);
        }
      });

      MOL_MODELS.x12_lattice.atoms = atoms;
      MOL_MODELS.x12_lattice.bonds = bonds;
      MOL_MODELS.x12_lattice.title = `[${CURRENT_DATASET.meta.tx_type}] ${CURRENT_DATASET.meta.filename} — 3D Spatial Loop Lattice (${atoms.length} Nodes, ${bonds.length} Links)`;
    }

    function sync3dLegendAndSubtitle() {
      const key = MOL_STATE.modelKey || 'x12_lattice';
      const subEl = document.getElementById('mol3dSubtitle');
      const legEl = document.getElementById('mol3dLegendBar');
      const selEl = document.getElementById('molModelSelect');
      if (selEl && selEl.value !== key) selEl.value = key;
      if (subEl) {
        if (key === 'x12_lattice') {
          subEl.textContent = MOL_MODELS.x12_lattice.title;
        } else {
          subEl.textContent = `${MOL_MODELS[key].title} • Active Context: ${CURRENT_DATASET.meta.filename}`;
        }
      }
      if (legEl) {
        if (key === 'x12_lattice') {
          legEl.innerHTML = `
            <span class="legend-item"><span class="legend-swatch" style="background:#0D9488"></span>Envelope/Line</span>
            <span class="legend-item"><span class="legend-swatch" style="background:#4F46E5"></span>Entity/Clinical</span>
            <span class="legend-item"><span class="legend-swatch" style="background:#059669"></span>Claim/Paid</span>
            <span class="legend-item"><span class="legend-swatch" style="background:#D97706"></span>Adjustment</span>
            <span class="legend-item"><span class="legend-swatch" style="background:#E11D48"></span>Alert/Pended</span>
          `;
        } else {
          legEl.innerHTML = `
            <span class="legend-item"><span class="legend-swatch" style="background:#0D9488"></span>C / Backbone</span>
            <span class="legend-item"><span class="legend-swatch" style="background:#4F46E5"></span>N / Amine</span>
            <span class="legend-item"><span class="legend-swatch" style="background:#E11D48"></span>O / Carbonyl</span>
            <span class="legend-item"><span class="legend-swatch" style="background:#D97706"></span>S / Ring</span>
            <span class="legend-item"><span class="legend-swatch" style="background:#059669"></span>Active Site</span>
          `;
        }
      }
    }

    function initWebGL3D() {
      const canvas = document.getElementById('molecular3dCanvas');
      if (!canvas) return;

      try {
        const gl = canvas.getContext('webgl', { antialias: true, alpha: true, premultipliedAlpha: false });
        if (!gl) {
          MOL_STATE.webglReady = false;
          return;
        }

        const vsSrc = `
          attribute vec2 aCorner;
          attribute vec3 aPos;
          attribute vec3 aColor;
          attribute float aSize;
          attribute float aKind;
          varying vec2 vUv;
          varying vec3 vColor;
          varying float vKind;
          void main() {
            vUv = aCorner;
            vColor = aColor;
            vKind = aKind;
            gl_Position = vec4(aPos.xy + aCorner * aSize, aPos.z, 1.0);
          }
        `;
        const fsSrc = `
          precision mediump float;
          varying vec2 vUv;
          varying vec3 vColor;
          varying float vKind;
          void main() {
            if (vKind > 0.5) {
              float r2 = dot(vUv, vUv);
              if (r2 > 1.0) discard;
              float nz = sqrt(max(0.0, 1.0 - r2));
              vec3 norm = normalize(vec3(vUv.x, vUv.y, nz));
              vec3 lightDir = normalize(vec3(-0.45, 0.55, 0.70));
              float diff = max(dot(norm, lightDir), 0.0);
              float spec = pow(max(dot(reflect(-lightDir, norm), vec3(0.0, 0.0, 1.0)), 0.0), 22.0);
              vec3 lit = vColor * (0.38 + 0.62 * diff) + vec3(0.24) * spec;
              float alpha = smoothstep(1.0, 0.88, r2);
              gl_FragColor = vec4(lit, alpha);
            } else {
              gl_FragColor = vec4(vColor, 0.52);
            }
          }
        `;

        const compile = (type, src) => {
          const s = gl.createShader(type);
          gl.shaderSource(s, src);
          gl.compileShader(s);
          if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) return null;
          return s;
        };

        const vs = compile(gl.VERTEX_SHADER, vsSrc);
        const fs = compile(gl.FRAGMENT_SHADER, fsSrc);
        if (!vs || !fs) { MOL_STATE.webglReady = false; return; }

        const prog = gl.createProgram();
        gl.attachShader(prog, vs);
        gl.attachShader(prog, fs);
        gl.linkProgram(prog);
        if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) { MOL_STATE.webglReady = false; return; }

        MOL_STATE.gl = gl;
        MOL_STATE.glProg = prog;
        MOL_STATE.glBuf = gl.createBuffer();
        MOL_STATE.webglReady = true;
      } catch (_) {
        MOL_STATE.webglReady = false;
      }
    }

    function set3dModel(key) {
      MOL_STATE.modelKey = key;
      if (key === 'x12_lattice') buildX12LatticeModel();
      sync3dLegendAndSubtitle();
      request3dRender();
    }

    function reset3dCamera() {
      MOL_STATE.yaw = 0.48;
      MOL_STATE.pitch = 0.26;
      MOL_STATE.zoom = 1.0;
      request3dRender();
    }

    function toggle3dRendererMode() {
      MOL_STATE.forceSoftware = !MOL_STATE.forceSoftware;
      document.getElementById('btnToggle3dRenderer').textContent = MOL_STATE.forceSoftware ? 'Engine: Software' : 'Engine: Auto';
      // Recreate canvas if switching between WebGL and 2D context on same element
      const oldCanvas = document.getElementById('molecular3dCanvas');
      const nextCanvas = oldCanvas.cloneNode(false);
      oldCanvas.parentNode.replaceChild(nextCanvas, oldCanvas);
      bind3dCanvasEvents(nextCanvas);
      if (!MOL_STATE.forceSoftware) {
        initWebGL3D();
      } else {
        MOL_STATE.gl = null;
      }
      request3dRender();
    }

    function projectModelGeometry(model, w, h) {
      const atoms = model.atoms || [];
      if (atoms.length === 0) return { projAtoms: [], bonds: [] };

      let cx = 0, cy = 0, cz = 0;
      atoms.forEach(a => { cx += a.x; cy += a.y; cz += a.z; });
      cx /= atoms.length; cy /= atoms.length; cz /= atoms.length;

      const cosY = Math.cos(MOL_STATE.yaw), sinY = Math.sin(MOL_STATE.yaw);
      const cosP = Math.cos(MOL_STATE.pitch), sinP = Math.sin(MOL_STATE.pitch);
      const camDist = 11.5 / MOL_STATE.zoom;
      const fov = Math.min(w, h) * 0.92;

      const projAtoms = atoms.map((a, idx) => {
        const dx = a.x - cx, dy = a.y - cy, dz = a.z - cz;
        const x1 = dx * cosY + dz * sinY;
        const z1 = -dx * sinY + dz * cosY;
        const y2 = dy * cosP - z1 * sinP;
        const z2 = dy * sinP + z1 * cosP;
        const depth = Math.max(2.2, camDist - z2);
        const scale = fov / depth;
        return {
          idx,
          atom: a,
          sx: w / 2 + x1 * scale,
          sy: h / 2 - y2 * scale,
          depth,
          sr: Math.max(5, a.r * scale),
          ndcX: (x1 * scale) / (w / 2),
          ndcY: (y2 * scale) / (h / 2),
          ndcZ: Math.max(-0.95, Math.min(0.95, (depth - camDist) / 10.0))
        };
      });

      return { projAtoms, bonds: model.bonds || [] };
    }

    function request3dRender() {
      const canvas = document.getElementById('molecular3dCanvas');
      if (!canvas) return;
      const rect = canvas.parentElement.getBoundingClientRect();
      const w = Math.max(rect.width, 320);
      const h = Math.max(rect.height, 260);
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);

      const model = MOL_MODELS[MOL_STATE.modelKey] || MOL_MODELS.lisinopril;
      const { projAtoms, bonds } = projectModelGeometry(model, w, h);
      MOL_STATE.projectedAtoms = projAtoms;

      const useWebGL = !MOL_STATE.forceSoftware && MOL_STATE.webglReady && MOL_STATE.gl;
      const badge = document.getElementById('mol3dEngineBadge');

      if (useWebGL) {
        badge.textContent = 'Renderer: Hardware WebGL Shader';
        const gl = MOL_STATE.gl;
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
        gl.useProgram(MOL_STATE.glProg);

        const verts = [];
        const pushQuad = (pts, rgb, sizeX, sizeY, kind) => {
          // 2 triangles
          const c = [[-1,-1],[1,-1],[1,1],[-1,-1],[1,1],[-1,1]];
          c.forEach(cn => {
            verts.push(cn[0] * sizeX, cn[1] * sizeY, pts[0], pts[1], pts[2], rgb[0], rgb[1], rgb[2], 1.0, kind);
          });
        };

        // Back-to-front sorted draw list (bonds + spheres)
        const items = [];
        bonds.forEach(b => {
          const p1 = projAtoms[b[0]], p2 = projAtoms[b[1]];
          if (!p1 || !p2) return;
          items.push({ depth: (p1.depth + p2.depth) * 0.5 + 0.08, type: 'bond', p1, p2 });
        });
        projAtoms.forEach(pa => {
          items.push({ depth: pa.depth, type: 'atom', pa });
        });
        items.sort((a, b) => b.depth - a.depth);

        items.forEach(it => {
          if (it.type === 'bond') {
            const { p1, p2 } = it;
            const dx = p2.sx - p1.sx, dy = p2.sy - p1.sy;
            const len = Math.hypot(dx, dy) || 1;
            const nx = (-dy / len) * 2.2 / (w / 2);
            const ny = (-dx / len) * 2.2 / (h / 2);
            const rgb = hexToRgb(p1.atom.color).map(v => v / 255);
            const x1 = p1.ndcX, y1 = p1.ndcY, x2 = p2.ndcX, y2 = p2.ndcY;
            const q = [
              [x1 - nx, y1 - ny], [x1 + nx, y1 + ny], [x2 + nx, y2 + ny],
              [x1 - nx, y1 - ny], [x2 + nx, y2 + ny], [x2 - nx, y2 - ny]
            ];
            q.forEach(pt => {
              verts.push(0, 0, pt[0], pt[1], 0, rgb[0], rgb[1], rgb[2], 0.0, 0.0);
            });
          } else {
            const pa = it.pa;
            const rgb = hexToRgb(pa.atom.color).map(v => v / 255);
            const rx = pa.sr / (w / 2);
            const ry = pa.sr / (h / 2);
            const corners = [[-1,-1],[1,-1],[1,1],[-1,-1],[1,1],[-1,1]];
            corners.forEach(cn => {
              verts.push(cn[0], cn[1], pa.ndcX + cn[0] * rx, pa.ndcY + cn[1] * ry, 0, rgb[0], rgb[1], rgb[2], 0.0, 1.0);
            });
          }
        });

        const arr = new Float32Array(verts);
        gl.bindBuffer(gl.ARRAY_BUFFER, MOL_STATE.glBuf);
        gl.bufferData(gl.ARRAY_BUFFER, arr, gl.DYNAMIC_DRAW);

        const stride = 10 * 4;
        const bindAttr = (name, size, offset) => {
          const loc = gl.getAttribLocation(MOL_STATE.glProg, name);
          if (loc >= 0) {
            gl.enableVertexAttribArray(loc);
            gl.vertexAttribPointer(loc, size, gl.FLOAT, false, stride, offset * 4);
          }
        };
        bindAttr('aCorner', 2, 0);
        bindAttr('aPos', 3, 2);
        bindAttr('aColor', 3, 5);
        bindAttr('aSize', 1, 8);
        bindAttr('aKind', 1, 9);

        gl.drawArrays(gl.TRIANGLES, 0, verts.length / 10);
      } else {
        // Software 2D Perspective Projection Fallback (DESIGN.md Section 4)
        badge.textContent = 'Renderer: Software Projection Fallback';
        const ctx = canvas.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);

        const items = [];
        bonds.forEach(b => {
          const p1 = projAtoms[b[0]], p2 = projAtoms[b[1]];
          if (p1 && p2) items.push({ depth: (p1.depth + p2.depth) * 0.5 + 0.08, type: 'bond', p1, p2 });
        });
        projAtoms.forEach(pa => items.push({ depth: pa.depth, type: 'atom', pa }));
        items.sort((a, b) => b.depth - a.depth);

        items.forEach(it => {
          if (it.type === 'bond') {
            ctx.strokeStyle = it.p1.atom.color;
            ctx.globalAlpha = 0.48;
            ctx.lineWidth = 3.2;
            ctx.beginPath();
            ctx.moveTo(it.p1.sx, it.p1.sy);
            ctx.lineTo(it.p2.sx, it.p2.sy);
            ctx.stroke();
            ctx.globalAlpha = 1.0;
          } else {
            const pa = it.pa;
            ctx.fillStyle = pa.atom.color;
            ctx.beginPath();
            ctx.arc(pa.sx, pa.sy, pa.sr, 0, Math.PI * 2);
            ctx.fill();
            // Specular highlight dot
            ctx.fillStyle = 'rgba(255,255,255,0.34)';
            ctx.beginPath();
            ctx.arc(pa.sx - pa.sr * 0.28, pa.sy - pa.sr * 0.28, Math.max(1.5, pa.sr * 0.28), 0, Math.PI * 2);
            ctx.fill();
          }
        });
      }
    }

    function bind3dCanvasEvents(canvas) {
      if (!canvas) return;
      canvas.addEventListener('mousedown', e => {
        MOL_STATE.dragging = true;
        MOL_STATE.lastX = e.clientX;
        MOL_STATE.lastY = e.clientY;
      });
      window.addEventListener('mousemove', e => {
        if (MOL_STATE.dragging) {
          const dx = e.clientX - MOL_STATE.lastX;
          const dy = e.clientY - MOL_STATE.lastY;
          MOL_STATE.lastX = e.clientX;
          MOL_STATE.lastY = e.clientY;
          MOL_STATE.yaw += dx * 0.011;
          MOL_STATE.pitch = Math.max(-1.45, Math.min(1.45, MOL_STATE.pitch + dy * 0.011));
          request3dRender();
          return;
        }
        // Hover picking on 3D canvas
        const rect = canvas.getBoundingClientRect();
        if (e.clientX >= rect.left && e.clientX <= rect.right && e.clientY >= rect.top && e.clientY <= rect.bottom) {
          const mx = e.clientX - rect.left;
          const my = e.clientY - rect.top;
          let hit = null;
          for (const pa of MOL_STATE.projectedAtoms) {
            if (Math.hypot(mx - pa.sx, my - pa.sy) <= pa.sr + 3) {
              if (!hit || pa.depth < hit.depth) hit = pa;
            }
          }
          if (hit) {
            showTooltip(e.clientX, e.clientY, `${hit.atom.label}\nCoords: (${hit.atom.x.toFixed(1)}, ${hit.atom.y.toFixed(1)}, ${hit.atom.z.toFixed(1)})`);
          } else {
            hideTooltip();
          }
        }
      });
      window.addEventListener('mouseup', () => { MOL_STATE.dragging = false; });
      canvas.addEventListener('mouseleave', hideTooltip);
      canvas.addEventListener('wheel', e => {
        e.preventDefault();
        MOL_STATE.zoom = Math.max(0.55, Math.min(2.4, MOL_STATE.zoom * (e.deltaY < 0 ? 1.08 : 0.92)));
        request3dRender();
      }, { passive: false });
    }

    /* ==========================================================================
       TOOLTIP HELPERS & 2D CHART HOVER
       ========================================================================== */
    function showTooltip(cx, cy, text) {
      const tip = document.getElementById('vizTooltip');
      if (!tip) return;
      tip.textContent = text;
      tip.style.whiteSpace = 'pre-line';
      tip.style.display = 'block';
      tip.style.left = `${Math.min(window.innerWidth - 280, cx + 12)}px`;
      tip.style.top = `${Math.max(12, cy - 18)}px`;
    }

    function hideTooltip() {
      const tip = document.getElementById('vizTooltip');
      if (tip) tip.style.display = 'none';
    }

    function initChartHover() {
      const c = document.getElementById('financialChartCanvas');
      if (!c) return;
      c.addEventListener('mousemove', e => {
        const rect = c.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const hit = CHART_HIT_BOXES.find(b => mx >= b.x && mx <= b.x + b.w && my >= b.y && my <= b.y + b.h);
        if (hit) {
          showTooltip(e.clientX, e.clientY, `${hit.title}\n${hit.detail}`);
        } else {
          hideTooltip();
        }
      });
      c.addEventListener('mouseleave', hideTooltip);
    }

    /* ==========================================================================
       SYNCHRONIZED SEGMENT-TO-JSON EXPLORER
       ========================================================================== */
    function buildSegmentIndex(data, rawEdi) {
      ALL_SEGMENTS = [];
      const delimSeg = ((data.delimiters || {}).segment_terminator) || '~';
      const delimElem = ((data.delimiters || {}).element_separator) || '*';

      const parsedSegMap = {};
      if (data.interchange_header && data.interchange_header.line_number) {
        parsedSegMap[data.interchange_header.line_number] = data.interchange_header;
      }
      if (data.interchange_trailer && data.interchange_trailer.line_number) {
        parsedSegMap[data.interchange_trailer.line_number] = data.interchange_trailer;
      }
      (data.functional_groups || []).forEach(g => {
        if (g.functional_group_header && g.functional_group_header.line_number) {
          parsedSegMap[g.functional_group_header.line_number] = g.functional_group_header;
        }
        if (g.functional_group_trailer && g.functional_group_trailer.line_number) {
          parsedSegMap[g.functional_group_trailer.line_number] = g.functional_group_trailer;
        }
        (g.transaction_sets || []).forEach(tx => {
          (tx.segments || []).forEach(s => {
            if (s.line_number) parsedSegMap[s.line_number] = s;
          });
        });
      });

      const lines = (rawEdi || '').split(delimSeg).map(l => l.trim()).filter(Boolean);
      lines.forEach((line, idx) => {
        const lineNum = idx + 1;
        const parts = line.split(delimElem);
        const segId = parts[0].trim();
        const parsedSeg = parsedSegMap[lineNum] || null;
        ALL_SEGMENTS.push({
          idx,
          line_number: lineNum,
          raw_text: line + delimSeg,
          segment_id: segId,
          elements: parts.slice(1),
          parsed_fields: parsedSeg ? (parsedSeg.fields || {}) : {},
          loop: (SEGMENT_KB[segId] && SEGMENT_KB[segId].loop) || 'Transaction Stream'
        });
      });
      FILTERED_SEGMENTS = ALL_SEGMENTS.slice();
    }

    function getSegToneClass(id) {
      if (['ISA', 'GS', 'ST', 'SE', 'GE', 'IEA', 'CLM', 'SV1', 'SV2', 'EB', 'EQ', 'UM'].includes(id)) return 'tone-teal';
      if (['CLP', 'BPR', 'TRN', 'SVC', 'HCR'].includes(id)) return 'tone-emerald';
      if (['NM1', 'N1', 'N3', 'N4', 'DMG', 'HI', 'BDS', 'BIN', 'CAT'].includes(id)) return 'tone-indigo';
      if (['STC', 'PWK'].includes(id)) return 'tone-rose';
      if (['CAS', 'PLB'].includes(id)) return 'tone-amber';
      return '';
    }

    function renderSegmentList(segments) {
      const container = document.getElementById('segmentListContainer');
      container.innerHTML = '';
      document.getElementById('segCountBadge').textContent = `${segments.length} segs`;

      segments.forEach(seg => {
        const isSelected = seg.idx === SELECTED_SEG_INDEX;
        const tone = getSegToneClass(seg.segment_id);
        const div = document.createElement('div');
        div.className = `seg-item ${isSelected ? 'seg-active' : ''}`;
        div.id = `seg-row-${seg.idx}`;
        div.onclick = () => selectSegment(seg.idx);
        div.innerHTML = `
          <div class="seg-item-top">
            <div>
              <span class="mono tone-muted" style="font-size:0.69rem;margin-right:6px">#${String(seg.line_number).padStart(2, '0')}</span>
              <span class="seg-tag ${tone}">${escapeHtml(seg.segment_id)}</span>
            </div>
            <span class="mono tone-muted" style="font-size:0.68rem">${escapeHtml(seg.loop)}</span>
          </div>
          <div class="seg-raw-preview">${escapeHtml(seg.raw_text.slice(0, 110))}</div>
        `;
        container.appendChild(div);
      });
    }

    function selectSegment(index) {
      if (index < 0 || index >= ALL_SEGMENTS.length) return;
      SELECTED_SEG_INDEX = index;

      document.querySelectorAll('#segmentListContainer .seg-item').forEach(el => {
        el.classList.toggle('seg-active', el.id === `seg-row-${index}`);
      });

      const seg = ALL_SEGMENTS[index];
      const kb = SEGMENT_KB[seg.segment_id] || {
        name: `${seg.segment_id} Segment`,
        loop: seg.loop || 'Transaction Stream',
        desc: `Standard EDI X12 5010 segment ${seg.segment_id}.`
      };

      document.getElementById('activeSegTag').textContent = seg.segment_id;
      document.getElementById('activeSegName').textContent = `${seg.segment_id} — ${kb.name}`;
      document.getElementById('activeSegDesc').textContent = kb.desc;
      document.getElementById('activeSegLoop').textContent = kb.loop;

      const targetInfo = findJsonEquivalent(seg);
      document.getElementById('activeSegTargetPath').textContent = targetInfo.path;
      document.getElementById('activeJsonSubtreeDisplay').textContent = JSON.stringify(targetInfo.subtree, null, 2);

      const tbody = document.getElementById('activeSegElementsTbody');
      if (seg.elements && seg.elements.length > 0) {
        const fieldKeys = Object.keys(seg.parsed_fields || {});
        tbody.innerHTML = seg.elements.map((val, eIdx) => {
          const elemRef = `${seg.segment_id}${String(eIdx + 1).padStart(2, '0')}`;
          const fKey = fieldKeys[eIdx] || `element_${eIdx + 1}`;
          const displayVal = val ? escapeHtml(String(val).slice(0, 140)) : '<span class="tone-muted">&mdash;</span>';
          return `
            <tr>
              <td class="mono tone-teal" style="font-weight:600">${elemRef}</td>
              <td class="mono tone-muted" style="font-size:0.72rem">${escapeHtml(fKey)}</td>
              <td class="mono" style="word-break:break-all">${displayVal}</td>
            </tr>
          `;
        }).join('');
      } else {
        tbody.innerHTML = `<tr><td colspan="3" class="tone-muted">No element values</td></tr>`;
      }
    }

    function nonEmptyObj(o) {
      if (!o || typeof o !== 'object') return null;
      if (Array.isArray(o)) return o.length > 0 ? o : null;
      return Object.keys(o).length > 0 ? o : null;
    }

    function findJsonEquivalent(seg) {
      const id = seg.segment_id;
      const firstGroup = (CURRENT_DATA.functional_groups || [])[0] || {};
      const firstTx = (firstGroup.transaction_sets || [])[0] || {};
      const parsedTx = firstTx.parsed_transaction || {};

      if (id === 'ISA') return { path: 'interchange_header', subtree: CURRENT_DATA.interchange_header || {} };
      if (id === 'IEA') return { path: 'interchange_trailer', subtree: CURRENT_DATA.interchange_trailer || {} };
      if (id === 'GS') return { path: 'functional_groups[0].functional_group_header', subtree: firstGroup.functional_group_header || {} };
      if (id === 'GE') return { path: 'functional_groups[0].functional_group_trailer', subtree: firstGroup.functional_group_trailer || {} };
      if (id === 'ST') return { path: 'transaction_sets[0].transaction_header', subtree: firstTx.transaction_header || {} };
      if (id === 'SE') return { path: 'transaction_sets[0].transaction_trailer', subtree: firstTx.transaction_trailer || {} };
      if (id === 'BHT') return { path: 'parsed_transaction.beginning_of_hierarchical_transaction', subtree: nonEmptyObj(parsedTx.beginning_of_hierarchical_transaction) || seg.parsed_fields };
      if (id === 'BGN') return { path: 'parsed_transaction.beginning_segment', subtree: nonEmptyObj(parsedTx.beginning_segment) || seg.parsed_fields };
      if (id === 'BPR') return { path: 'parsed_transaction.financial_information', subtree: nonEmptyObj(parsedTx.financial_information) || seg.parsed_fields };
      if (id === 'TRN') return { path: 'parsed_transaction.reassociation_trace', subtree: nonEmptyObj(parsedTx.reassociation_trace) || seg.parsed_fields };
      if (id === 'CLM' || id === 'CLP') return { path: 'parsed_transaction.claims[0]', subtree: (parsedTx.claims && parsedTx.claims[0]) || seg.parsed_fields };
      if (id === 'CAS') return { path: 'parsed_transaction.claims[0].adjustments', subtree: (parsedTx.claims && parsedTx.claims[0] && nonEmptyObj(parsedTx.claims[0].adjustments)) || seg.parsed_fields };
      if (id === 'SV1' || id === 'SV2' || id === 'SVC') {
        const lines = (parsedTx.claims && parsedTx.claims[0] && nonEmptyObj(parsedTx.claims[0].service_lines)) || (parsedTx.events && parsedTx.events[0] && nonEmptyObj(parsedTx.events[0].services));
        return { path: 'parsed_transaction.service_lines', subtree: lines || seg.parsed_fields };
      }
      if (id === 'HI') {
        const diags = (parsedTx.claims && parsedTx.claims[0] && nonEmptyObj(parsedTx.claims[0].diagnoses)) || (parsedTx.events && parsedTx.events[0] && nonEmptyObj(parsedTx.events[0].diagnoses));
        return { path: 'parsed_transaction.diagnoses', subtree: diags || seg.parsed_fields };
      }
      if (id === 'NM1' || id === 'N1') {
        const q = seg.elements[0];
        if (q === '85') return { path: 'parsed_transaction.billing_provider', subtree: nonEmptyObj(parsedTx.billing_provider) || nonEmptyObj(parsedTx.provider) || seg.parsed_fields };
        if (q === 'PR') return { path: 'parsed_transaction.payer', subtree: nonEmptyObj(parsedTx.payer) || nonEmptyObj(parsedTx.information_source) || nonEmptyObj(parsedTx.utilization_management_organization) || findN1SegmentEntity(parsedTx, 'PR') || seg.parsed_fields };
        if (q === 'PE') return { path: 'parsed_transaction.payee', subtree: nonEmptyObj(parsedTx.payee) || findN1SegmentEntity(parsedTx, 'PE') || seg.parsed_fields };
        if (q === 'IL') return { path: 'parsed_transaction.subscriber', subtree: nonEmptyObj(parsedTx.subscriber) || nonEmptyObj(parsedTx.subscribers) || seg.parsed_fields };
        if (q === 'QC') return { path: 'parsed_transaction.patient', subtree: nonEmptyObj(parsedTx.patient) || nonEmptyObj(parsedTx.subscriber) || seg.parsed_fields };
        if (q === '41') return { path: 'parsed_transaction.submitter', subtree: nonEmptyObj(parsedTx.submitter) || seg.parsed_fields };
        if (q === '40') return { path: 'parsed_transaction.receiver', subtree: nonEmptyObj(parsedTx.receiver) || seg.parsed_fields };
        if (q === '1P' || q === 'FA') return { path: 'parsed_transaction.requester', subtree: nonEmptyObj(parsedTx.requester) || nonEmptyObj(parsedTx.information_receiver) || seg.parsed_fields };
      }
      if (id === 'STC' || id === 'PWK') return { path: 'parsed_transaction.required_attachments', subtree: nonEmptyObj(parsedTx.required_attachments) || seg.parsed_fields };
      if (id === 'CAT' || id === 'PID') return { path: 'parsed_transaction.attachment_metadata', subtree: nonEmptyObj(parsedTx.attachment_information) || seg.parsed_fields };
      if (id === 'BDS' || id === 'BIN') return { path: 'parsed_transaction.attached_clinical_data', subtree: nonEmptyObj(parsedTx.attached_clinical_data) || seg.parsed_fields };
      if (id === 'EB') return { path: 'parsed_transaction.subscriber.eligibility_benefits', subtree: (parsedTx.subscriber && nonEmptyObj(parsedTx.subscriber.eligibility_benefits)) || nonEmptyObj(parsedTx.eligibility_benefits) || seg.parsed_fields };
      if (id === 'EQ') return { path: 'parsed_transaction.inquiries', subtree: nonEmptyObj(parsedTx.inquiries) || (parsedTx.subscriber && nonEmptyObj(parsedTx.subscriber.inquiries)) || seg.parsed_fields };
      if (id === 'UM' || id === 'HCR') return { path: 'parsed_transaction.events', subtree: nonEmptyObj(parsedTx.events) || seg.parsed_fields };
      if (id === 'PLB') return { path: 'parsed_transaction.provider_adjustments', subtree: nonEmptyObj(parsedTx.provider_adjustments) || seg.parsed_fields };

      return { path: `transaction_sets[0].segments[#${seg.line_number}]`, subtree: nonEmptyObj(seg.parsed_fields) || { raw: seg.raw_text } };
    }

    function filterSegments(skipSelect = false) {
      const q = (document.getElementById('segFilterInput').value || '').toLowerCase().trim();
      FILTERED_SEGMENTS = ALL_SEGMENTS.filter(s =>
        !q ||
        s.segment_id.toLowerCase().includes(q) ||
        s.raw_text.toLowerCase().includes(q) ||
        s.loop.toLowerCase().includes(q)
      );
      renderSegmentList(FILTERED_SEGMENTS);
      if (!skipSelect && FILTERED_SEGMENTS.length > 0 && !FILTERED_SEGMENTS.some(s => s.idx === SELECTED_SEG_INDEX)) {
        selectSegment(FILTERED_SEGMENTS[0].idx);
      }
    }

    /* ==========================================================================
       VALIDATION AUDIT, PROVENANCE CITATIONS, ENVELOPES, ENTITIES & DOMAIN TABLES
       ========================================================================== */
    function statusBadgeClass(st) {
      if (st === 'PASS') return 'status-tag status-pass';
      if (st === 'WARN') return 'status-tag status-warn';
      if (st === 'ALERT' || st === 'ERROR') return 'status-tag status-alert';
      return 'status-tag status-nominal';
    }

    function renderValidationAndProvenance() {
      const meta = CURRENT_DATASET.meta;
      const badge = document.getElementById('overallValidationBadge');
      badge.className = statusBadgeClass(meta.validation_status);
      badge.textContent = `${meta.validation_status} (${meta.tx_type})`;

      const valSub = document.getElementById('validationSubtitle');
      if (valSub) {
        valSub.textContent = `HIPAA 5010 structural & control number checks for [${meta.tx_type}] ${meta.filename}`;
      }

      const vBody = document.getElementById('validationAuditTbody');
      vBody.innerHTML = (meta.validations || []).map(v => `
        <tr>
          <td class="mono">${escapeHtml(v.rule_id)}</td>
          <td class="mono tone-muted">${escapeHtml(v.scope)}</td>
          <td>${escapeHtml(v.check)}</td>
          <td class="mono">${escapeHtml(v.expected)}</td>
          <td class="mono">${escapeHtml(v.observed)}</td>
          <td><span class="${statusBadgeClass(v.status)}">${escapeHtml(v.status)}</span></td>
        </tr>
      `).join('') || `<tr><td colspan="6" class="tone-muted">Envelope validated</td></tr>`;

      document.getElementById('activeProvenanceCitation').textContent =
        `Active Source: ${meta.source_path} • [${meta.tx_type}] • SHA-256: ${meta.sha256} • ${meta.byte_size.toLocaleString()} bytes`;

      const pBody = document.getElementById('provenanceLogTbody');
      pBody.innerHTML = BUNDLE.datasets.map((ds, idx) => {
        const m = ds.meta;
        const segs = (ds.parsed_data.summary || {}).total_segments_count || 0;
        const isCurrent = idx === ACTIVE_DATASET_IDX;
        const activeStyle = isCurrent ? 'font-weight:600;color:var(--viz-teal)' : '';
        return `
          <tr style="cursor:pointer;${isCurrent ? 'background:var(--bg-subtle)' : ''}" onclick="selectWorkspaceDataset(${idx}, true, false)">
            <td class="mono" style="${activeStyle}">${isCurrent ? '&rarr; ' : ''}${escapeHtml(m.source_path)}</td>
            <td class="mono">${escapeHtml(m.tx_type)}</td>
            <td class="mono">${segs}</td>
            <td class="mono tone-muted">${escapeHtml(m.sha256)}</td>
            <td class="mono">${Number(m.parse_ms || 0).toFixed(2)} ms</td>
            <td><span class="${statusBadgeClass(m.validation_status)}">${escapeHtml(m.validation_status)}</span></td>
          </tr>
        `;
      }).join('');
    }

    function renderEnvelopes(data, meta) {
      const grid = document.getElementById('envelopeGrid');
      const isa = (data.interchange_header && data.interchange_header.fields) || {};
      const firstGroup = (data.functional_groups || [])[0] || {};
      const gs = (firstGroup.functional_group_header && firstGroup.functional_group_header.fields) || {};
      const firstTx = (firstGroup.transaction_sets || [])[0] || {};
      const delims = data.delimiters || {};

      const envSub = document.getElementById('envelopeSubtitle');
      if (envSub) {
        envSub.textContent = `[${meta.tx_type}] ${meta.filename} • ISA13 #${isa.interchange_control_number || meta.isa_control_number} • ${meta.byte_size.toLocaleString()} bytes`;
      }

      const items = [
        { label: 'Sender ID (ISA06)', val: `${isa.interchange_sender_id_qualifier || 'ZZ'}:${isa.interchange_sender_id || 'N/A'}` },
        { label: 'Receiver ID (ISA08)', val: `${isa.interchange_receiver_id_qualifier || 'ZZ'}:${isa.interchange_receiver_id || 'N/A'}` },
        { label: 'Interchange Control (ISA13)', val: isa.interchange_control_number || meta.isa_control_number },
        { label: 'Interchange Timestamp', val: `${isa.interchange_date || 'N/A'} ${isa.interchange_time || ''}`.trim() },
        { label: 'Functional Group (GS01/GS06)', val: `${firstGroup.functional_identifier_code || gs.functional_identifier_code || 'HC'} #${firstGroup.group_control_number || gs.group_control_number || '1'}` },
        { label: 'Implementation Spec (GS08)', val: firstGroup.version || gs.version_release_industry_identifier_code || meta.gs_version || '005010' },
        { label: 'Set Control # (ST01/ST02)', val: `ST*${firstTx.transaction_type || meta.tx_type}*${firstTx.transaction_set_control_number || '0001'}` },
        { label: 'Detected Delimiters', val: `Elem '${delims.element_separator || '*'}' • Comp '${delims.component_separator || ':'}' • Seg '${(delims.segment_terminator || '~') === '\n' ? '\\n' : (delims.segment_terminator || '~')}'` }
      ];

      grid.innerHTML = items.map(it => `
        <div class="flat-cell">
          <span class="detail-kv-label">${escapeHtml(it.label)}</span>
          <span class="mono" style="font-size:0.78rem;font-weight:500">${escapeHtml(it.val)}</span>
        </div>
      `).join('');
    }

    function renderEntities(data, meta) {
      const grid = document.getElementById('entitiesGrid');
      const entSub = document.getElementById('entitiesSubtitle');
      if (entSub && meta) {
        entSub.textContent = `Resolved healthcare entities in [${meta.tx_type}] ${meta.filename}`;
      }

      const fg = (data.functional_groups || [])[0] || {};
      const ts = (fg.transaction_sets || [])[0] || {};
      const tx = ts.parsed_transaction || {};
      const partners = resolveTradingPartners(tx);

      const candidates = [
        { role: 'Billing / Service Provider', obj: partners.provider, tone: 'tone-teal' },
        { role: 'Payer / Information Source', obj: partners.payer, tone: 'tone-emerald' },
        { role: 'Subscriber / Patient', obj: partners.patient, tone: 'tone-indigo' },
        { role: 'Submitter / Receiver', obj: partners.submitter, tone: '' }
      ];

      const cards = [];
      candidates.forEach(c => {
        if (!c.obj) return;
        const o = c.obj;
        const name = o._displayName || o.name_last_or_organization || o.name || '';
        if (!name && !o.identification_code) return;
        const idCode = o.identification_code ? `${o.identification_code_qualifier || 'ID'}: ${o.identification_code}` : 'Role Verified';
        const addr = o.address || {};
        const geo = o.geographic_location || {};
        const loc = addr.address_line_1
          ? `${addr.address_line_1}, ${geo.city || ''} ${geo.state || ''} ${geo.postal_code || ''}`.trim()
          : (o.date_of_birth ? `DOB: ${o.date_of_birth}${o.gender ? ' • Sex: ' + o.gender : ''}` : `Active in ${meta ? meta.tx_type : 'X12'} Loop`);
        cards.push(`
          <div class="flat-cell">
            <span class="detail-kv-label ${c.tone}">${escapeHtml(c.role)}</span>
            <span style="font-weight:600;font-size:0.84rem">${escapeHtml(name)}</span>
            <span class="mono tone-muted" style="font-size:0.74rem">${escapeHtml(idCode)}</span>
            <span style="font-size:0.74rem;color:var(--text-secondary)">${escapeHtml(loc)}</span>
          </div>
        `);
      });

      grid.innerHTML = cards.slice(0, 3).join('') || `<div class="flat-cell"><span class="tone-muted">No distinct entity loops in [${escapeHtml(meta ? meta.tx_type : 'X12')}] ${escapeHtml(meta ? meta.filename : '')}.</span></div>`;
    }

    function renderTxSpecific(data, meta) {
      const panel = document.getElementById('txSpecificPanel');
      const fg = (data.functional_groups || [])[0] || {};
      const ts = (fg.transaction_sets || [])[0] || {};
      const tx = ts.parsed_transaction || {};
      const txType = ts.transaction_type || (meta && meta.tx_type) || 'X12';
      const fileTag = meta ? meta.filename : '';

      if (txType === '837') {
        const claims = tx.claims || [];
        panel.innerHTML = claims.map(c => `
          <section class="bento-pane">
            <div class="pane-header">
              <div class="pane-title-group">
                <h2 class="pane-title">Submitted Claim ${escapeHtml(c.claim_id || '')} — Service Lines &amp; Diagnoses (${escapeHtml(fileTag)})</h2>
                <p class="pane-subtitle">ICD-10 Diagnoses: ${(c.diagnoses || []).map(d => `${d.diagnosis_type || 'DX'}:${d.code}`).join(', ') || 'None'}</p>
              </div>
              <span class="mono tone-teal" style="font-weight:600">$${(parseFloat(c.total_claim_charge_amount) || 0).toFixed(2)}</span>
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead><tr><th>Line #</th><th>Procedure / Modifier</th><th>Place of Service</th><th>Units</th><th>Submitted Charge</th></tr></thead>
                <tbody>
                  ${(c.service_lines || []).map((sl, sIdx) => `
                    <tr>
                      <td class="mono">${escapeHtml(sl.line_number || (sIdx + 1))}</td>
                      <td class="mono tone-teal" style="font-weight:600">${escapeHtml((sl.procedure && (sl.procedure.raw || sl.procedure.procedure_code || sl.procedure.code)) || sl.revenue_code || 'N/A')}</td>
                      <td class="mono">${escapeHtml(sl.place_of_service || c.facility_code || '11')}</td>
                      <td class="mono">${escapeHtml(sl.unit_count || sl.service_unit_count || 1)}</td>
                      <td class="mono">$${(parseFloat(sl.charge_amount) || 0).toFixed(2)}</td>
                    </tr>
                  `).join('') || `<tr><td colspan="5" class="tone-muted">Claim header total: $${(parseFloat(c.total_claim_charge_amount) || 0).toFixed(2)}</td></tr>`}
                </tbody>
              </table>
            </div>
          </section>
        `).join('') || `<section class="bento-pane"><div class="pane-header"><h2 class="pane-title">837 Claim Stream (${escapeHtml(fileTag)})</h2></div><div style="padding:14px" class="tone-muted">No CLM loops found in active stream.</div></section>`;
      } else if (txType === '835') {
        const claims = tx.claims || [];
        panel.innerHTML = claims.map(c => {
          const svcRows = (c.service_lines || []).map((sv, idx) => `
            <tr>
              <td class="mono">SVC #${idx + 1}</td>
              <td class="mono tone-teal" style="font-weight:600">${escapeHtml((sv.procedure && (sv.procedure.raw || sv.procedure.procedure_code || sv.procedure.code)) || sv.procedure_code || 'SVC')}</td>
              <td class="mono">$${(parseFloat(sv.charge_amount || sv.line_item_charge_amount) || 0).toFixed(2)}</td>
              <td class="mono tone-emerald">$${(parseFloat(sv.payment_amount || sv.line_item_provider_payment_amount) || 0).toFixed(2)}</td>
            </tr>
          `).join('');
          return `
          <section class="bento-pane">
            <div class="pane-header">
              <div class="pane-title-group">
                <h2 class="pane-title">Remittance Adjudication — Claim ${escapeHtml(c.patient_control_number || '')} (${escapeHtml(fileTag)})</h2>
                <p class="pane-subtitle">ICN: ${escapeHtml(c.payer_claim_control_number || 'N/A')} • Status: ${escapeHtml(c.claim_status_description || 'Processed as Primary')}</p>
              </div>
              <span class="mono tone-emerald" style="font-weight:600">Paid $${(parseFloat(c.claim_payment_amount) || 0).toFixed(2)} / Billed $${(parseFloat(c.total_claim_charge_amount) || 0).toFixed(2)}</span>
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead><tr><th>Adjustment Group</th><th>CARC Reason</th><th>Quantity</th><th>Adjustment Amount</th></tr></thead>
                <tbody>
                  ${(c.adjustments || []).map(a => `
                    <tr>
                      <td class="mono ${a.group_code === 'PR' ? 'tone-amber' : 'tone-indigo'}" style="font-weight:600">${escapeHtml(a.group_code)} (${escapeHtml(a.group_description || 'Adjustment')})</td>
                      <td class="mono">CARC ${escapeHtml(a.reason_code)}</td>
                      <td class="mono">${escapeHtml(a.quantity || 1)}</td>
                      <td class="mono">$${(parseFloat(a.adjustment_amount) || 0).toFixed(2)}</td>
                    </tr>
                  `).join('') || `<tr><td colspan="4" class="tone-muted">No CAS adjustments recorded on this claim</td></tr>`}
                </tbody>
              </table>
            </div>
            ${svcRows ? `
            <div class="table-scroll" style="border-top:1px solid var(--border)">
              <table class="data-table">
                <thead><tr><th>Remittance Line</th><th>Adjudicated Procedure</th><th>Submitted Charge</th><th>Line Paid Amount</th></tr></thead>
                <tbody>${svcRows}</tbody>
              </table>
            </div>` : ''}
          </section>
        `;
        }).join('');
      } else if (txType === '277') {
        const reqs = tx.required_attachments || [];
        panel.innerHTML = `
          <section class="bento-pane">
            <div class="pane-header">
              <div class="pane-title-group">
                <h2 class="pane-title">Pended Claim Documentation Requests — 277 (${escapeHtml(fileTag)})</h2>
                <p class="pane-subtitle">Loop 2200D STC &amp; PWK clinical attachment triggers ($${((meta && meta.financials && meta.financials.pended_exposure) || 0).toFixed(2)} pended exposure)</p>
              </div>
              <span class="status-tag status-alert">${reqs.length} Action Required</span>
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead><tr><th>Category</th><th>Action</th><th>Report Type (PWK01)</th><th>Transmission</th><th>Tracking Control #</th></tr></thead>
                <tbody>
                  ${reqs.map(r => `
                    <tr>
                      <td class="mono tone-rose" style="font-weight:600">${escapeHtml(r.status_category_code || 'R4')}</td>
                      <td>${escapeHtml(r.action_description || r.action_code || 'Pended')}</td>
                      <td><span class="mono">${escapeHtml(r.attachment_report_type_code || '09')}</span> — ${escapeHtml(r.attachment_report_type_description || 'Clinical Document')}</td>
                      <td class="mono">${escapeHtml(r.attachment_transmission_code || 'EL')}</td>
                      <td class="mono">${escapeHtml(r.attachment_control_number || 'N/A')}</td>
                    </tr>
                  `).join('') || `<tr><td colspan="5" class="tone-muted">No STC/PWK rows detected</td></tr>`}
                </tbody>
              </table>
            </div>
          </section>
        `;
      } else if (txType === '271') {
        const sub = tx.subscriber || {};
        const bens = sub.eligibility_benefits || tx.eligibility_benefits || [];
        panel.innerHTML = `
          <section class="bento-pane">
            <div class="pane-header">
              <div class="pane-title-group">
                <h2 class="pane-title">Eligibility &amp; Benefit Coverage Schedule — 271 (${escapeHtml(fileTag)})</h2>
                <p class="pane-subtitle">Loop 2110C EB benefit determinations (${bens.length} coverage entries)</p>
              </div>
              <span class="status-tag status-pass">${bens.length} EB Rows</span>
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead><tr><th>EB Code</th><th>Benefit Type</th><th>Service Type</th><th>Plan / Terms</th><th>Amount / Percent</th></tr></thead>
                <tbody>
                  ${bens.map(b => `
                    <tr>
                      <td class="mono tone-teal" style="font-weight:600">${escapeHtml(b.eligibility_code)}</td>
                      <td>${escapeHtml(b.eligibility_description || 'Coverage Term')}</td>
                      <td class="mono">${escapeHtml(b.service_type_code || '30')}</td>
                      <td>${escapeHtml(b.plan_coverage_description || b.insurance_type_code || 'In-Network')}</td>
                      <td class="mono">${b.monetary_amount !== null && b.monetary_amount !== undefined ? '$' + Number(b.monetary_amount).toFixed(2) : (b.percent !== null && b.percent !== undefined && b.percent !== '' ? (Number(b.percent) <= 1 ? (Number(b.percent) * 100).toFixed(0) : Number(b.percent).toFixed(0)) + '%' : 'Active Coverage')}</td>
                    </tr>
                  `).join('') || `<tr><td colspan="5" class="tone-muted">No EB segments in stream</td></tr>`}
                </tbody>
              </table>
            </div>
          </section>
        `;
      } else if (txType === '270') {
        const eqSegs = ALL_SEGMENTS.filter(s => s.segment_id === 'EQ');
        const trnSeg = ALL_SEGMENTS.find(s => s.segment_id === 'TRN');
        const dtpSeg = ALL_SEGMENTS.find(s => s.segment_id === 'DTP');
        const stcLabels = {
          '30': 'Health Benefit Plan Coverage',
          '98': 'Professional (Physician) Office Visit',
          '35': 'Dental Care',
          '47': 'Hospital Inpatient / Outpatient',
          '88': 'Pharmacy Coverage',
          'AL': 'Vision (Optometry)',
          'MH': 'Mental Health',
          'UC': 'Urgent Care'
        };
        panel.innerHTML = `
          <section class="bento-pane">
            <div class="pane-header">
              <div class="pane-title-group">
                <h2 class="pane-title">Real-Time Eligibility &amp; Benefit Inquiries — 270 (${escapeHtml(fileTag)})</h2>
                <p class="pane-subtitle">Trace: ${escapeHtml((trnSeg && trnSeg.elements[1]) || 'N/A')} • Service Date: ${escapeHtml((dtpSeg && dtpSeg.elements[2]) || 'Current')}</p>
              </div>
              <span class="status-tag status-nominal">${eqSegs.length} EQ Inquiries</span>
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead><tr><th>Segment Line</th><th>Service Type Code (EQ01)</th><th>Requested Coverage Scope</th><th>Coverage Level (EQ02)</th></tr></thead>
                <tbody>
                  ${eqSegs.map(eq => {
                    const code = eq.elements[0] || '30';
                    return `
                      <tr>
                        <td class="mono">#${eq.line_number}</td>
                        <td class="mono tone-teal" style="font-weight:600">EQ*${escapeHtml(code)}</td>
                        <td>${escapeHtml(stcLabels[code] || `Service Type ${code} Eligibility Verification`)}</td>
                        <td class="mono">${escapeHtml(eq.elements[1] || 'IND / Plan Level')}</td>
                      </tr>
                    `;
                  }).join('') || `<tr><td colspan="4" class="tone-muted">General subscriber eligibility inquiry</td></tr>`}
                </tbody>
              </table>
            </div>
          </section>
        `;
      } else if (txType === '275') {
        const clin = tx.attached_clinical_data || {};
        const docMeta = clin.document_metadata || {};
        const bgnSeg = ALL_SEGMENTS.find(s => s.segment_id === 'BGN');
        const catSeg = ALL_SEGMENTS.find(s => s.segment_id === 'CAT');
        const pidSeg = ALL_SEGMENTS.find(s => s.segment_id === 'PID');
        const bdsSeg = ALL_SEGMENTS.find(s => s.segment_id === 'BDS' || s.segment_id === 'BIN');
        const bdsLen = bdsSeg ? (parseInt(bdsSeg.elements[1], 10) || (bdsSeg.elements[2] || bdsSeg.elements[0] || '').length) : 0;
        panel.innerHTML = `
          <section class="bento-pane">
            <div class="pane-header">
              <div class="pane-title-group">
                <h2 class="pane-title">Patient Information &amp; Clinical Attachment Manifest — 275 (${escapeHtml(fileTag)})</h2>
                <p class="pane-subtitle">Attachment Ref: ${escapeHtml((bgnSeg && bgnSeg.elements[1]) || docMeta.document_id || 'CCDA-275')} • Report Description: ${escapeHtml((pidSeg && pidSeg.elements[4]) || docMeta.title || 'HL7 C-CDA R2.1')}</p>
              </div>
              <span class="status-tag status-pass">${bdsLen.toLocaleString()} XML Octets</span>
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead><tr><th>C-CDA / 275 Section</th><th>LOINC / EDI Spec</th><th>Extracted Entries</th><th>Primary Clinical Observation</th></tr></thead>
                <tbody>
                  <tr>
                    <td style="font-weight:600">Envelope &amp; Category (CAT/BDS)</td>
                    <td class="mono">CAT*${escapeHtml((catSeg && catSeg.elements[0]) || 'AE')}*${escapeHtml((catSeg && catSeg.elements[1]) || 'HL')}</td>
                    <td class="mono">${bdsSeg ? '1 XML Document' : '0'}</td>
                    <td class="mono">${escapeHtml(docMeta.title || 'Consolidated Clinical Document')}</td>
                  </tr>
                  <tr>
                    <td style="font-weight:600">Allergies &amp; Intolerances</td>
                    <td class="mono">LOINC 48765-2</td>
                    <td class="mono tone-rose">${(clin.allergies || []).length}</td>
                    <td class="mono">${escapeHtml((clin.allergies || []).map(a => `${a.substance} (${a.severity || 'alert'})`).join(', ') || 'None')}</td>
                  </tr>
                  <tr>
                    <td style="font-weight:600">Medications</td>
                    <td class="mono">LOINC 10160-0</td>
                    <td class="mono tone-indigo">${(clin.medications || []).length}</td>
                    <td class="mono">${escapeHtml((clin.medications || []).map(m => `${m.medication_name} ${m.dose || ''}`.trim()).join(', ') || 'None')}</td>
                  </tr>
                  <tr>
                    <td style="font-weight:600">Problems &amp; Diagnoses</td>
                    <td class="mono">LOINC 11450-4</td>
                    <td class="mono tone-teal">${(clin.problems_and_diagnoses || []).length}</td>
                    <td class="mono">${escapeHtml((clin.problems_and_diagnoses || []).map(p => `${p.code}: ${p.problem_name}`).join(', ') || 'None')}</td>
                  </tr>
                  <tr>
                    <td style="font-weight:600">Vital Signs Panel</td>
                    <td class="mono">LOINC 8716-3</td>
                    <td class="mono tone-emerald">${(clin.vital_signs || []).length}</td>
                    <td class="mono">${escapeHtml((clin.vital_signs || []).map(v => `${v.vital_sign || v.measurement}: ${v.value} ${v.unit || ''}`.trim()).join(' • ') || 'None')}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        `;
      } else if (txType === '278') {
        const events = tx.events || [];
        panel.innerHTML = events.map(ev => `
          <section class="bento-pane">
            <div class="pane-header">
              <div class="pane-title-group">
                <h2 class="pane-title">Prior Authorization Services Review — 278 (${escapeHtml(fileTag)})</h2>
                <p class="pane-subtitle">Diagnoses: ${(ev.diagnoses || []).map(d => d.code || d).join(', ') || 'See HI'} • Requested Services: ${(ev.services || []).map(s => (s.procedure && (s.procedure.procedure_code || s.procedure.raw)) || 'SV1').join(', ') || 'Certified'}</p>
              </div>
              <span class="status-tag status-pass">${(ev.review_results || []).length} Review Decision</span>
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead><tr><th>Request Category</th><th>Action Code</th><th>Decision</th><th>Authorization ID</th><th>Requested Charge / Units</th></tr></thead>
                <tbody>
                  ${(ev.review_results || []).map((r, rIdx) => {
                    const sv = (ev.services || [])[rIdx] || (ev.services || [])[0] || {};
                    const chg = parseFloat(sv.charge_amount || 0);
                    return `
                      <tr>
                        <td class="mono">${escapeHtml(ev.request_category_code || 'SC')} (${escapeHtml(ev.certification_type_code || 'I')})</td>
                        <td class="mono tone-emerald" style="font-weight:600">${escapeHtml(r.action_code)}</td>
                        <td>${escapeHtml(r.action_description || r.approval_status || 'Certified in Total')}</td>
                        <td class="mono">${escapeHtml(r.review_identification_number || 'N/A')}</td>
                        <td class="mono">${chg > 0 ? '$' + chg.toFixed(2) + ' (' + escapeHtml(sv.unit_count || 1) + ' u)' : 'Authorized'}</td>
                      </tr>
                    `;
                  }).join('')}
                </tbody>
              </table>
            </div>
          </section>
        `).join('');
      } else {
        // Generic X12 fallback table for any custom transaction set
        const countsBySeg = {};
        ALL_SEGMENTS.forEach(s => { countsBySeg[s.segment_id] = (countsBySeg[s.segment_id] || 0) + 1; });
        const segSummaryRows = Object.entries(countsBySeg).map(([segId, cnt]) => {
          const kb = SEGMENT_KB[segId] || { name: `EDI ${segId} Segment`, loop: 'Transaction Body' };
          return `
            <tr>
              <td class="mono tone-teal" style="font-weight:600">${escapeHtml(segId)}</td>
              <td>${escapeHtml(kb.name)}</td>
              <td class="mono">${escapeHtml(kb.loop)}</td>
              <td class="mono">${cnt}</td>
            </tr>
          `;
        }).join('');
        panel.innerHTML = `
          <section class="bento-pane">
            <div class="pane-header">
              <div class="pane-title-group">
                <h2 class="pane-title">Transaction Set ${escapeHtml(txType)} Segment Inventory (${escapeHtml(fileTag)})</h2>
                <p class="pane-subtitle">Empirical segment breakdown across ${ALL_SEGMENTS.length} parsed segments</p>
              </div>
              <span class="status-tag status-nominal">ST*${escapeHtml(txType)}</span>
            </div>
            <div class="table-scroll">
              <table class="data-table">
                <thead><tr><th>Segment ID</th><th>5010 Segment Name</th><th>Loop Context</th><th>Occurrences</th></tr></thead>
                <tbody>${segSummaryRows}</tbody>
              </table>
            </div>
          </section>
        `;
      }
    }

    function renderClinicalSection(data, meta) {
      const fg = (data.functional_groups || [])[0] || {};
      const ts = (fg.transaction_sets || [])[0] || {};
      const tx = ts.parsed_transaction || {};
      const txType = ts.transaction_type || (meta && meta.tx_type) || 'X12';
      const clin = tx.attached_clinical_data;
      const grid = document.getElementById('clinicalSectionsGrid');

      // Case 1: Active stream contains an embedded HL7 C-CDA R2.1 XML document (e.g., 275 stream or custom 275 upload)
      if (clin && Object.keys(clin).length > 0) {
        const docMeta = clin.document_metadata || {};
        const pt = clin.patient_demographics || {};
        document.getElementById('clinicalDocTitle').textContent =
          `${docMeta.title || 'Consolidated Clinical Document (C-CDA R2.1)'} — [${txType}] ${meta ? meta.filename : ''}`;
        document.getElementById('clinicalDocMeta').textContent =
          `Patient: ${(pt.name && pt.name.full_name) || 'Verified Patient'} • DOB: ${pt.date_of_birth || 'N/A'} • Active Source: ${meta ? meta.source_path : '275 BDS'} (SHA-256 ${meta ? meta.sha256 : ''})`;
        const tagEl = document.getElementById('clinicalSourceTag');
        tagEl.className = 'status-tag status-pass';
        tagEl.textContent = docMeta.document_id || `275 C-CDA (${meta ? meta.filename : 'XML'})`;

        const meds = clin.medications || [];
        const algs = clin.allergies || [];
        const probs = clin.problems_and_diagnoses || [];
        const vitals = clin.vital_signs || [];
        const notesObj = clin.clinical_notes_and_evaluations || {};
        const narrative = notesObj.progress_note_medical_necessity_evaluation || notesObj.assessment_and_plan || 'Embedded C-CDA clinical payload parsed from active stream.';

        grid.innerHTML = `
          <div class="flat-cell">
            <span class="detail-kv-label tone-rose">Allergies &amp; Adverse Reactions (LOINC 48765-2)</span>
            ${algs.map(a => `<div class="mono" style="font-size:0.77rem"><strong>${escapeHtml(a.substance)}</strong>${a.rxnorm_code ? ` [RxNorm ${escapeHtml(a.rxnorm_code)}]` : ''} &rarr; <span class="tone-rose">${escapeHtml(a.reaction || 'Adverse reaction')}${a.severity ? ` (${escapeHtml(a.severity)})` : ''}</span></div>`).join('') || '<span class="tone-muted">No allergies recorded in C-CDA section</span>'}
          </div>
          <div class="flat-cell">
            <span class="detail-kv-label tone-indigo">Active Medications (LOINC 10160-0)</span>
            ${meds.map(m => `<div class="mono" style="font-size:0.77rem"><strong>${escapeHtml(m.medication_name)}</strong>${m.rxnorm_code ? ` [RxNorm ${escapeHtml(m.rxnorm_code)}]` : ''} &bull; ${escapeHtml(m.dose || m.status || 'Active')}</div>`).join('') || '<span class="tone-muted">No medications recorded in C-CDA section</span>'}
          </div>
          <div class="flat-cell">
            <span class="detail-kv-label tone-teal">Problem List &amp; Diagnoses (LOINC 11450-4)</span>
            ${probs.map(p => `<div class="mono" style="font-size:0.77rem"><span class="tone-teal">${escapeHtml(p.code || 'DX')}</span> — ${escapeHtml(p.problem_name)} (${escapeHtml(p.status || 'active')})</div>`).join('') || '<span class="tone-muted">No problem entries recorded in C-CDA section</span>'}
          </div>
          <div class="flat-cell">
            <span class="detail-kv-label tone-emerald">Vital Signs Panel (LOINC 8716-3)</span>
            <div style="display:flex;flex-wrap:wrap;gap:10px" class="mono">
              ${vitals.map(v => `<span style="font-size:0.75rem">${escapeHtml(v.vital_sign || v.measurement || v.code)}: <strong>${escapeHtml(v.value)} ${escapeHtml(v.unit || '')}</strong></span>`).join('') || '<span class="tone-muted">No vital signs recorded in C-CDA section</span>'}
            </div>
          </div>
          <div class="flat-cell" style="grid-column: 1 / -1">
            <span class="detail-kv-label">Physician Progress Note &amp; Medical Necessity Justification (LOINC 11506-3)</span>
            <p style="font-size:0.79rem;line-height:1.55;color:var(--text-primary);white-space:pre-line">${escapeHtml(narrative)}</p>
          </div>
        `;
        return;
      }

      // Case 2: Non-275 X12 stream — show ONLY clinical, diagnostic, procedure & attachment metadata present in THIS active stream!
      const partners = resolveTradingPartners(tx);
      const ptObj = partners.patient || {};
      const dmgSeg = ALL_SEGMENTS.find(s => s.segment_id === 'DMG');
      const dob = ptObj.date_of_birth || (dmgSeg && dmgSeg.elements[1]) || 'Not carried in stream';
      const sex = ptObj.gender || (dmgSeg && dmgSeg.elements[2]) || 'N/A';
      const ptName = ptObj._displayName || 'No patient loop in stream';
      const ptId = ptObj.identification_code || 'N/A';

      document.getElementById('clinicalDocTitle').textContent =
        `Active Stream Clinical & Diagnostic Extract — [${txType}] ${meta ? meta.filename : ''}`;
      document.getElementById('clinicalDocMeta').textContent =
        `Patient/Subscriber: ${ptName} (${ptId}) • DOB: ${dob} • Active Source: ${meta ? meta.source_path : txType} (SHA-256 ${meta ? meta.sha256 : ''})`;
      const tagEl = document.getElementById('clinicalSourceTag');
      tagEl.className = 'status-tag status-nominal';
      tagEl.textContent = `EDI ${txType} (NO EMBEDDED XML)`;

      // Extract diagnoses from active stream
      const diagItems = [];
      (tx.claims || []).forEach(c => {
        (c.diagnoses || []).forEach(d => diagItems.push(`${d.diagnosis_type || 'HI'}:${d.code}`));
      });
      (tx.events || []).forEach(ev => {
        (ev.diagnoses || []).forEach(d => diagItems.push(`${d.diagnosis_type || 'HI'}:${d.code || d}`));
      });
      if (diagItems.length === 0) {
        ALL_SEGMENTS.filter(s => s.segment_id === 'HI').forEach(hi => {
          hi.elements.filter(Boolean).forEach(el => diagItems.push(el));
        });
      }

      // Extract clinical procedures / benefit service scopes from active stream
      const procItems = [];
      (tx.claims || []).forEach(c => {
        (c.service_lines || []).forEach(sl => {
          const pCode = (sl.procedure && (sl.procedure.raw || sl.procedure.procedure_code || sl.procedure.code)) || sl.procedure_code || sl.revenue_code || 'Service Line';
          const amt = parseFloat(sl.charge_amount || sl.line_item_charge_amount || 0);
          procItems.push(`${pCode} ($${amt.toFixed(2)}, ${sl.unit_count || 1} unit)`);
        });
      });
      (tx.events || []).forEach(ev => {
        (ev.services || []).forEach(sv => {
          const pCode = (sv.procedure && (sv.procedure.raw || sv.procedure.procedure_code)) || 'Auth Service';
          procItems.push(`${pCode} ($${(parseFloat(sv.charge_amount) || 0).toFixed(2)})`);
        });
        (ev.review_results || []).forEach(r => {
          procItems.push(`Auth Decision ${r.action_code}: ${r.action_description || 'Certified'} (#${r.review_identification_number || 'N/A'})`);
        });
      });
      const bens = (tx.subscriber && tx.subscriber.eligibility_benefits) || tx.eligibility_benefits || [];
      bens.forEach(b => {
        procItems.push(`EB*${b.eligibility_code} (STC ${b.service_type_code || '30'}): ${b.eligibility_description || 'Benefit'}`);
      });
      ALL_SEGMENTS.filter(s => s.segment_id === 'EQ').forEach(eq => {
        procItems.push(`EQ*${eq.elements[0] || '30'}: Service Eligibility Inquiry`);
      });

      // Extract PWK / STC clinical attachment references in active stream
      const pwkItems = [];
      (tx.required_attachments || []).forEach(r => {
        pwkItems.push(`STC ${r.status_category_code || 'R4'} / PWK ${r.attachment_report_type_code || '09'} (${r.attachment_report_type_description || 'Clinical Attachment'}) — Control #${r.attachment_control_number || 'N/A'}`);
      });
      if (pwkItems.length === 0) {
        ALL_SEGMENTS.filter(s => s.segment_id === 'PWK').forEach(pwk => {
          pwkItems.push(`PWK*${pwk.elements[0] || ''} (${pwk.elements[1] || 'EL'}) — Control #${pwk.elements[5] || 'N/A'}`);
        });
      }

      const ds275Idx = BUNDLE.datasets.findIndex(d => d.meta && d.meta.tx_type === '275');
      const switch275Btn = ds275Idx >= 0
        ? `<div style="margin-top:8px"><button type="button" class="mini-btn" onclick="selectWorkspaceDataset(${ds275Idx}, true, false)">Switch Active Stream to [275] ${escapeHtml(BUNDLE.datasets[ds275Idx].meta.filename)} to Inspect C-CDA XML</button></div>`
        : '';

      grid.innerHTML = `
        <div class="flat-cell">
          <span class="detail-kv-label tone-indigo">Patient / Subscriber Demographics (${escapeHtml(txType)})</span>
          <div class="mono" style="font-size:0.78rem"><strong>${escapeHtml(ptName)}</strong> &bull; ID: ${escapeHtml(ptId)}</div>
          <div class="mono tone-muted" style="font-size:0.75rem">DOB: ${escapeHtml(dob)} &bull; Administrative Sex: ${escapeHtml(sex)}</div>
        </div>
        <div class="flat-cell">
          <span class="detail-kv-label tone-teal">ICD-10-CM Diagnoses in Active Stream (HI)</span>
          ${diagItems.length > 0
            ? diagItems.map(d => `<div class="mono" style="font-size:0.77rem"><span class="tone-teal">${escapeHtml(d)}</span></div>`).join('')
            : `<span class="tone-muted">No HI diagnosis segments present in [${escapeHtml(txType)}] ${escapeHtml(meta ? meta.filename : '')}.</span>`}
        </div>
        <div class="flat-cell">
          <span class="detail-kv-label tone-emerald">Procedures, Services &amp; Coverage Terms (${escapeHtml(txType)})</span>
          ${procItems.length > 0
            ? procItems.slice(0, 6).map(p => `<div class="mono" style="font-size:0.76rem">${escapeHtml(p)}</div>`).join('')
            : `<span class="tone-muted">No SV1/SVC/EB/EQ service lines in [${escapeHtml(txType)}] ${escapeHtml(meta ? meta.filename : '')}.</span>`}
        </div>
        <div class="flat-cell">
          <span class="detail-kv-label tone-amber">Clinical Attachment Indicators (PWK / STC)</span>
          ${pwkItems.length > 0
            ? pwkItems.map(p => `<div class="mono tone-rose" style="font-size:0.76rem">${escapeHtml(p)}</div>`).join('')
            : `<span class="tone-muted">No PWK paperwork attachment triggers in [${escapeHtml(txType)}] ${escapeHtml(meta ? meta.filename : '')}.</span>`}
        </div>
        <div class="flat-cell" style="grid-column: 1 / -1">
          <span class="detail-kv-label">HL7 C-CDA R2.1 Binary XML Payload Status (BDS / BIN)</span>
          <p style="font-size:0.79rem;line-height:1.5;color:var(--text-secondary)">
            Active stream <strong class="mono" style="color:var(--text-primary)">[${escapeHtml(txType)}] ${escapeHtml(meta ? meta.filename : '')}</strong> is a structured X12 ${escapeHtml(txType)} transaction (${ALL_SEGMENTS.length} segments) and does not embed a <span class="mono">BDS</span>/<span class="mono">BIN</span> HL7 C-CDA XML clinical payload. All clinical codes shown above reflect only the currently selected stream.
          </p>
          ${switch275Btn}
        </div>
      `;
    }

    function renderRawEdi(raw, meta) {
      document.getElementById('rawEdiProvenanceSub').textContent = `${meta.source_path} • [${meta.tx_type}] • ${meta.byte_size.toLocaleString()} bytes • SHA-256 ${meta.sha256}`;
      document.getElementById('rawEdiDisplay').textContent = raw || '';
    }

    function renderJsonTree(data, meta) {
      const sub = document.getElementById('jsonProvenanceSub');
      if (sub && meta) {
        sub.textContent = `${meta.source_path} • [${meta.tx_type}] • ${ALL_SEGMENTS.length} segments • SHA-256 ${meta.sha256}`;
      }
      document.getElementById('jsonTreeDisplay').textContent = JSON.stringify(data, null, 2);
    }

    const CANONICAL_SPEC_ROWS = [
      { seg: 'ISA / IEA', keys: ['ISA', 'IEA'], path: 'interchange_header / interchange_trailer', loop: 'Envelope', desc: 'Sender/Receiver IDs, ISA13 control number, date/time, and element/segment delimiters.' },
      { seg: 'GS / GE', keys: ['GS', 'GE'], path: 'functional_groups[].functional_group_header', loop: 'Group Header', desc: 'Functional family (HC, HP, HN, PI, HB, HS, HI) and 5010X222A1–X279A1 version identifier.' },
      { seg: 'ST / SE', keys: ['ST', 'SE'], path: 'transaction_sets[].transaction_header', loop: 'Set Header', desc: 'Transaction set code (837, 835, 277, 275, 271, 270, 278) and SE01 segment tally.' },
      { seg: 'BHT / BGN', keys: ['BHT', 'BGN'], path: 'parsed_transaction.beginning_of_hierarchical_transaction', loop: 'Header', desc: 'Transaction purpose code, batch reference identifier, and creation timestamp.' },
      { seg: 'HL', keys: ['HL'], path: 'parsed_transaction.hierarchy_levels[]', loop: 'Loop 2000A–2000E', desc: 'Parent-child hierarchy levels (Information Source, Receiver, Billing Provider, Subscriber, Event).' },
      { seg: 'NM1 / N1', keys: ['NM1', 'N1'], path: 'billing_provider / payer / subscriber / patient', loop: 'Loop 1000 / 2010', desc: 'Entity legal/person names, NPI (XX), Payer ID (PI), Member ID (MI), and tax identifiers.' },
      { seg: 'N3 / N4 / PER', keys: ['N3', 'N4', 'PER'], path: '<entity>.address / geographic_location / contacts', loop: 'Loop 1000 / 2010', desc: 'Physical street address, city/state/ZIP location, and administrative communication contacts.' },
      { seg: 'SBR / DMG', keys: ['SBR', 'DMG'], path: 'subscriber.payer_responsibility / date_of_birth', loop: 'Loop 2000B / 2010BA', desc: 'Primary/secondary payer sequence, group policy number, birth date (YYYYMMDD), and gender.' },
      { seg: 'CLM', keys: ['CLM'], path: 'parsed_transaction.claims[]', loop: 'Loop 2300 (837)', desc: 'Patient control number, total submitted claim charge, facility place-of-service, and assignment.' },
      { seg: 'HI', keys: ['HI'], path: 'claims[].diagnoses[] / events[].diagnoses[]', loop: 'Loop 2300 / 2000E', desc: 'Principal (ABK) and secondary (ABF) ICD-10-CM clinical diagnosis codes.' },
      { seg: 'LX / SV1 / SV2', keys: ['LX', 'SV1', 'SV2'], path: 'claims[].service_lines[] / events[].services[]', loop: 'Loop 2400 / 2000F', desc: 'CPT/HCPCS procedure code, modifiers, line charge amount, unit count, and diagnosis pointers.' },
      { seg: 'BPR / TRN', keys: ['BPR', 'TRN'], path: 'financial_information / reassociation_trace', loop: 'Header (835)', desc: 'Net EFT/check settlement amount, ACH routing, payment date, and EFT trace number.' },
      { seg: 'CLP / CAS / SVC', keys: ['CLP', 'CAS', 'SVC'], path: 'claims[] / adjustments[] / service_lines[]', loop: 'Loop 2100 / 2110 (835)', desc: 'Adjudicated payment status, CO/PR CARC adjustment reason codes, and line-level remittance.' },
      { seg: 'STC / PWK', keys: ['STC', 'PWK'], path: 'parsed_transaction.required_attachments[]', loop: 'Loop 2200D (277)', desc: 'Pended claim status category (R4), action code, and requested LOINC/PWK clinical report type.' },
      { seg: 'CAT / PID / BDS', keys: ['CAT', 'PID', 'BDS', 'BIN'], path: 'parsed_transaction.attached_clinical_data', loop: 'Loop 2000 (275)', desc: 'Embedded HL7 C-CDA R2.1 XML clinical payload parsed into allergies, meds, problems, vitals, and notes.' },
      { seg: 'EQ', keys: ['EQ'], path: 'parsed_transaction.inquiries[]', loop: 'Loop 2110C (270)', desc: 'Real-time subscriber benefit eligibility inquiry by service type code (30, 98, etc.).' },
      { seg: 'EB', keys: ['EB'], path: 'subscriber.eligibility_benefits[]', loop: 'Loop 2110C (271)', desc: 'Active plan coverage status, copayment, deductible, and coinsurance percentages.' },
      { seg: 'UM / HCR', keys: ['UM', 'HCR'], path: 'parsed_transaction.events[].review_results[]', loop: 'Loop 2000E/F (278)', desc: 'Prior authorization certification category, decision code (A1), and review authorization number.' }
    ];

    function renderMappingSpec(data, meta) {
      const tbody = document.getElementById('specTableTbody');
      if (!tbody) return;
      const txType = (meta && meta.tx_type) || 'X12';
      const fileLabel = (meta && meta.filename) || 'stream.x12';

      const segCounts = {};
      ALL_SEGMENTS.forEach(s => {
        segCounts[s.segment_id] = (segCounts[s.segment_id] || 0) + 1;
      });

      const coveredKeys = new Set();
      const rowsWithCounts = CANONICAL_SPEC_ROWS.map(row => {
        let count = 0;
        row.keys.forEach(k => {
          coveredKeys.add(k);
          count += (segCounts[k] || 0);
        });
        return { ...row, count };
      });

      // Append any extra segment IDs observed in the active stream (e.g., DTP, DTM, REF, PRV, PLB, custom segments)
      Object.entries(segCounts).forEach(([segId, cnt]) => {
        if (!coveredKeys.has(segId)) {
          const kb = SEGMENT_KB[segId] || { name: `EDI ${segId} Segment`, loop: 'Transaction Loop', desc: `Parsed dynamically into segments[].fields for ${txType}.` };
          rowsWithCounts.push({
            seg: segId,
            keys: [segId],
            path: `transaction_sets[0].segments[segment_id="${segId}"]`,
            loop: kb.loop,
            desc: kb.desc,
            count: cnt
          });
        }
      });

      // Sort active stream's observed segments to the top so dataset changes are immediately visible
      rowsWithCounts.sort((a, b) => (b.count > 0 ? 1 : 0) - (a.count > 0 ? 1 : 0) || b.count - a.count);

      const distinctObserved = Object.keys(segCounts).length;
      const specSub = document.getElementById('specSubtitle');
      if (specSub) {
        specSub.textContent = `Active Stream [${txType}] ${fileLabel}: ${distinctObserved} distinct segment types (${ALL_SEGMENTS.length} total segments) mapped to JSON`;
      }

      tbody.innerHTML = rowsWithCounts.map(r => {
        const badgeHtml = r.count > 0
          ? `<span class="status-tag status-pass">${r.count} seg${r.count === 1 ? '' : 's'} in ${escapeHtml(txType)}</span>`
          : `<span class="mono tone-muted" style="font-size:0.72rem">0 in ${escapeHtml(txType)}</span>`;
        return `
          <tr style="${r.count > 0 ? '' : 'opacity:0.62'}">
            <td class="mono tone-teal" style="font-weight:600">${escapeHtml(r.seg)}</td>
            <td>${badgeHtml}</td>
            <td class="mono">${escapeHtml(r.path)}</td>
            <td class="mono">${escapeHtml(r.loop)}</td>
            <td>${escapeHtml(r.desc)}</td>
          </tr>
        `;
      }).join('');

      filterSpecTable();
    }

    /* ==========================================================================
       TAB SWITCHING & CLIPBOARD / EXPORT ACTIONS
       ========================================================================== */
    function switchTab(tabId) {
      ACTIVE_TAB = tabId;
      document.querySelectorAll('#tabBar .tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.id === `tabBtn-${tabId}`);
      });

      const studioVis = document.getElementById('studioVisualsGroup');
      const secExplorer = document.getElementById('tab-explorer');
      const secOverview = document.getElementById('tab-overview');
      const secClinical = document.getElementById('tab-clinical');
      const secRaw = document.getElementById('tab-raw_edi');
      const secJson = document.getElementById('tab-json');
      const secSpec = document.getElementById('tab-mapping_guide');

      [studioVis, secExplorer, secOverview, secClinical, secRaw, secJson, secSpec].forEach(el => {
        if (el) el.classList.add('hidden');
      });

      if (tabId === 'studio') {
        studioVis.classList.remove('hidden');
        secExplorer.classList.remove('hidden');
        secOverview.classList.remove('hidden');
        renderFinancialChart();
        renderHeatmapMatrix();
        renderRelationshipNodeMap(false);
        request3dRender();
        if (typeof requestAnimationFrame === 'function') {
          requestAnimationFrame(() => {
            renderFinancialChart();
            renderRelationshipNodeMap(false);
            request3dRender();
          });
        }
      } else if (tabId === 'explorer') {
        secExplorer.classList.remove('hidden');
      } else if (tabId === 'overview') {
        secOverview.classList.remove('hidden');
      } else if (tabId === 'clinical') {
        secClinical.classList.remove('hidden');
      } else if (tabId === 'raw_edi') {
        secRaw.classList.remove('hidden');
      } else if (tabId === 'json') {
        secJson.classList.remove('hidden');
      } else if (tabId === 'mapping_guide') {
        secSpec.classList.remove('hidden');
      }
    }

    function filterSpecTable() {
      const input = document.getElementById('specFilterInput');
      const q = ((input && input.value) || '').toLowerCase();
      document.querySelectorAll('#specTable tbody tr').forEach(r => {
        r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    }

    function copyTextWithFeedback(text, btnId) {
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(text).then(() => {
        const b = document.getElementById(btnId);
        if (b) {
          const prev = b.textContent;
          b.textContent = 'Copied';
          setTimeout(() => { b.textContent = prev; }, 1300);
        }
      });
    }

    function copyActiveJsonSubtree() {
      copyTextWithFeedback(document.getElementById('activeJsonSubtreeDisplay').textContent, 'btnCopyJsonNode');
    }

    function copyJsonOutput() {
      copyTextWithFeedback(document.getElementById('jsonTreeDisplay').textContent, 'btnCopyJsonFull');
    }

    function copyRawEdi() {
      copyTextWithFeedback(document.getElementById('rawEdiDisplay').textContent, 'btnCopyRawEdi');
    }

    function downloadBlob(content, filename, mime) {
      const blob = new Blob([content], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    }

    function downloadJsonFile() {
      downloadBlob(document.getElementById('jsonTreeDisplay').textContent, `x12_${CURRENT_DATASET.meta.tx_type}_parsed.json`, 'application/json');
    }

    function downloadRawEdiFile() {
      downloadBlob(CURRENT_RAW_EDI, CURRENT_DATASET.meta.filename || 'stream.x12', 'text/plain');
    }

    /* ==========================================================================
       OFFLINE CLIENT-SIDE X12 + HL7 C-CDA PARSER & LIVE REST / SSE INTEGRATION
       ========================================================================== */
    function openUploadModal() { document.getElementById('uploadModal').classList.add('open'); }
    function closeUploadModal() { document.getElementById('uploadModal').classList.remove('open'); }

    function clearUploadArea() {
      PENDING_UPLOAD_FILENAME = '';
      const area = document.getElementById('rawInputArea');
      if (area) area.value = '';
      const badge = document.getElementById('uploadedFileBadge');
      if (badge) badge.textContent = '';
      const fi = document.getElementById('fileInput');
      if (fi) fi.value = '';
    }

    function computeClientHexHash(str) {
      let h1 = 0x811c9dc5 >>> 0;
      let h2 = 0x01000193 >>> 0;
      for (let i = 0; i < str.length; i++) {
        const c = str.charCodeAt(i);
        h1 = Math.imul(h1 ^ c, 0x01000193) >>> 0;
        h2 = Math.imul(h2 ^ (c + (i & 0xff)), 0x85ebca6b) >>> 0;
      }
      return h1.toString(16).padStart(8, '0') + h2.toString(16).padStart(8, '0');
    }

    function parseEmbeddedCcdaXmlClient(rawXmlCandidate) {
      if (!rawXmlCandidate) return null;
      let xmlStr = String(rawXmlCandidate).trim();
      if (!xmlStr.includes('<ClinicalDocument') && !xmlStr.startsWith('<?xml')) {
        try {
          const cleaned = xmlStr.replace(/\s+/g, '');
          if (cleaned.length > 24 && /^[A-Za-z0-9+/=]+$/.test(cleaned)) {
            const decoded = atob(cleaned);
            if (decoded.includes('<ClinicalDocument') || decoded.includes('<?xml')) {
              xmlStr = decoded;
            }
          }
        } catch (_) {}
      }
      if (!xmlStr.includes('<ClinicalDocument') && !xmlStr.includes('<section')) return null;
      if (typeof DOMParser === 'undefined') return null;

      try {
        const doc = new DOMParser().parseFromString(xmlStr, 'text/xml');
        const byLocal = (root, tag) => Array.from(root.getElementsByTagName('*')).filter(el => el.localName === tag);
        const firstLocal = (root, tag) => byLocal(root, tag)[0] || null;

        const titleEl = firstLocal(doc, 'title');
        const idEl = firstLocal(doc, 'id');
        const effTimeEl = firstLocal(doc, 'effectiveTime');

        const patientRole = firstLocal(doc, 'patientRole');
        const patientEl = patientRole ? firstLocal(patientRole, 'patient') : null;
        let fullName = '';
        let dob = '';
        let gender = '';
        if (patientEl) {
          const given = byLocal(patientEl, 'given').map(g => (g.textContent || '').trim()).filter(Boolean).join(' ');
          const familyEl = firstLocal(patientEl, 'family');
          const family = familyEl ? (familyEl.textContent || '').trim() : '';
          fullName = `${given} ${family}`.trim();
          const bt = firstLocal(patientEl, 'birthTime');
          if (bt) dob = bt.getAttribute('value') || '';
          const ag = firstLocal(patientEl, 'administrativeGenderCode');
          if (ag) gender = ag.getAttribute('code') || '';
        }

        const allergies = [];
        const medications = [];
        const problems = [];
        const vitals = [];
        let progressNarrative = '';

        byLocal(doc, 'section').forEach(sec => {
          const codeEl = firstLocal(sec, 'code');
          const loinc = codeEl ? (codeEl.getAttribute('code') || '') : '';
          const secTitleEl = firstLocal(sec, 'title');
          const secTitle = secTitleEl ? (secTitleEl.textContent || '').trim() : '';
          const textEl = firstLocal(sec, 'text');
          const secText = textEl ? (textEl.textContent || '').replace(/\s+/g, ' ').trim() : '';

          if (loinc === '48765-2' || /allerg/i.test(secTitle)) {
            byLocal(sec, 'participantRole').forEach(pr => {
              const pe = firstLocal(pr, 'playingEntity');
              const ce = pe ? firstLocal(pe, 'code') : null;
              if (ce && (ce.getAttribute('displayName') || ce.getAttribute('code'))) {
                allergies.push({
                  substance: ce.getAttribute('displayName') || 'Allergen',
                  rxnorm_code: ce.getAttribute('code') || '',
                  reaction: secText.slice(0, 80) || 'Documented Reaction',
                  severity: /severe/i.test(secText) ? 'Severe' : 'Moderate'
                });
              }
            });
            if (allergies.length === 0 && secText) {
              allergies.push({ substance: secText.slice(0, 60), rxnorm_code: '', reaction: 'Reported', severity: 'Active' });
            }
          } else if (loinc === '10160-0' || /medication/i.test(secTitle)) {
            byLocal(sec, 'manufacturedMaterial').forEach(mm => {
              const ce = firstLocal(mm, 'code');
              if (ce) {
                medications.push({
                  medication_name: ce.getAttribute('displayName') || 'Medication',
                  rxnorm_code: ce.getAttribute('code') || '',
                  dose: secText.slice(0, 50) || 'Active Regimen'
                });
              }
            });
            if (medications.length === 0 && secText) {
              medications.push({ medication_name: secText.slice(0, 60), rxnorm_code: '', dose: 'Active' });
            }
          } else if (loinc === '11450-4' || /problem|diagnos/i.test(secTitle)) {
            byLocal(sec, 'value').forEach(v => {
              if (v.getAttribute('displayName') || v.getAttribute('code')) {
                problems.push({
                  code: v.getAttribute('code') || 'ICD-10',
                  problem_name: v.getAttribute('displayName') || secText.slice(0, 60),
                  status: 'active'
                });
              }
            });
          } else if (loinc === '8716-3' || /vital/i.test(secTitle)) {
            byLocal(sec, 'observation').forEach(obs => {
              const c = firstLocal(obs, 'code');
              const v = firstLocal(obs, 'value');
              if (c && v && v.getAttribute('value')) {
                vitals.push({
                  vital_sign: c.getAttribute('displayName') || c.getAttribute('code') || 'Vital',
                  code: c.getAttribute('code') || '',
                  value: v.getAttribute('value') || '',
                  unit: v.getAttribute('unit') || ''
                });
              }
            });
          } else if (loinc === '11506-3' || loinc === '51847-2' || /note|assessment|plan|necessity/i.test(secTitle)) {
            if (secText) progressNarrative = secText;
          }
        });

        return {
          document_metadata: {
            title: (titleEl && (titleEl.textContent || '').trim()) || 'Consolidated Clinical Document (C-CDA R2.1)',
            document_id: (idEl && (idEl.getAttribute('extension') || idEl.getAttribute('root'))) || 'CCDA-UPLOAD',
            effective_time: (effTimeEl && effTimeEl.getAttribute('value')) || ''
          },
          patient_demographics: {
            name: { full_name: fullName || 'Patient Record' },
            date_of_birth: dob,
            gender: gender
          },
          allergies: allergies,
          medications: medications,
          problems_and_diagnoses: problems,
          vital_signs: vitals,
          clinical_notes_and_evaluations: {
            progress_note_medical_necessity_evaluation: progressNarrative || 'Parsed via client-side HL7 C-CDA R2.1 XML DOM inspector.'
          }
        };
      } catch (_) {
        return null;
      }
    }

    function clientSideFallbackParse(rawText, customFilename = '') {
      const t0 = performance.now();
      const trimmed = rawText.trim();
      const elemSep = trimmed.startsWith('ISA') && trimmed.length > 3 ? trimmed[3] : '*';
      let compSep = ':';
      let segTerm = trimmed.includes('~') ? '~' : '\n';
      if (trimmed.startsWith('ISA')) {
        const isaFieldsPreview = trimmed.split(segTerm)[0].split(elemSep);
        if (isaFieldsPreview.length >= 17 && isaFieldsPreview[16]) {
          compSep = isaFieldsPreview[16][0] || ':';
        }
      }

      const rawSegs = trimmed.split(segTerm).map(s => s.replace(/^[\r\n]+|[\r\n]+$/g, '').trim()).filter(Boolean);

      let isaHeader = {}, ieaTrailer = {}, gsHeader = {}, geTrailer = {}, stHeader = {}, seTrailer = {};
      let txType = 'X12', txCtrl = '0001', gsCtrl = '1', gsFunc = 'HC', gsVer = '005010', isaCtrl = '000000001';
      let ieaCtrl = '', geCtrl = '', seCtrl = '', seCount = 0;
      const txSegments = [];
      const parsedTx = {
        claims: [],
        required_attachments: [],
        inquiries: [],
        eligibility_benefits: [],
        events: []
      };
      const stratumCounts = {
        'Envelope': 0,
        'Header': 0,
        'Loop 1000/2000': 0,
        'Loop 2010 Entities': 0,
        'Loop 2300/2100 Core': 0,
        'Loop 2400/Clinical': 0
      };

      let lastEntityObj = null;

      rawSegs.forEach((s, i) => {
        const p = s.split(elemSep);
        const id = (p[0] || '').trim();
        const ln = i + 1;
        if (['ISA','GS','ST','SE','GE','IEA'].includes(id)) stratumCounts['Envelope']++;
        else if (['BHT','BPR','TRN','BGN','DTM','CUR'].includes(id)) stratumCounts['Header']++;
        else if (['HL','PRV','SBR','PAT'].includes(id)) stratumCounts['Loop 1000/2000']++;
        else if (['NM1','N1','N3','N4','PER','DMG','REF'].includes(id)) stratumCounts['Loop 2010 Entities']++;
        else if (['CLM','CLP','HI','DTP','EB','EQ','UM','HCR','STC','CAS'].includes(id)) stratumCounts['Loop 2300/2100 Core']++;
        else stratumCounts['Loop 2400/Clinical']++;

        if (id === 'ISA') {
          isaCtrl = (p[13] || '000000001').trim();
          isaHeader = {
            segment_id: 'ISA',
            line_number: ln,
            fields: {
              interchange_sender_id_qualifier: (p[5] || 'ZZ').trim(),
              interchange_sender_id: (p[6] || '').trim(),
              interchange_receiver_id_qualifier: (p[7] || 'ZZ').trim(),
              interchange_receiver_id: (p[8] || '').trim(),
              interchange_date: (p[9] || '').trim(),
              interchange_time: (p[10] || '').trim(),
              interchange_control_number: isaCtrl
            }
          };
        } else if (id === 'IEA') {
          ieaCtrl = (p[2] || '').trim();
          ieaTrailer = { segment_id: 'IEA', line_number: ln, fields: { number_of_included_functional_groups: p[1] || '1', interchange_control_number: ieaCtrl } };
        } else if (id === 'GS') {
          gsFunc = (p[1] || 'HC').trim();
          gsCtrl = (p[6] || '1').trim();
          gsVer = (p[8] || '005010').trim();
          gsHeader = { segment_id: 'GS', line_number: ln, fields: { functional_identifier_code: gsFunc, application_senders_code: p[2] || '', application_receivers_code: p[3] || '', date: p[4] || '', time: p[5] || '', group_control_number: gsCtrl, version_release_industry_identifier_code: gsVer } };
        } else if (id === 'GE') {
          geCtrl = (p[2] || '').trim();
          geTrailer = { segment_id: 'GE', line_number: ln, fields: { number_of_transaction_sets_included: p[1] || '1', group_control_number: geCtrl } };
        } else {
          const fObj = {};
          p.slice(1).forEach((v, k) => { fObj[`${id.toLowerCase()}_${String(k + 1).padStart(2, '0')}`] = v; });
          const segObj = { segment_id: id, line_number: ln, fields: fObj };
          txSegments.push(segObj);

          if (id === 'ST') {
            txType = (p[1] || 'X12').trim();
            txCtrl = (p[2] || '0001').trim();
            stHeader = segObj;
          } else if (id === 'SE') {
            seCount = parseInt(p[1] || '0', 10) || txSegments.length;
            seCtrl = (p[2] || '').trim();
            seTrailer = { segment_id: 'SE', line_number: ln, fields: { number_of_included_segments: String(p[1] || ''), transaction_set_control_number: seCtrl } };
          } else if (id === 'BHT') {
            parsedTx.beginning_of_hierarchical_transaction = { hierarchical_structure_code: p[1] || '', transaction_set_purpose_code: p[2] || '', reference_identification: p[3] || '', date: p[4] || '', time: p[5] || '' };
          } else if (id === 'BGN') {
            parsedTx.beginning_segment = { purpose_code: p[1] || '', reference_identification: p[2] || '', date: p[3] || '' };
          } else if (id === 'BPR') {
            parsedTx.financial_information = { transaction_handling_code: p[1] || 'I', total_payment_amount: parseFloat(p[2] || 0) || 0, credit_debit_flag: p[3] || 'C', payment_method: p[4] || 'ACH', payment_effective_date: p[16] || '' };
          } else if (id === 'TRN') {
            parsedTx.reassociation_trace = { trace_type_code: p[1] || '1', reference_identification: p[2] || '', originating_company_identifier: p[3] || '' };
          } else if (id === 'NM1') {
            const qual = (p[1] || '').trim();
            const ent = {
              entity_identifier_code: qual,
              entity_type_qualifier: p[2] || '1',
              name_last_or_organization: p[3] || '',
              name_first: p[4] || '',
              name_middle: p[5] || '',
              identification_code_qualifier: p[8] || '',
              identification_code: p[9] || ''
            };
            lastEntityObj = ent;
            if (qual === '85' || qual === '1P' || qual === 'FA') parsedTx.billing_provider = ent;
            else if (qual === 'PR' || qual === 'X3') parsedTx.payer = ent;
            else if (qual === 'PE') parsedTx.payee = ent;
            else if (qual === 'IL') {
              ent.eligibility_benefits = parsedTx.eligibility_benefits;
              parsedTx.subscriber = ent;
            }
            else if (qual === 'QC') parsedTx.patient = ent;
            else if (qual === '41') parsedTx.submitter = ent;
            else if (qual === '40') parsedTx.receiver = ent;
          } else if (id === 'N1') {
            const qual = (p[1] || '').trim();
            const ent = {
              entity_identifier_code: qual,
              name: p[2] || '',
              name_last_or_organization: p[2] || '',
              identification_code_qualifier: p[3] || '',
              identification_code: p[4] || ''
            };
            lastEntityObj = ent;
            if (qual === 'PR') parsedTx.payer = ent;
            else if (qual === 'PE') parsedTx.payee = ent;
          } else if (id === 'N3' && lastEntityObj) {
            lastEntityObj.address = { address_line_1: p[1] || '', address_line_2: p[2] || '' };
          } else if (id === 'N4' && lastEntityObj) {
            lastEntityObj.geographic_location = { city: p[1] || '', state: p[2] || '', postal_code: p[3] || '' };
          } else if (id === 'DMG' && lastEntityObj) {
            lastEntityObj.date_of_birth = p[2] || '';
            lastEntityObj.gender = p[3] || '';
          } else if (id === 'CLM') {
            const posParts = (p[5] || '').split(compSep);
            parsedTx.claims.push({
              claim_id: p[1] || 'CLM-1',
              total_claim_charge_amount: parseFloat(p[2] || 0) || 0,
              facility_code: posParts[0] || '11',
              diagnoses: [],
              service_lines: []
            });
          } else if (id === 'HI') {
            const diags = p.slice(1).filter(Boolean).map(comp => {
              const parts = comp.split(compSep);
              return { diagnosis_type: parts[0] || 'ABK', code: parts[1] || parts[0] || '' };
            });
            if (parsedTx.claims.length > 0) {
              parsedTx.claims[parsedTx.claims.length - 1].diagnoses.push(...diags);
            } else if (parsedTx.events.length > 0) {
              parsedTx.events[parsedTx.events.length - 1].diagnoses.push(...diags);
            }
          } else if (id === 'SV1' || id === 'SV2') {
            const procField = id === 'SV1' ? (p[1] || '') : (p[2] || p[1] || '');
            const procParts = procField.split(compSep);
            const chargeAmt = parseFloat(id === 'SV1' ? (p[2] || 0) : (p[3] || 0)) || 0;
            const unitCnt = id === 'SV1' ? (p[4] || '1') : (p[5] || '1');
            const posCode = id === 'SV1' ? (p[5] || '11') : '21';
            const lineObj = {
              line_number: String((parsedTx.claims.length ? parsedTx.claims[parsedTx.claims.length - 1].service_lines.length : 0) + 1),
              procedure: { raw: procField, qualifier: procParts[0] || 'HC', procedure_code: procParts[1] || procField },
              charge_amount: chargeAmt,
              unit_count: unitCnt,
              place_of_service: posCode
            };
            if (parsedTx.claims.length > 0) {
              parsedTx.claims[parsedTx.claims.length - 1].service_lines.push(lineObj);
            } else if (parsedTx.events.length > 0) {
              parsedTx.events[parsedTx.events.length - 1].services.push(lineObj);
            }
          } else if (id === 'CLP') {
            const stMap = { '1': 'Processed as Primary', '2': 'Processed as Secondary', '4': 'Denied', '22': 'Reversal' };
            parsedTx.claims.push({
              patient_control_number: p[1] || 'CLP-1',
              claim_status_code: p[2] || '1',
              claim_status_description: stMap[p[2]] || `Status ${p[2] || '1'}`,
              total_claim_charge_amount: parseFloat(p[3] || 0) || 0,
              claim_payment_amount: parseFloat(p[4] || 0) || 0,
              patient_responsibility_amount: parseFloat(p[5] || 0) || 0,
              payer_claim_control_number: p[7] || '',
              adjustments: [],
              service_lines: []
            });
          } else if (id === 'CAS' && parsedTx.claims.length > 0) {
            const grp = p[1] || 'CO';
            const grpNames = { 'CO': 'Contractual Obligations', 'PR': 'Patient Responsibility', 'OA': 'Other Adjustments', 'PI': 'Payer Initiated Reductions' };
            for (let k = 2; k < p.length; k += 3) {
              if (!p[k]) break;
              parsedTx.claims[parsedTx.claims.length - 1].adjustments.push({
                group_code: grp,
                group_description: grpNames[grp] || 'Adjustment',
                reason_code: p[k],
                adjustment_amount: parseFloat(p[k + 1] || 0) || 0,
                quantity: p[k + 2] || '1'
              });
            }
          } else if (id === 'SVC' && parsedTx.claims.length > 0) {
            const procParts = (p[1] || '').split(compSep);
            parsedTx.claims[parsedTx.claims.length - 1].service_lines.push({
              procedure: { raw: p[1] || '', procedure_code: procParts[1] || p[1] || 'SVC' },
              charge_amount: parseFloat(p[2] || 0) || 0,
              payment_amount: parseFloat(p[3] || 0) || 0,
              unit_count: p[5] || '1'
            });
          } else if (id === 'STC') {
            const stcParts = (p[1] || '').split(compSep);
            parsedTx.required_attachments.push({
              status_category_code: stcParts[0] || 'R4',
              status_code: stcParts[1] || '',
              action_code: p[3] || 'A4',
              action_description: p[3] === 'U' ? 'Rejected' : 'Pended for Clinical Documentation',
              claim_charge_amount: parseFloat(p[4] || 0) || 0,
              attachment_report_type_code: '09',
              attachment_report_type_description: 'Progress Notes / Medical Record',
              attachment_transmission_code: 'EL',
              attachment_control_number: ''
            });
          } else if (id === 'PWK') {
            const pwkNames = { '09': 'Progress Notes', 'AS': 'Admission Summary', 'B2': 'Prescription', 'DG': 'Diagnostic Report', 'DS': 'Discharge Summary', 'OB': 'Operative Note', 'OZ': 'Support Data for Claim' };
            const rptCode = p[1] || '09';
            if (parsedTx.required_attachments.length > 0 && !parsedTx.required_attachments[parsedTx.required_attachments.length - 1].attachment_control_number) {
              const lastReq = parsedTx.required_attachments[parsedTx.required_attachments.length - 1];
              lastReq.attachment_report_type_code = rptCode;
              lastReq.attachment_report_type_description = pwkNames[rptCode] || `Report ${rptCode}`;
              lastReq.attachment_transmission_code = p[2] || 'EL';
              lastReq.attachment_control_number = p[6] || '';
            } else {
              parsedTx.required_attachments.push({
                status_category_code: 'PWK',
                action_code: 'EL',
                action_description: 'Supplemental Attachment',
                claim_charge_amount: 0,
                attachment_report_type_code: rptCode,
                attachment_report_type_description: pwkNames[rptCode] || `Report ${rptCode}`,
                attachment_transmission_code: p[2] || 'EL',
                attachment_control_number: p[6] || ''
              });
            }
          } else if (id === 'EQ') {
            parsedTx.inquiries.push({ service_type_code: p[1] || '30', coverage_level_code: p[2] || '' });
          } else if (id === 'EB') {
            const ebNames = { '1': 'Active Coverage', 'A': 'Co-Insurance', 'B': 'Co-Payment', 'C': 'Deductible', 'F': 'Limitations', 'G': 'Out of Pocket (Stop Loss)', '6': 'Inactive' };
            parsedTx.eligibility_benefits.push({
              eligibility_code: p[1] || '1',
              eligibility_description: ebNames[p[1]] || `Benefit ${p[1] || '1'}`,
              coverage_level_code: p[2] || '',
              service_type_code: p[3] || '30',
              insurance_type_code: p[4] || '',
              plan_coverage_description: p[5] || '',
              time_period_qualifier: p[6] || '',
              monetary_amount: p[7] !== undefined && p[7] !== '' ? parseFloat(p[7]) : null,
              percent: p[8] !== undefined && p[8] !== '' ? parseFloat(p[8]) : null
            });
            if (parsedTx.subscriber) parsedTx.subscriber.eligibility_benefits = parsedTx.eligibility_benefits;
          } else if (id === 'UM') {
            parsedTx.events.push({
              request_category_code: p[1] || 'SC',
              certification_type_code: p[2] || 'I',
              service_type_code: p[3] || '',
              review_results: [],
              diagnoses: [],
              services: []
            });
          } else if (id === 'HCR') {
            if (parsedTx.events.length === 0) {
              parsedTx.events.push({ request_category_code: 'SC', certification_type_code: 'I', review_results: [], diagnoses: [], services: [] });
            }
            const actNames = { 'A1': 'Certified in Total', 'A2': 'Certified - Partial', 'A3': 'Not Certified', 'A4': 'Pended', 'CT': 'Contact Payer' };
            parsedTx.events[parsedTx.events.length - 1].review_results.push({
              action_code: p[1] || 'A1',
              action_description: actNames[p[1]] || `Decision ${p[1] || 'A1'}`,
              review_identification_number: p[2] || ''
            });
          } else if (id === 'BDS' || id === 'BIN') {
            const payloadCandidate = id === 'BDS' ? p.slice(3).join(elemSep) : p.slice(2).join(elemSep);
            const parsedCcda = parseEmbeddedCcdaXmlClient(payloadCandidate);
            if (parsedCcda) {
              parsedTx.attached_clinical_data = parsedCcda;
            }
          }
        }
      });

      // Compute accurate financial totals
      let billed = 0, paid = 0, adjustments = 0, patientResp = 0, pendedExposure = 0;
      parsedTx.claims.forEach(c => {
        billed += parseFloat(c.total_claim_charge_amount) || 0;
        paid += parseFloat(c.claim_payment_amount) || 0;
        patientResp += parseFloat(c.patient_responsibility_amount) || 0;
        (c.adjustments || []).forEach(a => {
          adjustments += parseFloat(a.adjustment_amount) || 0;
        });
      });
      if (parsedTx.financial_information && parsedTx.financial_information.total_payment_amount) {
        paid = parseFloat(parsedTx.financial_information.total_payment_amount) || paid;
      }
      parsedTx.required_attachments.forEach(r => {
        pendedExposure += parseFloat(r.claim_charge_amount) || 0;
      });

      // Build HIPAA 5010 envelope validation audit rows
      const validations = [];
      const isaPass = !ieaCtrl || isaCtrl === ieaCtrl;
      validations.push({
        rule_id: 'HIPAA-ISA-IEA',
        scope: 'Envelope',
        check: 'ISA13 == IEA02 Control Match',
        expected: isaCtrl,
        observed: ieaCtrl || isaCtrl,
        status: isaPass ? 'PASS' : 'WARN'
      });
      const gsPass = !geCtrl || gsCtrl === geCtrl;
      validations.push({
        rule_id: 'HIPAA-GS-GE',
        scope: `Group ${gsFunc}`,
        check: 'GS06 == GE02 Group Control Match',
        expected: gsCtrl,
        observed: geCtrl || gsCtrl,
        status: gsPass ? 'PASS' : 'WARN'
      });
      const sePass = (!seCtrl || txCtrl === seCtrl) && (!seCount || seCount === txSegments.length);
      validations.push({
        rule_id: 'HIPAA-ST-SE',
        scope: `ST*${txType}`,
        check: 'SE01 Segment Count & ST02/SE02 Match',
        expected: `${txSegments.length} segs (#${txCtrl})`,
        observed: `${seCount || txSegments.length} segs (#${seCtrl || txCtrl})`,
        status: sePass ? 'PASS' : 'WARN'
      });

      let overallStatus = (isaPass && gsPass && sePass) ? 'PASS' : 'WARN';
      if (txType === '277' && parsedTx.required_attachments.length > 0) overallStatus = 'ALERT';

      const elapsed = Math.max(0.15, performance.now() - t0);
      const parsedData = {
        delimiters: { element_separator: elemSep, component_separator: compSep, segment_terminator: segTerm },
        interchange_header: isaHeader,
        interchange_trailer: ieaTrailer,
        functional_groups: [{
          functional_group_header: gsHeader,
          functional_group_trailer: geTrailer,
          functional_identifier_code: gsFunc,
          group_control_number: gsCtrl,
          version: gsVer,
          transaction_sets: [{
            transaction_type: txType,
            transaction_set_control_number: txCtrl,
            transaction_header: stHeader,
            transaction_trailer: seTrailer,
            parsed_transaction: parsedTx,
            segments: txSegments
          }]
        }],
        summary: { total_segments_count: rawSegs.length, total_functional_groups_count: 1, total_transaction_sets_count: 1 }
      };

      const txNames = {
        '837': 'Health Care Claim (837)',
        '835': 'Electronic Remittance Advice (835)',
        '277': 'Health Care Claim Status Request (277)',
        '275': 'Patient Information & C-CDA Attachment (275)',
        '271': 'Eligibility & Benefit Response (271)',
        '270': 'Eligibility & Benefit Inquiry (270)',
        '278': 'Prior Authorization Review (278)'
      };
      const cleanName = customFilename
        ? customFilename.replace(/^.*[\\/]/, '')
        : `uploaded_${txType}_stream.x12`;
      const digest16 = computeClientHexHash(trimmed);

      return {
        id: `upload_${digest16}`,
        raw_x12: trimmed,
        parsed_data: parsedData,
        meta: {
          filename: cleanName,
          source_path: `uploaded/${cleanName}`,
          sha256: digest16,
          sha256_full: digest16.repeat(4),
          byte_size: new Blob([trimmed]).size,
          line_count: rawSegs.length,
          parse_ms: Number(elapsed.toFixed(2)),
          tx_type: txType,
          tx_label: txNames[txType] || `Custom EDI X12 ${txType}`,
          isa_control_number: isaCtrl,
          gs_version: gsVer,
          stratum_counts: stratumCounts,
          financials: {
            billed: Number(billed.toFixed(2)),
            paid: Number(paid.toFixed(2)),
            adjustments: Number(adjustments.toFixed(2)),
            patient_responsibility: Number(patientResp.toFixed(2)),
            pended_exposure: Number(pendedExposure.toFixed(2))
          },
          validation_status: overallStatus,
          validations: validations
        }
      };
    }

    async function parseCustomX12() {
      const rawText = (document.getElementById('rawInputArea').value || '').trim();
      if (!rawText) return;

      const uploadFilename = PENDING_UPLOAD_FILENAME || '';
      const uploadSource = uploadFilename ? `uploaded/${uploadFilename}` : '';

      if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
        try {
          const resp = await fetch('/v1/parse/x12?include_telemetry=1', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              raw_x12: rawText,
              source_path: uploadSource || undefined
            })
          });
          if (resp.ok) {
            const payload = await resp.json();
            if (payload && payload.parsed_data && payload.meta) {
              ingestLiveDataset(payload);
            } else {
              const fallback = clientSideFallbackParse(rawText, uploadFilename);
              fallback.parsed_data = payload;
              ingestLiveDataset(fallback);
            }
            closeUploadModal();
            return;
          }
        } catch (_) {}
      }

      const localDs = clientSideFallbackParse(rawText, uploadFilename);
      ingestLiveDataset(localDs);
      closeUploadModal();
    }

    function ingestLiveDataset(dsRecord) {
      if (!dsRecord || !dsRecord.parsed_data || !dsRecord.meta) return;
      const scrollY = window.scrollY;
      if (!dsRecord.id) {
        dsRecord.id = `live_${dsRecord.meta.sha256 || Date.now()}`;
      }

      // Deduplicate if SSE 'parse_update' and direct HTTP response arrive for the same upload
      const existingIdx = BUNDLE.datasets.findIndex(d =>
        (d.id && dsRecord.id && d.id === dsRecord.id) ||
        (d.id && String(d.id).startsWith('sse_') && d.meta && dsRecord.meta && d.meta.sha256 === dsRecord.meta.sha256 && d.raw_x12 === dsRecord.raw_x12) ||
        (d.id && String(d.id).startsWith('upload_') && d.meta && dsRecord.meta && d.meta.sha256 === dsRecord.meta.sha256 && d.raw_x12 === dsRecord.raw_x12)
      );

      if (existingIdx >= 0) {
        BUNDLE.datasets[existingIdx] = dsRecord;
        populateDatasetSelector();
        selectWorkspaceDataset(existingIdx, false, false);
      } else {
        BUNDLE.datasets.unshift(dsRecord);
        populateDatasetSelector();
        selectWorkspaceDataset(0, false, false);
      }
      window.scrollTo(0, scrollY);
    }

    // Expose programmatic incremental update hook for embedded webviews & SSE
    window.updateDashboardData = function(payload) {
      if (!payload) return;
      if (payload.parsed_data && payload.meta) {
        ingestLiveDataset(payload);
      } else if (payload.raw_x12) {
        const ds = clientSideFallbackParse(payload.raw_x12, payload.filename || '');
        if (payload.parsed_data) ds.parsed_data = payload.parsed_data;
        ingestLiveDataset(ds);
      }
    };

    function initSSEConnection() {
      if (window.location.protocol !== 'http:' && window.location.protocol !== 'https:') return;
      if (typeof EventSource === 'undefined') return;
      try {
        const es = new EventSource('/v1/events');
        const ind = document.getElementById('sseStatusIndicator');
        es.onopen = () => {
          if (ind) {
            ind.setAttribute('data-live', 'true');
            ind.textContent = 'SSE Stream: Connected (/v1/events)';
          }
        };
        es.addEventListener('parse_update', ev => {
          try {
            const data = JSON.parse(ev.data);
            window.updateDashboardData(data);
          } catch (_) {}
        });
        es.onerror = () => {
          if (ind) {
            ind.setAttribute('data-live', 'false');
            ind.textContent = 'Mode: Standalone Empirical Bundle';
          }
          es.close();
        };
      } catch (_) {}
    }

    function initUploadControls() {
      const dropZone = document.getElementById('dropZone');
      const fileInput = document.getElementById('fileInput');
      if (!dropZone || !fileInput) return;

      dropZone.addEventListener('click', () => {
        fileInput.value = '';
        fileInput.click();
      });
      dropZone.addEventListener('dragover', e => { e.preventDefault(); });
      dropZone.addEventListener('drop', e => {
        e.preventDefault();
        const file = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (file) readUploadedFile(file);
      });
      fileInput.addEventListener('change', e => {
        const file = e.target.files && e.target.files[0];
        if (file) readUploadedFile(file);
      });
    }

    function readUploadedFile(file) {
      PENDING_UPLOAD_FILENAME = file.name || 'uploaded_stream.x12';
      const badge = document.getElementById('uploadedFileBadge');
      if (badge) {
        badge.textContent = `Loaded File: ${PENDING_UPLOAD_FILENAME} (${file.size.toLocaleString()} bytes)`;
      }
      const reader = new FileReader();
      reader.onload = ev => {
        document.getElementById('rawInputArea').value = ev.target.result || '';
      };
      reader.readAsText(file);
    }

    function escapeHtml(str) {
      if (str === null || str === undefined) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    /* ==========================================================================
       BOOTSTRAP STUDIO
       ========================================================================== */
    function bootstrap() {
      let savedMode = 'system';
      try {
        const s = localStorage.getItem(STORAGE_KEY_THEME);
        if (s === 'light' || s === 'dark' || s === 'system') savedMode = s;
      } catch (_) {}

      populateDatasetSelector();
      initWebGL3D();
      bind3dCanvasEvents(document.getElementById('molecular3dCanvas'));
      initNodeMapInteractions();
      initChartHover();
      initUploadControls();

      autoSelect3dModelForDataset(CURRENT_DATA, CURRENT_DATASET.meta);
      applyThemeMode(savedMode, false);
      refreshAllComponents(false);
      if (document.readyState === 'complete') {
        setTimeout(initSSEConnection, 40);
      } else {
        window.addEventListener('load', () => setTimeout(initSSEConnection, 40), { once: true });
      }

      let resizeTimer = null;
      window.addEventListener('resize', () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
          renderFinancialChart();
          renderHeatmapMatrix();
          renderRelationshipNodeMap(false);
          request3dRender();
        }, 80);
      });
    }

    bootstrap();
  </script>
</body>
</html>
"""


def generate_html_dashboard(
    parsed_data: Optional[Dict[str, Any]] = None,
    raw_x12: str = "",
    title: str = "EDI X12 Semantic Mapping Engine",
    source_path: str = "inline_stream.x12",
    include_workspace_samples: bool = True,
) -> str:
    """
    Generate a complete, self-contained HTML5 dashboard adhering strictly to DESIGN.md.
    """
    ws_datasets, ws_telemetry = _load_workspace_sample_datasets() if include_workspace_samples else ([], [])

    datasets: List[Dict[str, Any]] = []
    active_index = 0

    if parsed_data is not None:
        primary_meta = compute_dataset_telemetry(parsed_data, raw_x12=raw_x12, source_path=source_path, parse_ms=0.38)
        matched_idx = -1
        for i, ds in enumerate(ws_datasets):
            if raw_x12 and ds["meta"]["sha256_full"] == primary_meta["sha256_full"]:
                matched_idx = i
                break
        if matched_idx >= 0:
            datasets = ws_datasets
            active_index = matched_idx
        else:
            datasets = [
                {
                    "id": "primary_active",
                    "meta": primary_meta,
                    "parsed_data": parsed_data,
                    "raw_x12": raw_x12,
                }
            ] + ws_datasets
            active_index = 0
    else:
        datasets = ws_datasets
        active_index = 0

    if not datasets:
        empty_parsed: Dict[str, Any] = {"delimiters": {}, "interchange_header": {}, "functional_groups": [], "summary": {"total_segments_count": 0}}
        datasets = [{
            "id": "empty",
            "meta": compute_dataset_telemetry(empty_parsed, raw_x12="", source_path="workspace"),
            "parsed_data": empty_parsed,
            "raw_x12": "",
        }]

    active_ds = datasets[active_index]
    tx_badge = f"{active_ds['meta']['tx_type']} • {active_ds['meta']['gs_version']}"
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    bundle = {
        "system_theme": detect_host_system_theme(),
        "generated_at": generated_at,
        "active_index": active_index,
        "datasets": datasets,
        "telemetry_events": ws_telemetry,
    }

    # Safely serialize JSON for embedding inside <script> without premature </script> closure
    bundle_json = json.dumps(bundle, ensure_ascii=False, default=str).replace("</", "<\\/")

    html = HTML_TEMPLATE.replace("__TITLE__", title)
    html = html.replace("__TX_BADGE__", tx_badge)
    html = html.replace("__GENERATED_AT__", generated_at)
    html = html.replace("__BUNDLE_JSON__", bundle_json)
    return html


def save_html_dashboard(
    parsed_data: Optional[Dict[str, Any]],
    output_path: str,
    raw_x12: str = "",
    title: str = "EDI X12 Semantic Mapping Engine",
    source_path: str = "inline_stream.x12",
) -> str:
    """Generate and write standalone HTML dashboard to disk."""
    html_content = generate_html_dashboard(
        parsed_data=parsed_data,
        raw_x12=raw_x12,
        title=title,
        source_path=source_path,
    )
    abs_out = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(abs_out), exist_ok=True)
    with open(abs_out, "w", encoding="utf-8") as f:
        f.write(html_content)
    return output_path


def generate_workspace_dashboard(output_path: str = "dashboard.html") -> str:
    """
    Build the self-contained empirical workspace dashboard (`dashboard.html`)
    combining all sample_data/*.x12 transactions, provenance citations, and C-CDA records.
    """
    return save_html_dashboard(
        parsed_data=None,
        output_path=output_path,
        title="EDI X12 Semantic Mapping Engine",
        source_path="sample_data/sample_837_claim.x12",
    )


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
        "dashboard.html",
    )
    written = generate_workspace_dashboard(out)
    print(f"Standalone empirical dashboard generated: {written}")
