"""
Command-Line Interface for X12-to-JSON Healthcare Parser.

Usage:
    python3 -m x12_parser.cli <input_file.x12> [--output <output_file.json>] [--pretty]
"""

import sys
import os
import json
import argparse
from .engine.base_parser import X12Parser


def main():
    parser = argparse.ArgumentParser(
        description="Enterprise EDI X12 (5010) to JSON Parser with C-CDA XML Integration."
    )
    parser.add_argument("input_file", nargs="?", help="Path to input X12 EDI raw file (or '-' for stdin)")
    parser.add_argument("-o", "--output", help="Path to write output JSON file (default: stdout)")
    parser.add_argument("-p", "--pretty", action="store_true", default=True, help="Pretty print JSON output")
    parser.add_argument("-s", "--summary", action="store_true", help="Print summary of parsed transaction sets")
    parser.add_argument("-v", "--version", action="version", version="x12-parser 1.0.0")

    args = parser.parse_args()

    # Read input
    if not args.input_file or args.input_file == "-":
        if sys.stdin.isatty():
            parser.print_help()
            sys.exit(1)
        raw_x12 = sys.stdin.read()
    else:
        if not os.path.exists(args.input_file):
            print(f"Error: File not found: {args.input_file}", file=sys.stderr)
            sys.exit(1)
        with open(args.input_file, "r", encoding="utf-8", errors="replace") as f:
            raw_x12 = f.read()

    try:
        parsed_data = X12Parser.parse(raw_x12)
    except Exception as e:
        print(f"Error parsing X12 content: {e}", file=sys.stderr)
        sys.exit(1)

    if args.summary:
        print("=" * 60)
        print("X12 EDI PARSER SUMMARY REPORT")
        print("=" * 60)
        summary = parsed_data.get("summary", {})
        print(f"Total Segments:         {summary.get('total_segments_count')}")
        print(f"Functional Groups:      {summary.get('total_functional_groups_count')}")
        print(f"Transaction Sets:       {summary.get('total_transaction_sets_count')}")
        print("-" * 60)

        for g_idx, group in enumerate(parsed_data.get("functional_groups", []), start=1):
            print(f"Group #{g_idx}: Code={group.get('functional_identifier_code')} Version={group.get('version')}")
            for tx_idx, tx in enumerate(group.get("transaction_sets", []), start=1):
                tx_type = tx.get("transaction_type")
                tx_ctrl = tx.get("transaction_set_control_number")
                print(f"  └─ Transaction #{tx_idx}: Type={tx_type} ControlNo={tx_ctrl}")
                
                parsed_tx = tx.get("parsed_transaction", {})
                if tx_type == "837":
                    claims = parsed_tx.get("claims", [])
                    print(f"     Claims Count: {len(claims)}")
                    for c in claims:
                        print(f"     Claim ID: {c.get('claim_id')}, Charge: ${c.get('total_claim_charge_amount')}")
                elif tx_type == "835":
                    claims = parsed_tx.get("claims", [])
                    fin = parsed_tx.get("financial_information", {})
                    print(f"     Payment Amount: ${fin.get('total_payment_amount')}, Method: {fin.get('payment_method')}")
                    print(f"     Remittance Claims: {len(claims)}")
                elif tx_type == "277":
                    req_att = parsed_tx.get("required_attachments", [])
                    print(f"     Required Attachments Flagged: {len(req_att)}")
                    for a in req_att:
                        print(f"     - Type: {a.get('attachment_report_type_description')} (Code: {a.get('attachment_report_type_code')}), Transmission: {a.get('attachment_transmission_code')}")
                elif tx_type == "275":
                    clin = parsed_tx.get("attached_clinical_data", {})
                    meta = clin.get("document_metadata", {})
                    pt = clin.get("patient_demographics", {})
                    print(f"     Clinical C-CDA Title: {meta.get('title')}")
                    print(f"     Patient: {pt.get('name', {}).get('full_name')} (DOB: {pt.get('date_of_birth')})")
                    print(f"     Allergies: {len(clin.get('allergies', []))}, Medications: {len(clin.get('medications', []))}, Problems: {len(clin.get('problems_and_diagnoses', []))}, Vitals: {len(clin.get('vital_signs', []))}")
        print("=" * 60)

    # Output JSON
    indent = 2 if args.pretty else None
    json_out = json.dumps(parsed_data, indent=indent, default=str)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_out)
        print(f"Structured JSON output successfully written to: {args.output}")
    elif not args.summary:
        print(json_out)


if __name__ == "__main__":
    main()
