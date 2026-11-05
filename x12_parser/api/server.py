"""
Production HTTP REST API & SSE Streaming Server for X12 Healthcare Parser.

Zero-dependency implementation using standard library http.server,
providing full OpenAPI 3.1 compliance, Server-Sent Events (/v1/events),
and standalone dashboard serving.
"""

import json
import os
import queue
import sys
import threading
import time
from http.server import ThreadingHTTPServer, HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Any, List

from ..engine.base_parser import X12Parser
from ..ui.dashboard_generator import compute_dataset_telemetry, generate_html_dashboard


_SSE_CLIENTS_LOCK = threading.Lock()
_SSE_CLIENTS: List["queue.Queue[str]"] = []


def broadcast_sse_event(event_name: str, payload: Any) -> None:
    """Broadcast a JSON event payload to all connected SSE subscribers."""
    serialized = json.dumps(payload, default=str)
    msg = f"event: {event_name}\ndata: {serialized}\n\n"
    with _SSE_CLIENTS_LOCK:
        stale = []
        for q in _SSE_CLIENTS:
            try:
                q.put_nowait(msg)
            except queue.Full:
                stale.append(q)
        for s in stale:
            if s in _SSE_CLIENTS:
                _SSE_CLIENTS.remove(s)


class X12APIRequestHandler(BaseHTTPRequestHandler):
    """Handles HTTP requests for X12 parsing API, SSE telemetry, and plugin manifests."""

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

        elif path in ("/v1/events", "/events"):
            is_once = "once=1" in parsed_url.query
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close" if is_once else "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            client_queue: "queue.Queue[str]" = queue.Queue(maxsize=32)
            with _SSE_CLIENTS_LOCK:
                _SSE_CLIENTS.append(client_queue)

            try:
                init_msg = json.dumps({"status": "connected", "service": "X12_Healthcare_Parser"})
                self.wfile.write(f"event: status\ndata: {init_msg}\n\n".encode("utf-8"))
                self.wfile.flush()

                # Support non-blocking single-shot check in tests via ?once=1
                if "once=1" in parsed_url.query:
                    return

                while True:
                    try:
                        msg = client_queue.get(timeout=15.0)
                        self.wfile.write(msg.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                self.close_connection = True
                with _SSE_CLIENTS_LOCK:
                    if client_queue in _SSE_CLIENTS:
                        _SSE_CLIENTS.remove(client_queue)

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

        elif path in ("/", "/dashboard", "/dashboard.html", "/ui", "/v1/dashboard"):
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            candidates = [
                os.path.join(project_root, "dashboard.html"),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), "ui", "x12_mapping_dashboard.html"),
            ]
            served = False
            for cpath in candidates:
                if os.path.exists(cpath):
                    with open(cpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    self._set_headers(200, content_type="text/html")
                    self.wfile.write(content.encode("utf-8"))
                    served = True
                    break
            if not served:
                html_content = generate_html_dashboard(title="EDI X12 Semantic Mapping Engine")
                self._set_headers(200, content_type="text/html")
                self.wfile.write(html_content.encode("utf-8"))

        else:
            self._send_error_json(404, f"Endpoint not found: {path}")

    def do_POST(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        query = parsed_url.query

        if path in ("/v1/parse/x12", "/parse", "/dashboard", "/v1/dashboard/generate"):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length == 0:
                self._send_error_json(400, "Empty request body. Please provide raw X12 EDI text.")
                return

            body_bytes = self.rfile.read(content_length)
            content_type = self.headers.get("Content-Type", "")
            accept_header = self.headers.get("Accept", "")

            raw_x12 = ""
            context = ""
            source_path = "api/live_stream.x12"
            requested_format = "json"
            include_telemetry = "include_telemetry=1" in query

            if "format=html" in query or path in ("/dashboard", "/v1/dashboard/generate"):
                requested_format = "html"
            elif "text/html" in accept_header and "application/json" not in accept_header:
                requested_format = "html"

            try:
                if "application/json" in content_type:
                    payload = json.loads(body_bytes.decode("utf-8"))
                    raw_x12 = payload.get("raw_x12", "")
                    context = payload.get("context", "")
                    if payload.get("source_path"):
                        source_path = str(payload.get("source_path"))
                    if payload.get("format") == "html" or payload.get("dashboard") is True:
                        requested_format = "html"
                else:
                    raw_x12 = body_bytes.decode("utf-8")
            except Exception as e:
                self._send_error_json(400, f"Malformed request body: {str(e)}")
                return

            if not raw_x12 or not raw_x12.strip():
                self._send_error_json(400, "No raw X12 content provided in 'raw_x12' field or body.")
                return

            try:
                t0 = time.perf_counter()
                parsed_result = X12Parser.parse(raw_x12)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                if context:
                    parsed_result["request_context"] = context

                # Broadcast live incremental update to any connected SSE dashboard clients
                meta = compute_dataset_telemetry(
                    parsed_result,
                    raw_x12=raw_x12,
                    source_path=source_path,
                    parse_ms=elapsed_ms,
                )
                event_record = {
                    "id": f"sse_{int(time.time() * 1000)}_{meta['sha256'][:8]}",
                    "meta": meta,
                    "parsed_data": parsed_result,
                    "raw_x12": raw_x12,
                }
                broadcast_sse_event("parse_update", event_record)

                if requested_format == "html":
                    html_dashboard = X12Parser.generate_dashboard(
                        parsed_result,
                        raw_x12=raw_x12,
                        title="EDI X12 Semantic Mapping Engine",
                    )
                    self._set_headers(200, content_type="text/html")
                    self.wfile.write(html_dashboard.encode("utf-8"))
                elif include_telemetry:
                    self._set_headers(200, content_type="application/json")
                    self.wfile.write(json.dumps(event_record, indent=2, default=str).encode("utf-8"))
                else:
                    self._set_headers(200, content_type="application/json")
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
    """Start the multi-threaded HTTP & SSE API server."""
    server_address = (host, port)
    server_cls = ThreadingHTTPServer if hasattr(sys.modules[__name__], "ThreadingHTTPServer") else HTTPServer
    httpd = server_cls(server_address, X12APIRequestHandler)
    print("==================================================")
    print(f"X12 Healthcare Parser API & SSE Server at http://{host}:{port}")
    print(f"  - Dashboard UI:    http://{host}:{port}/dashboard")
    print(f"  - SSE Live Stream: http://{host}:{port}/v1/events")
    print(f"  - Health Check:    http://{host}:{port}/v1/health")
    print(f"  - Parse Endpoint:  POST http://{host}:{port}/v1/parse/x12")
    print("==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.server_close()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    run_server(port=port)
