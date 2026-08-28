"""
Example: End-to-End Parsing and Interactive Visual Dashboard Generation.

Demonstrates parsing an EDI X12 claim transaction (837) and generating
an interactive visual dashboard.
"""

import sys
import os

# Add project root to sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from x12_parser import X12Parser
from sample_data import read_sample


def main():
    # 1. Load sample 837 Claim EDI file
    raw_x12 = read_sample("sample_837_claim.x12")

    # 2. Parse X12 text into structured Python dictionary
    parsed_json = X12Parser.parse(raw_x12)
    print("Parsed Transaction Summary:")
    print(f"  Total Segments: {parsed_json['summary']['total_segments_count']}")
    
    first_tx = parsed_json["functional_groups"][0]["transaction_sets"][0]["parsed_transaction"]
    claims = first_tx.get("claims", [])
    print(f"  Claims Extracted: {len(claims)}")
    for c in claims:
        print(f"  - Claim ID: {c.get('claim_id')}, Billed Charges: ${c.get('total_claim_charge_amount')}")

    # 3. Generate Interactive Visual Dashboard
    output_html_path = os.path.normpath("docs/dashboard_837_claim.html")
    X12Parser.generate_dashboard(
        parsed_json,
        output_path=output_html_path,
        raw_x12=raw_x12,
        title="Dashboard - Sample 837 Claim"
    )
    print(f"\nVisual HTML Dashboard generated at:\n  {output_html_path}")


if __name__ == "__main__":
    main()
