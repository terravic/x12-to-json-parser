"""
C-CDA Extraction Tests for X12 275 Transactions.
Verifies embedded XML / Base64 extraction and structured clinical object parsing.
"""

import base64
import unittest
from x12_parser.engine.base_parser import X12Parser
from x12_parser.clinical_parsers.ccda_parser import CCDAParser
from sample_data import read_sample


class TestCCDAExtraction(unittest.TestCase):

    def test_275_embedded_ccda_extraction(self):
        raw = read_sample("sample_275_ccda_response.x12")
        parsed = X12Parser.parse(raw)
        tx = parsed["functional_groups"][0]["transaction_sets"][0]["parsed_transaction"]

        self.assertEqual(tx["transaction_type"], "275")
        self.assertEqual(tx["raw_payload_info"]["format"], "XML")

        clinical = tx.get("attached_clinical_data", {})
        self.assertIsNotNone(clinical)

        # 1. Document Metadata
        meta = clinical.get("document_metadata", {})
        self.assertIn("Metropolitan Medical Center", meta.get("title", ""))
        self.assertEqual(meta.get("document_id", {}).get("extension"), "CCDA-DOC-20260814-001")
        self.assertEqual(meta.get("author", {}).get("name", {}).get("family_name"), "Smith")
        self.assertEqual(meta.get("author", {}).get("name", {}).get("first_name"), "Robert")

        # 2. Patient Demographics
        demo = clinical.get("patient_demographics", {})
        self.assertEqual(demo.get("patient_identifier"), "MRN-DOE-78901")
        self.assertEqual(demo.get("name", {}).get("family_name"), "Doe")
        self.assertEqual(demo.get("name", {}).get("first_name"), "John")
        self.assertEqual(demo.get("date_of_birth"), "19750412")
        self.assertEqual(demo.get("gender"), "Male")
        self.assertEqual(demo.get("address", {}).get("street_address"), "742 Evergreen Terrace")
        self.assertEqual(demo.get("address", {}).get("city"), "Metropolis")
        self.assertEqual(demo.get("address", {}).get("state"), "NY")

        # 3. Allergies
        allergies = clinical.get("allergies", [])
        self.assertEqual(len(allergies), 1)
        self.assertEqual(allergies[0]["substance"], "Penicillin G")
        self.assertEqual(allergies[0]["reaction"], "Anaphylaxis")
        self.assertEqual(allergies[0]["severity"], "Severe")
        self.assertEqual(allergies[0]["status"], "active")

        # 4. Medications
        meds = clinical.get("medications", [])
        self.assertEqual(len(meds), 1)
        self.assertEqual(meds[0]["medication_name"], "Lisinopril 20 MG Oral Tablet")
        self.assertEqual(meds[0]["rxnorm_code"], "314076")
        self.assertEqual(meds[0]["dose"], "20 mg")
        self.assertEqual(meds[0]["route"], "Oral")
        self.assertEqual(meds[0]["status"], "active")

        # 5. Problems / Diagnoses
        problems = clinical.get("problems_and_diagnoses", [])
        self.assertEqual(len(problems), 2)
        prob_codes = [p["code"] for p in problems]
        self.assertIn("I10", prob_codes)
        self.assertIn("R07.9", prob_codes)

        # 6. Vital Signs
        vitals = clinical.get("vital_signs", [])
        self.assertGreaterEqual(len(vitals), 5)
        vital_dict = {v["measurement_name"]: v["value"] for v in vitals}
        self.assertEqual(vital_dict.get("Systolic Blood Pressure"), "138")
        self.assertEqual(vital_dict.get("Diastolic Blood Pressure"), "86")
        self.assertEqual(vital_dict.get("Heart Rate"), "72")
        self.assertEqual(vital_dict.get("Oxygen Saturation"), "98")
        self.assertEqual(vital_dict.get("Body Mass Index"), "27.4")

        # 7. Clinical Notes & Medical Necessity Evaluation
        notes = clinical.get("clinical_notes_and_evaluations", {})
        self.assertIn("chief_complaint_and_reason_for_visit", notes)
        self.assertIn("assessment_and_plan", notes)
        self.assertIn("progress_note_medical_necessity_evaluation", notes)
        eval_note = notes["progress_note_medical_necessity_evaluation"]
        self.assertIn("John Doe", eval_note)
        self.assertIn("Lisinopril 20mg", eval_note)
        self.assertIn("medical necessity", eval_note.lower())

    def test_275_base64_encoded_payload(self):
        # Read raw 275 sample, extract XML, encode to Base64, and construct 275 with B64
        raw = read_sample("sample_275_ccda_response.x12")
        xml_start = raw.find("<?xml")
        xml_end = raw.find("</ClinicalDocument>") + len("</ClinicalDocument>")
        xml_str = raw[xml_start:xml_end]

        b64_str = base64.b64encode(xml_str.encode("utf-8")).decode("utf-8")
        b64_275 = (
            "ISA*00*          *00*          *ZZ*SUBMITTER123   *ZZ*BLUEHORIZON    *260814*1600*^*00501*000000004*0*P*:~"
            "GS*PI*SUBMITTER123*BLUEHORIZON*20260814*1600*4*X*005010X210~"
            "ST*275*0001*005010X210~"
            "BGN*00*ATT-TRANS-20260814*20260814*1600~"
            "NM1*41*2*METROPOLITAN MEDICAL CENTER*****XX*1234567890~"
            "CAT*TI*09*ATT-REF-99214-CCDA~"
            f"BDS*B64*{len(b64_str)}*{b64_str}~"
            "SE*7*0001~"
            "GE*1*4~"
            "IEA*1*000000004~"
        )

        parsed = X12Parser.parse(b64_275)
        tx = parsed["functional_groups"][0]["transaction_sets"][0]["parsed_transaction"]
        self.assertEqual(tx["transaction_type"], "275")
        self.assertTrue(tx["raw_payload_info"]["is_base64"])

        clinical = tx.get("attached_clinical_data", {})
        demo = clinical.get("patient_demographics", {})
        self.assertEqual(demo.get("name", {}).get("family_name"), "Doe")
        self.assertEqual(demo.get("name", {}).get("first_name"), "John")
        meds = clinical.get("medications", [])
        self.assertEqual(meds[0]["rxnorm_code"], "314076")


if __name__ == "__main__":
    unittest.main()
