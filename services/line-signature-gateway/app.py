#!/usr/bin/env python3
"""Verify LINE webhook signatures before forwarding requests to n8n."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


LOG = logging.getLogger("line-signature-gateway")
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or value.startswith("REPLACE_WITH"):
        raise RuntimeError(f"{name} must be configured")
    return value


def verify_signature(channel_secret: str, body: bytes, supplied: str) -> bool:
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, supplied.strip())


class GatewayHandler(BaseHTTPRequestHandler):
    server_version = "LINEGateway"
    sys_version = ""

    def log_message(self, format_string: str, *args: object) -> None:
        LOG.info("%s %s", self.client_address[0], format_string % args)

    def send_json(self, status: int, payload: dict[str, str]) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - HTTP handler API
        if urlsplit(self.path).path == "/healthz":
            self.send_json(200, {"status": "ok"})
            return
        self.send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - HTTP handler API
        if urlsplit(self.path).path != self.server.webhook_path:
            self.send_json(404, {"error": "not found"})
            return

        signature = self.headers.get("x-line-signature", "")
        if not signature:
            self.send_json(401, {"error": "missing LINE signature"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            self.send_json(400, {"error": "invalid content length"})
            return

        if content_length < 0:
            self.send_json(411, {"error": "content length required"})
            return
        if content_length > self.server.max_body_bytes:
            self.send_json(413, {"error": "request body too large"})
            return

        body = self.rfile.read(content_length)
        if len(body) != content_length:
            self.send_json(400, {"error": "incomplete request body"})
            return

        if not verify_signature(self.server.channel_secret, body, signature):
            LOG.warning("Rejected webhook with an invalid signature")
            self.send_json(401, {"error": "invalid LINE signature"})
            return

        self.forward_to_n8n(body)

    def forward_to_n8n(self, body: bytes) -> None:
        target = f"{self.server.upstream_base_url}{self.path}"
        headers = {
            name: value
            for name, value in self.headers.items()
            if name.lower() not in HOP_BY_HOP_HEADERS
            and name.lower() not in {"host", "content-length"}
        }
        headers["Content-Length"] = str(len(body))

        request = Request(target, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.server.upstream_timeout) as response:
                response_body = response.read()
                self.send_response(response.status)
                for name, value in response.headers.items():
                    if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "content-length":
                        self.send_header(name, value)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)
        except HTTPError as error:
            response_body = error.read()
            self.send_response(error.code)
            for name, value in error.headers.items():
                if name.lower() not in HOP_BY_HOP_HEADERS and name.lower() != "content-length":
                    self.send_header(name, value)
            self.send_header("Content-Length", str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)
        except (TimeoutError, URLError):
            LOG.exception("n8n upstream request failed")
            self.send_json(502, {"error": "n8n upstream unavailable"})


class GatewayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], handler: type[GatewayHandler]) -> None:
        super().__init__(address, handler)
        self.channel_secret = required_env("LINE_CHANNEL_SECRET")
        self.webhook_path = required_env("LINE_WEBHOOK_PATH")
        if not self.webhook_path.startswith("/") or "?" in self.webhook_path:
            raise RuntimeError("LINE_WEBHOOK_PATH must be a path beginning with / and without a query")
        self.upstream_base_url = os.environ.get("UPSTREAM_BASE_URL", "http://n8n:5678").rstrip("/")
        self.max_body_bytes = int(os.environ.get("MAX_BODY_BYTES", "1048576"))
        self.upstream_timeout = float(os.environ.get("UPSTREAM_TIMEOUT_SECONDS", "30"))


def main() -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        server = GatewayServer(("0.0.0.0", 8080), GatewayHandler)
    except (RuntimeError, ValueError) as error:
        LOG.error("Configuration error: %s", error)
        return 1

    LOG.info("LINE signature gateway listening on port 8080 for %s", server.webhook_path)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
