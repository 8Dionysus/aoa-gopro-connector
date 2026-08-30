from __future__ import annotations

import json
import socket
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import pytest

from aoa_gopro_connector.adapters import HTTPReadAdapter
from aoa_gopro_connector.adapters.http_read import _validate_base_url
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


@pytest.mark.parametrize("base_url", ["http://0.0.0.0", "http://[::]"])
def test_unspecified_address_is_rejected(base_url: str) -> None:
    with pytest.raises(ContractError, match="private"):
        HTTPReadAdapter(base_url)


@pytest.mark.parametrize(
    "base_url",
    ["http://127.0.0.1:abc", "http://127.0.0.1:70000"],
)
def test_invalid_port_is_a_contract_error(base_url: str) -> None:
    with pytest.raises(ContractError, match="invalid port"):
        HTTPReadAdapter(base_url)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://foo bar.local",
        "http://-camera.local",
        "http://camera..local",
    ],
)
def test_malformed_mdns_hostname_is_a_contract_error(base_url: str) -> None:
    with pytest.raises(ContractError, match="valid local mDNS"):
        HTTPReadAdapter(base_url)


def test_mdns_address_is_pinned_while_host_header_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolution_count = 0

    def changing_resolution(*args: object, **kwargs: object) -> object:
        nonlocal resolution_count
        resolution_count += 1
        address = "192.168.1.2" if resolution_count == 1 else "8.8.8.8"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 8080))]

    class RecordingOpener:
        request: urllib.request.Request | None = None

        def open(
            self,
            request: urllib.request.Request,
            *,
            timeout: float,
        ) -> BytesIO:
            self.request = request
            return BytesIO(b'{"status": "ok"}')

    monkeypatch.setattr(socket, "getaddrinfo", changing_resolution)
    adapter = HTTPReadAdapter("http://camera-name.local:8080")
    opener = RecordingOpener()
    adapter._opener = opener

    assert adapter.get_json("/gopro/camera/info") == {"status": "ok"}
    assert resolution_count == 1
    assert opener.request is not None
    assert opener.request.full_url == "http://192.168.1.2:8080/gopro/camera/info"
    assert opener.request.get_header("Host") == "camera-name.local:8080"


def test_mdns_hostname_resolving_public_address_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 80))
        ],
    )
    with pytest.raises(ContractError, match="outside local"):
        HTTPReadAdapter("http://camera.local")


def test_unresolved_mdns_hostname_is_a_contract_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_resolution(*args: object, **kwargs: object) -> object:
        raise socket.gaierror("not found")

    monkeypatch.setattr(socket, "getaddrinfo", fail_resolution)
    with pytest.raises(ContractError, match="could not be resolved"):
        HTTPReadAdapter("http://camera.local")


@pytest.mark.parametrize(
    "timeout_seconds",
    [float("nan"), float("inf"), float("-inf")],
)
def test_non_finite_timeout_is_a_contract_error(timeout_seconds: float) -> None:
    with pytest.raises(ContractError, match="finite"):
        HTTPReadAdapter("http://127.0.0.1", timeout_seconds=timeout_seconds)


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://[::1]", "http://[::1]"),
        ("http://[fe80::1]:8080", "http://[fe80::1]:8080"),
    ],
)
def test_ipv6_base_url_preserves_brackets(base_url: str, expected: str) -> None:
    assert _validate_base_url(base_url).endpoint == expected


def test_http_adapter_disables_ambient_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:8080")
    adapter = HTTPReadAdapter("http://127.0.0.1")
    proxy_handlers = [
        handler
        for handler in adapter._opener.handlers
        if isinstance(handler, urllib.request.ProxyHandler)
    ]
    assert not any(handler.proxies for handler in proxy_handlers)


def test_redirect_handler_fails_closed(redirect_server: str) -> None:
    adapter = HTTPReadAdapter(redirect_server)
    with pytest.raises(TransportError):
        adapter.get_json("/gopro/camera/info")
