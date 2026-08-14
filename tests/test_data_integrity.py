"""
Data Integrity Tests for 837, 835, 270, 271, and 278 Transactions.
Verifies exact semantic field mappings, financial amounts, and code resolutions.
"""

import unittest
from x12_parser.engine.base_parser import X12Parser
from sample_data import read_sample


class TestDataIntegrity(unittest.TestCase):

    def test_837_claim_data_integrity(self):
        raw = read_sample("sample_837_claim.x12")
        parsed = X12Parser.parse(raw)
        tx = parsed["functional_groups"][0]["transaction_sets"][0]["parsed_transaction"]

        # Submitter & Receiver
        self.assertEqual(tx["submitter"]["name_last_or_organization"], "ACME BILLING SERVICES")
        self.assertEqual(tx["receiver"]["name_last_or_organization"], "BLUE HORIZON HEALTH PLAN")

        # Billing Provider
        self.assertEqual(tx["billing_provider"]["name_last_or_organization"], "METROPOLITAN MEDICAL CENTER")
        self.assertEqual(tx["billing_provider"]["identification_code"], "1234567890")
        self.assertEqual(tx["billing_provider"]["address"]["address_line_1"], "100 HEALTHCARE BLVD")
        self.assertEqual(tx["billing_provider"]["geographic_location"]["city"], "METROPOLIS")
        self.assertEqual(tx["billing_provider"]["geographic_location"]["state"], "NY")

        # Subscriber
        self.assertEqual(tx["subscriber"]["name_last_or_organization"], "DOE")
        self.assertEqual(tx["subscriber"]["name_first"], "JOHN")
        self.assertEqual(tx["subscriber"]["identification_code"], "W1234567890")
        self.assertEqual(tx["subscriber"]["demographics"]["date_of_birth"], "19750412")
        self.assertEqual(tx["subscriber"]["demographics"]["gender"], "M")

        # Claim Details
        claims = tx["claims"]
        self.assertEqual(len(claims), 1)
        c = claims[0]
        self.assertEqual(c["claim_id"], "CLM-2026-98124")
        self.assertEqual(c["total_claim_charge_amount"], 1500.00)
        self.assertEqual(c["dates"]["service_date"], "20260810")

        # Diagnoses
        self.assertEqual(len(c["diagnoses"]), 2)
        self.assertEqual(c["diagnoses"][0]["code"], "I10")
        self.assertEqual(c["diagnoses"][1]["code"], "R07.9")

        # Service Lines
        lines = c["service_lines"]
        self.assertEqual(len(lines), 2)
        # Line 1: 99214 with modifier 25
        self.assertEqual(lines[0]["procedure"]["code"], "99214")
        self.assertEqual(lines[0]["procedure"]["modifiers"], ["25"])
        self.assertEqual(lines[0]["charge_amount"], 250.00)
        # Line 2: 93000
        self.assertEqual(lines[1]["procedure"]["code"], "93000")
        self.assertEqual(lines[1]["charge_amount"], 1250.00)

    def test_835_remittance_integrity(self):
        raw = read_sample("sample_835_remittance.x12")
        parsed = X12Parser.parse(raw)
        tx = parsed["functional_groups"][0]["transaction_sets"][0]["parsed_transaction"]

        # Financial info
        fin = tx["financial_information"]
        self.assertEqual(fin["total_payment_amount"], 950.00)
        self.assertEqual(fin["payment_method"], "ACH")
        self.assertEqual(fin["payment_effective_date"], "20260814")

        # Reassociation Trace
        self.assertEqual(tx["reassociation_trace"]["check_or_eft_trace_number"], "CHK78912345")

        # Claim payment CLP
        claims = tx["claims"]
        self.assertEqual(len(claims), 1)
        c = claims[0]
        self.assertEqual(c["patient_control_number"], "CLM-2026-98124")
        self.assertEqual(c["total_claim_charge_amount"], 1500.00)
        self.assertEqual(c["claim_payment_amount"], 950.00)
        self.assertEqual(c["patient_responsibility_amount"], 100.00)
        self.assertEqual(c["claim_status_code"], "1")
        self.assertEqual(c["claim_status_description"], "Processed as Primary")

        # Claim Adjustments (CO:45, CO:96, PR:1, PR:2)
        adjs = c["adjustments"]
        self.assertGreater(len(adjs), 0)
        adj_map = {(a["group_code"], a["reason_code"]): a["adjustment_amount"] for a in adjs}
        self.assertEqual(adj_map.get(("CO", "45")), 350.00)
        self.assertEqual(adj_map.get(("CO", "96")), 100.00)
        self.assertEqual(adj_map.get(("PR", "1")), 50.00)
        self.assertEqual(adj_map.get(("PR", "2")), 50.00)

        # Service Lines
        lines = c["service_lines"]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["procedure"]["code"], "99214")
        self.assertEqual(lines[0]["line_charge_amount"], 250.00)
        self.assertEqual(lines[0]["line_payment_amount"], 200.00)

        self.assertEqual(lines[1]["procedure"]["code"], "93000")
        self.assertEqual(lines[1]["line_charge_amount"], 1250.00)
        self.assertEqual(lines[1]["line_payment_amount"], 750.00)

    def test_271_eligibility_integrity(self):
        raw = read_sample("sample_271_response.x12")
        parsed = X12Parser.parse(raw)
        tx = parsed["functional_groups"][0]["transaction_sets"][0]["parsed_transaction"]

        self.assertEqual(tx["transaction_type"], "271")
        self.assertEqual(tx["subscriber"]["name_last_or_organization"], "DOE")
        self.assertEqual(tx["subscriber"]["name_first"], "JOHN")

        benefits = tx["eligibility_benefits"]
        self.assertGreater(len(benefits), 0)
        
        # Verify copay (EB*B) and deductible (EB*C)
        copay_found = False
        deductible_found = False
        for b in benefits:
            if b["eligibility_code"] == "B" and b["service_type_code"] == "98":
                self.assertEqual(b["monetary_amount"], 25.00)
                copay_found = True
            elif b["eligibility_code"] == "C" and b["service_type_code"] == "30":
                self.assertEqual(b["monetary_amount"], 500.00)
                deductible_found = True

        self.assertTrue(copay_found)
        self.assertTrue(deductible_found)

    def test_278_prior_auth_integrity(self):
        raw = read_sample("sample_278_prior_auth.x12")
        parsed = X12Parser.parse(raw)
        tx = parsed["functional_groups"][0]["transaction_sets"][0]["parsed_transaction"]

        self.assertEqual(tx["transaction_type"], "278")
        events = tx["events"]
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["review_results"][0]["approval_status"], "Approved")
        self.assertEqual(event["review_results"][0]["review_identification_number"], "AUTH-PA-2026-9901")


if __name__ == "__main__":
    unittest.main()
