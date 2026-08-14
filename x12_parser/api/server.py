"""
Production HTTP REST API Server for X12 Healthcare Parser.

Zero-dependency implementation using standard library http.server,
providing full OpenAPI 3.1 compliance and Gemini Enterprise Plugin endpoints.
"""

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Dict, Any

from ..engine.base_parser import X12Parser


class X12APIRequestHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for X12 parsing API and plugin manifests."""

    def _set_headers(self, status_code: int = 200, content_type: str = "application/json") -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self._set_headers(204)

    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path in ("/v1/health", "/health"):
            self._set_headers(200)
            res = {"status": "healthy", "version": "1.0.0", "service": "X12_Healthcare_Parser"}
            self.wfile.write(json.dumps(res, indent=2).encode("utf-8"))

        elif path in ("/openapi.json", "/v1/openapi.json"):
            openapi_path = os.path.join(os.path.dirname(__file__), "openapi.json")
            if os.path.exists(openapi_path):
                with open(openapi_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self._set_headers(200)
                self.wfile.write(content.encode("utf-8"))
            else:
                self._send_error_json(404, "OpenAPI definition not found")

        elif path in ("/.well-known/ai-plugin.json", "/ai-plugin.json"):
            manifest_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manifests", "ai-plugin.json")
            if os.path.exists(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self._set_headers(200)
                self.wfile.write(content.encode("utf-8"))
            else:
                self._send_error_json(404, "AI plugin manifest not found")

        elif path in ("/skill-manifest.json", "/v1/skill-manifest.json"):
            manifest_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "manifests", "skill-manifest.json")
            if os.path.exists(manifest_path):
                with open(manifest_path, "r", encoding="utf-8") as f:
                    content = f.read()
                self._set_headers(200)
                self.wfile.write(content.encode("utf-8"))
            else:
                self._send_error_json(404, "Skill manifest not found")

        else:
            self._send_error_json(404, f"Endpoint not found: {path}")

    def do_POST(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path in ("/v1/parse/x12", "/parse"):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_error_json(400, "Empty request body. Please provide raw X12 EDI text.")
                return

            body_bytes = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")

            raw_x12 = ""
            context = ""

            try:
                if "application/json" in content_type:
                    payload = json.loads(body_bytes.decode("utf-8"))
                    raw_x12 = payload.get("raw_x12", "")
                    context = payload.get("context", "")
                else:
                    raw_x12 = body_bytes.decode("utf-8")
            except Exception as e:
                self._send_error_json(400, f"Malformed request body: {str(e)}")
                return

            if not raw_x12 or not raw_x12.strip():
                self._send_error_json(400, "No raw X12 content provided in 'raw_x12' field or body.")
                return

            try:
                parsed_result = X12Parser.parse(raw_x12)
                if context:
                    parsed_result["request_context"] = context
                self._set_headers(200)
                self.wfile.write(json.dumps(parsed_result, indent=2, default=str).encode("utf-8"))
            except Exception as e:
                self._send_error_json(400, f"X12 parsing error: {str(e)}")
        else:
            self._send_error_json(404, f"Endpoint not found: {path}")

    def _send_error_json(self, code: int, message: str) -> None:
        self._set_headers(code)
        err = {"error": message, "status_code": code}
        self.wfile.write(json.dumps(err, indent=2).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        """Custom clean logging format."""
        sys.stderr.write(f"[X12-API] {self.address_string()} - {format % args}\n")


def run_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the HTTP API server."""
    server_address = (host, port)
    httpd = HTTPServer(server_address, X12APIRequestHandler)
    print(f"==================================================")
    print(f"X12 Healthcare Parser API Server running at http://{host}:{port}")
    print(f"  - Health Check:    http://{host}:{port}/v1/health")
    print(f"  - Parse Endpoint:  POST http://{host}:{port}/v1/parse/x12")
    print(f"  - OpenAPI Spec:    http://{host}:{port}/openapi.json")
    print(f"  - Plugin Manifest: http://{host}:{port}/.well-known/ai-plugin.json")
    print(f"==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port=port)
