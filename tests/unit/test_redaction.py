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


def test_unrelated_short_n_key_is_not_globally_sensitive() -> None:
    assert_public_safe({"n": "synthetic-non-media-value"})


def test_public_safety_rejects_excessive_nesting_without_recursion() -> None:
    root: dict[str, object] = {}
    cursor = root
    for _ in range(80):
        child: dict[str, object] = {}
        cursor["child"] = child
        cursor = child

    with pytest.raises(PublicSafetyError, match="nesting limit"):
        assert_public_safe(root)
