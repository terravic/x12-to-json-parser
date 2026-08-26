"""
Tests for OpenAPI specification, Gemini Enterprise Skill/Plugin manifests, and API Server.
"""

import os
import json
import time
import socket
import threading
import unittest
import urllib.request
import urllib.error
from http.server import HTTPServer

from x12_parser.api.server import X12APIRequestHandler
from sample_data import read_sample


def get_free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestAPIAndManifests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.port = get_free_port()
        cls.server = HTTPServer(("127.0.0.1", cls.port), X12APIRequestHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_openapi_json_schema(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        openapi_file = os.path.join(project_root, "x12_parser", "api", "openapi.json")
        self.assertTrue(os.path.exists(openapi_file))

        with open(openapi_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("openapi", data)
        self.assertIn("/v1/parse/x12", data["paths"])
        post_op = data["paths"]["/v1/parse/x12"]["post"]
        self.assertEqual(post_op["operationId"], "parseX12Transaction")
        self.assertIn("requestBody", post_op)
        self.assertIn("200", post_op["responses"])

    def test_ai_plugin_manifest(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        manifest_file = os.path.join(project_root, "x12_parser", "manifests", "ai-plugin.json")
        self.assertTrue(os.path.exists(manifest_file))

        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        self.assertEqual(manifest.get("schema_version"), "1.0")
        self.assertEqual(manifest.get("name_for_model"), "X12_Healthcare_Parser")
        self.assertIn("raw EDI X12 healthcare transaction text", manifest.get("description_for_model", ""))
        self.assertIn("C-CDA XML", manifest.get("description_for_model", ""))

    def test_skill_manifest(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        skill_file = os.path.join(project_root, "x12_parser", "manifests", "skill-manifest.json")
        self.assertTrue(os.path.exists(skill_file))

        with open(skill_file, "r", encoding="utf-8") as f:
            skill = json.load(f)

        self.assertEqual(skill.get("schema_version"), "1.0")
        self.assertEqual(skill.get("name_for_model"), "X12_Healthcare_Parser")
        self.assertTrue(skill.get("ui_canvas", {}).get("supported"))
        endpoints = skill.get("endpoints", [])
        self.assertGreaterEqual(len(endpoints), 1)
        self.assertEqual(endpoints[0]["path"], "/v1/parse/x12")
        self.assertEqual(endpoints[0]["method"], "POST")

    def test_server_dashboard_endpoint(self):
        url = f"{self.base_url}/dashboard"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            html_content = resp.read().decode("utf-8")
            self.assertIn("EDI X12", html_content)
            self.assertIn("Semantic Mapping Engine", html_content)

    def test_server_health_endpoint(self):
        url = f"{self.base_url}/v1/health"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "healthy")

    def test_server_parse_837_post(self):
        url = f"{self.base_url}/v1/parse/x12"
        raw_837 = read_sample("sample_837_claim.x12")
        payload = json.dumps({
            "raw_x12": raw_837,
            "context": "Automated Unit Test Submission"
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("request_context"), "Automated Unit Test Submission")
            groups = data.get("functional_groups", [])
            self.assertEqual(len(groups), 1)
            tx = groups[0]["transaction_sets"][0]["parsed_transaction"]
            self.assertEqual(tx["claims"][0]["claim_id"], "CLM-2026-98124")

    def test_server_parse_275_ccda_post(self):
        url = f"{self.base_url}/v1/parse/x12"
        raw_275 = read_sample("sample_275_ccda_response.x12")
        payload = json.dumps({"raw_x12": raw_275}).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            tx = data["functional_groups"][0]["transaction_sets"][0]["parsed_transaction"]
            self.assertEqual(tx["transaction_type"], "275")
            clin = tx.get("attached_clinical_data", {})
            self.assertEqual(clin.get("patient_demographics", {}).get("name", {}).get("family_name"), "Doe")

    def test_generate_dashboard_any_x12_file(self):
        from x12_parser import X12Parser
        for sample_name in [
            "sample_837_claim.x12",
            "sample_835_remittance.x12",
            "sample_277_request.x12",
            "sample_275_ccda_response.x12",
            "sample_271_response.x12",
            "sample_278_prior_auth.x12"
        ]:
            raw = read_sample(sample_name)
            html = X12Parser.generate_dashboard(raw, title=f"Test {sample_name}")
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("tailwindcss.min.js", html)
            self.assertIn("CURRENT_DATA", html)

    def test_server_parse_and_build_html_dashboard(self):
        url = f"{self.base_url}/v1/parse/x12"
        raw_835 = read_sample("sample_835_remittance.x12")
        payload = json.dumps({"raw_x12": raw_835, "format": "html"}).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("text/html", resp.headers.get("Content-Type", ""))
            html_out = resp.read().decode("utf-8")
            self.assertIn("835", html_out)
            self.assertIn("Payment Total", html_out)


if __name__ == "__main__":
    unittest.main()
