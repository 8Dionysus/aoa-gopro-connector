from __future__ import annotations

import pytest

from aoa_gopro_connector.errors import PublicSafetyError
from aoa_gopro_connector.redaction import assert_public_safe


def test_firmware_version_is_not_misclassified_as_ip() -> None:
    assert_public_safe({"firmware_version": "H24.01.02.10.00"})


@pytest.mark.parametrize(
    "value",
    [
        {"serial_number": "redacted"},
        {"value": "192.168.1.50"},
        {"value": "fe80::1234"},
        {"value": "http://[::1]"},
        {"value": "http://kitchen-camera.local:8080"},
        {"value": "kitchen-camera.home.arpa"},
        {"value": "camera.lan"},
        {"value": "camera.localdomain"},
        {"camera.home.arpa": "synthetic"},
        {"value": "aa:bb:cc:dd:ee:ff"},
        {"value": "AA-BB-CC-DD-EE-FF"},
        {"value": "aabb.ccdd.eeff"},
        {"value": "AABBCCDDEEFF"},
        {"value": "C1234567890123"},
        {"device_id": "unit-kitchen-hero-13"},
        {"device-id": "unit-kitchen-hero-13"},
        {"deviceId": "unit-kitchen-hero-13"},
        {"cameraIdentifier": "unit-kitchen-hero-13"},
        {"apiKey": "synthetic-secret"},
        {"authorization-header": "synthetic-secret"},
        {"wifiPassword": "synthetic-secret"},
        {"wifiSsid": "synthetic-network"},
        {"authToken": "synthetic-secret"},
        {"passphrase": "correct horse battery staple"},
        {"wifiName": "Kitchen"},
    ],
)
def test_public_safety_rejects_identity(value: object) -> None:
    with pytest.raises(PublicSafetyError):
        assert_public_safe(value)


def test_public_safety_rejects_camera_media_filename_by_wire_path() -> None:
    with pytest.raises(PublicSafetyError, match="camera media filename"):
        assert_public_safe({"media": [{"fs": [{"n": "GOPR0123.MP4"}]}]})


def test_public_safety_allows_only_fixed_synthetic_media_filename() -> None:
    assert_public_safe({"media": [{"fs": [{"n": "synthetic-video.mp4"}]}]})
    with pytest.raises(PublicSafetyError, match="camera media filename"):
        assert_public_safe({"media": [{"fs": [{"n": "synthetic-kitchen.mp4"}]}]})


def test_unrelated_short_n_key_is_not_globally_sensitive() -> None:
    assert_public_safe({"n": "synthetic-non-media-value"})


@pytest.mark.parametrize(
    "hostname",
    [
        "owned-camera.example.com",
        "owned-camera.xn--p1ai",
        "камера.рф",
        "камера。рф",
    ],
)
def test_profile_limitation_rejects_public_hostname(hostname: str) -> None:
    with pytest.raises(PublicSafetyError, match="public hostname"):
        assert_public_safe({"limitations": [f"Observed at {hostname} during probe."]})


def test_profile_limitation_allows_dotted_numeric_version() -> None:
    assert_public_safe({"limitations": ["Stock firmware 2.10.00 was observed."]})


@pytest.mark.parametrize(
    "limitation",
    [
        "Wi-Fi password: correct horse battery staple",
        "Observed SSID: owned-camera-network",
        "API token = synthetic-secret-value",
        "Camera serial number was C1234567890123",
        "WPA PSK: correct horse battery staple",
        "Admin PIN: 123456",
        "Wi-Fi passphrase: correct horse battery staple",
        "BLE pairing code: 123456",
        "Pre-shared key: correct horse battery staple",
        "Recovery code: 1234-5678",
        "Session cookie: synthetic-cookie-value",
        "Provisioning seed: synthetic-seed-value",
    ],
)
def test_profile_limitation_rejects_sensitive_prose(limitation: str) -> None:
    with pytest.raises(PublicSafetyError, match="sensitive"):
        assert_public_safe({"limitations": [limitation]})


def test_public_safety_rejects_excessive_nesting_without_recursion() -> None:
    root: dict[str, object] = {}
    cursor = root
    for _ in range(80):
        child: dict[str, object] = {}
        cursor["child"] = child
        cursor = child

    with pytest.raises(PublicSafetyError, match="nesting limit"):
        assert_public_safe(root)
