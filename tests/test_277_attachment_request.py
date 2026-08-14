"""
Tests for X12 277 Claim Status & Request for Additional Information.
Verifies `required_attachments` flagging and correlation.
"""

import unittest
from x12_parser.engine.base_parser import X12Parser
from sample_data import read_sample


class Test277AttachmentRequest(unittest.TestCase):

    def test_277_flags_required_attachments(self):
        raw = read_sample("sample_277_request.x12")
        parsed = X12Parser.parse(raw)
        tx = parsed["functional_groups"][0]["transaction_sets"][0]["parsed_transaction"]

        self.assertEqual(tx["transaction_type"], "277")

        # Verify required_attachments array is populated
        req_attachments = tx.get("required_attachments", [])
        self.assertEqual(len(req_attachments), 1)

        att = req_attachments[0]
        self.assertEqual(att["claim_tracking_number"], "CLM-2026-98124")
        self.assertEqual(att["payer_claim_control_number"], "BH-ICN-987654321")
        self.assertEqual(att["patient_name"], "DOE")
        
        # Attachment report type
        self.assertEqual(att["attachment_report_type_code"], "09")
        self.assertEqual(att["attachment_report_type_description"], "Progress Report")
        
        # Transmission code
        self.assertEqual(att["attachment_transmission_code"], "EL")
        self.assertEqual(att["attachment_transmission_description"], "Electronic Only (EDI / C-CDA)")
        self.assertEqual(att["attachment_control_number"], "ATT-REF-99214-CCDA")

        # STC Status codes
        self.assertEqual(att["status_category_code"], "R4")
        self.assertIn("Supporting Documentation", att["status_category_description"])
        self.assertEqual(att["action_code"], "A4")
        self.assertEqual(att["action_description"], "Pended / Additional Information Required")


if __name__ == "__main__":
    unittest.main()
