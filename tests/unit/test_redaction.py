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
        {"value": "aa:bb:cc:dd:ee:ff"},
        {"value": "C1234567890123"},
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
