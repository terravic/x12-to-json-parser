#!/usr/bin/env python3
"""
Visual Dashboard Generator for EDI X12 Healthcare Transactions.

This script parses raw EDI X12 files (837, 835, 270, 271, 277, 275, 278) and produces
an interactive, responsive HTML visual dashboard alongside structured JSON output.

Usage:
    python3 skills/x12-healthcare-parser/scripts/generate_visual_dashboard.py <input.x12> -o <dashboard.html>
"""

import sys
import os
import json
import argparse

# Add project root to sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from x12_parser.engine.base_parser import X12Parser


def main():
    parser = argparse.ArgumentParser(
        description="Generate interactive visual dashboard from EDI X12 healthcare transaction."
    )
    parser.add_argument("input_file", nargs="?", help="Path to input X12 EDI raw file (or '-' for stdin)")
    parser.add_argument("-o", "--output", default="docs/x12_dashboard.html", help="Path to save generated HTML dashboard (default: docs/x12_dashboard.html)")
    parser.add_argument("-j", "--json-output", help="Optional path to save structured JSON output")
    parser.add_argument("-t", "--title", help="Custom title for the dashboard")
    parser.add_argument("-s", "--summary", action="store_true", help="Print summary of parsed transaction sets to stdout")

    args = parser.parse_args()

    # Read raw content
    if not args.input_file or args.input_file == "-":
        if sys.stdin.isatty():
            parser.print_help()
            sys.exit(1)
        raw_x12 = sys.stdin.read()
        file_label = "EDI Transaction"
    else:
        if not os.path.exists(args.input_file):
            print(f"Error: File not found: {args.input_file}", file=sys.stderr)
            sys.exit(1)
        with open(args.input_file, "r", encoding="utf-8", errors="replace") as f:
            raw_x12 = f.read()
        file_label = os.path.basename(args.input_file)

    # Parse X12 data
    try:
        parsed_data = X12Parser.parse(raw_x12)
    except Exception as e:
        print(f"Error parsing X12 content: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine dashboard title
    title = args.title or f"Dashboard - {file_label}"

    # Generate and save HTML Dashboard
    output_html = os.path.normpath(args.output)
    X12Parser.generate_dashboard(
        parsed_data,
        output_path=output_html,
        raw_x12=raw_x12,
        title=title
    )

    # Optional JSON output
    if args.json_output:
        json_path = os.path.normpath(args.json_output)
        os.makedirs(os.path.dirname(json_path) or ".", exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(parsed_data, f, indent=2, default=str)
        print(f"Structured JSON saved: {json_path}")

    # Summary
    summary = parsed_data.get("summary", {})
    first_group = (parsed_data.get("functional_groups") or [{}])[0]
    first_tx = (first_group.get("transaction_sets") or [{}])[0]
    tx_type = first_tx.get("transaction_type", "Unknown")

    print("=" * 65)
    print("VISUAL DASHBOARD GENERATED")
    print("=" * 65)
    print(f"Transaction Type:      {tx_type}")
    print(f"Total Segments:        {summary.get('total_segments_count')}")
    print(f"Functional Groups:     {summary.get('total_functional_groups_count')}")
    print(f"Transaction Sets:      {summary.get('total_transaction_sets_count')}")
    print("-" * 65)
    print(f"Dashboard HTML:        {output_html}")
    print("=" * 65)


if __name__ == "__main__":
    main()
