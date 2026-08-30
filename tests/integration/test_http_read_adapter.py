from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from aoa_gopro_connector.adapters import HTTPReadAdapter
from aoa_gopro_connector.errors import ContractError, TransportError


RESPONSES = {
    "/gopro/camera/info": {
        "model_name": "HERO13 Black",
        "model_number": "65",
        "firmware_version": "H24.01.02.10.00",
    },
    "/gopro/camera/state": {"status": {}, "settings": {}},
    "/gopro/media/list": {"id": "fixture", "media": []},
}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        payload = RESPONSES.get(self.path)
        if payload is None:
            self.send_response(404)
            self.end_headers()
            return
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


class _RedirectHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(302)
        self.send_header("Location", "/gopro/camera/state")
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def local_server() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


@pytest.fixture
def redirect_server() -> str:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RedirectHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_allowlisted_local_read(local_server: str) -> None:
    adapter = HTTPReadAdapter(local_server)
    assert adapter.get_json("/gopro/camera/info")["model_name"] == "HERO13 Black"


def test_non_allowlisted_route_is_rejected(local_server: str) -> None:
    adapter = HTTPReadAdapter(local_server)
    with pytest.raises(ContractError, match="not read-allowlisted"):
        adapter.get_json("/gopro/camera/shutter/start")


def test_public_address_is_rejected() -> None:
    with pytest.raises(ContractError, match="private"):
        HTTPReadAdapter("http://8.8.8.8")


def test_redirect_handler_fails_closed(redirect_server: str) -> None:
    adapter = HTTPReadAdapter(redirect_server)
    with pytest.raises(TransportError):
        adapter.get_json("/gopro/camera/info")
