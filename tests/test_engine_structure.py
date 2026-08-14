"""
Structure Tests for X12 Parser.
Validates ISA/GS/ST/SE/GE/IEA envelopes, custom delimiters, and segment tokenization.
"""

import unittest
from x12_parser.engine.tokenizer import X12Tokenizer, X12Delimiters
from x12_parser.engine.base_parser import X12Parser
from sample_data import read_sample


class TestEngineStructure(unittest.TestCase):

    def test_delimiter_detection_standard(self):
        raw = read_sample("sample_837_claim.x12")
        delims = X12Tokenizer.detect_delimiters(raw)
        self.assertEqual(delims.element_separator, "*")
        self.assertEqual(delims.component_separator, ":")
        self.assertEqual(delims.segment_terminator, "~")
        self.assertEqual(delims.repetition_separator, "^")

    def test_custom_delimiters(self):
        custom_x12 = (
            "ISA|00|          |00|          |ZZ|SENDER         |ZZ|RECEIVER       |260814|1200|!|00501|000000001|0|P|>#"
            "GS|HC|SENDER|RECEIVER|20260814|1200|1|X|005010X222A1#"
            "ST|837|0001|005010X222A1#"
            "BHT|0019|00|REF123|20260814|1200|CH#"
            "SE|4|0001#"
            "GE|1|1#"
            "IEA|1|000000001#"
        )
        delims = X12Tokenizer.detect_delimiters(custom_x12)
        self.assertEqual(delims.element_separator, "|")
        self.assertEqual(delims.component_separator, ">")
        self.assertEqual(delims.segment_terminator, "#")
        self.assertEqual(delims.repetition_separator, "!")

        parsed = X12Parser.parse(custom_x12)
        self.assertEqual(parsed["summary"]["total_transaction_sets_count"], 1)
        tx = parsed["functional_groups"][0]["transaction_sets"][0]
        self.assertEqual(tx["transaction_type"], "837")
        self.assertEqual(tx["transaction_set_control_number"], "0001")

    def test_envelope_hierarchy(self):
        raw = read_sample("sample_837_claim.x12")
        parsed = X12Parser.parse(raw)

        # Interchange Header (ISA)
        isa = parsed.get("interchange_header", {})
        self.assertEqual(isa.get("segment_id"), "ISA")
        self.assertEqual(isa.get("fields", {}).get("interchange_control_number"), "000000001")

        # Functional Group (GS)
        groups = parsed.get("functional_groups", [])
        self.assertEqual(len(groups), 1)
        gs = groups[0].get("functional_group_header", {})
        self.assertEqual(gs.get("segment_id"), "GS")
        self.assertEqual(groups[0].get("functional_identifier_code"), "HC")
        self.assertEqual(groups[0].get("version"), "005010X222A1")

        # Transaction Set (ST)
        txs = groups[0].get("transaction_sets", [])
        self.assertEqual(len(txs), 1)
        st = txs[0].get("transaction_header", {})
        self.assertEqual(st.get("segment_id"), "ST")
        self.assertEqual(txs[0].get("transaction_type"), "837")

        # Interchange Trailer (IEA) & Functional Group Trailer (GE)
        ge = groups[0].get("functional_group_trailer", {})
        self.assertEqual(ge.get("segment_id"), "GE")
        iea = parsed.get("interchange_trailer", {})
        self.assertEqual(iea.get("segment_id"), "IEA")

    def test_summary_counts(self):
        raw = read_sample("sample_835_remittance.x12")
        parsed = X12Parser.parse(raw)
        summary = parsed.get("summary", {})
        self.assertEqual(summary.get("total_functional_groups_count"), 1)
        self.assertEqual(summary.get("total_transaction_sets_count"), 1)
        self.assertGreater(summary.get("total_segments_count"), 15)


if __name__ == "__main__":
    unittest.main()
