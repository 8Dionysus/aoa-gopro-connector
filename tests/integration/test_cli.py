from __future__ import annotations

import json
from pathlib import Path

import pytest

from aoa_gopro_connector.cli import main


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_doctor_is_offline_and_has_no_effect_surface(capsys) -> None:
    assert main(["doctor"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["effects_available"] is False
    assert payload["live_routes"] == "read_only_allowlist"
    assert payload["open_gopro_sdk"]["published_version"] == "0.22.0"
    assert payload["open_gopro_sdk"]["declared_python"] == ">=3.11,<3.14"
    assert isinstance(payload["open_gopro_sdk"]["current_python_compatible"], bool)


def test_doctor_invalid_schema_definition_emits_structured_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys,
) -> None:
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()
    (schema_root / "camera_state.schema.json").write_text(
        '{"type": 42}',
        encoding="utf-8",
    )
    monkeypatch.setenv("AOA_GOPRO_SCHEMA_ROOT", str(schema_root))

    assert main(["doctor"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "ContractError"
    assert "invalid schema definition" in payload["message"]


def test_replay_cli_emits_profile(capsys) -> None:
    fixture = REPO_ROOT / "connector/fixtures/hero13/stock-usb-ncm-read-only.json"
    assert main(["replay-probe", str(fixture)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "aoa_gopro_capability_profile_v1"
    assert payload["posture"] == "sanitized_replay"


def test_probe_cli_invalid_port_emits_structured_error(capsys) -> None:
    assert main(["probe", "--base-url", "http://127.0.0.1:abc"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "ContractError"


def test_probe_cli_malformed_ipv6_emits_structured_error(capsys) -> None:
    assert main(["probe", "--base-url", "http://[::1"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "ContractError"


def test_probe_cli_non_finite_timeout_emits_structured_error(capsys) -> None:
    assert (
        main(
            [
                "probe",
                "--base-url",
                "http://127.0.0.1",
                "--timeout",
                "nan",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "ContractError"


def test_probe_cli_invalid_mdns_hostname_emits_structured_error(capsys) -> None:
    assert main(["probe", "--base-url", "http://foo bar.local"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "ContractError"


def test_probe_cli_rejects_identifying_discovery_value(capsys) -> None:
    assert (
        main(
            [
                "probe",
                "--base-url",
                "http://127.0.0.1",
                "--discovery",
                "kitchen-camera.home.arpa",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "ContractError"


def test_probe_cli_has_no_free_form_evidence_id(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        main(
            [
                "probe",
                "--base-url",
                "http://127.0.0.1",
                "--evidence-id",
                "kitchen-hero13",
            ]
        )
    assert raised.value.code == 2
    assert "unrecognized arguments: --evidence-id" in capsys.readouterr().err


def test_probe_cli_rejects_identifying_protocol_version(capsys) -> None:
    assert (
        main(
            [
                "probe",
                "--base-url",
                "http://127.0.0.1",
                "--protocol-version",
                "kitchen-hero13",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "ContractError"


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_schema_cli_rejects_nonstandard_numeric_constants(
    constant: str,
    tmp_path: Path,
    capsys,
) -> None:
    document = {
        "schema_version": "aoa_gopro_event_v1",
        "event_id": "event:fixture-discovered",
        "event_type": "camera.discovered",
        "device_ref": "device:fixture-camera",
        "causal_operation_id": None,
        "wall_time": "2026-08-30T05:00:00Z",
        "monotonic_ns": 1,
        "observed_source": "fixture",
        "capability_profile_digest": "sha256:" + "1" * 64,
        "confidence": None,
        "freshness": {
            "observed_at": "2026-08-30T05:00:00Z",
            "expires_at": None,
            "posture": "current",
        },
        "payload": {},
        "evidence_refs": ["fixture:event"],
        "event_digest": "sha256:" + "0" * 64,
    }
    encoded = json.dumps(document).replace(
        '"confidence": null',
        f'"confidence": {constant}',
    )
    packet_path = tmp_path / "event.json"
    packet_path.write_text(encoded, encoding="utf-8")

    assert main(["schema", "validate", "event", str(packet_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "JSONDecodeError"


def test_schema_cli_rejects_oversized_integer(
    tmp_path: Path,
    capsys,
) -> None:
    packet_path = tmp_path / "oversized-integer.json"
    packet_path.write_text(
        '{"value": ' + "9" * 5000 + "}",
        encoding="utf-8",
    )

    assert main(["schema", "validate", "event", str(packet_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "JSONDecodeError"


@pytest.mark.parametrize("discovery", ["mdns", None])
def test_replay_cli_rejects_non_list_discovery(
    discovery: object,
    tmp_path: Path,
    capsys,
) -> None:
    fixture_path = REPO_ROOT / "connector/fixtures/hero13/stock-usb-ncm-read-only.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["context"]["discovery"] = discovery
    invalid_path = tmp_path / "invalid-replay.json"
    invalid_path.write_text(json.dumps(fixture), encoding="utf-8")

    assert main(["replay-probe", str(invalid_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "ContractError"


def test_replay_cli_rejects_identifying_discovery_value(
    tmp_path: Path,
    capsys,
) -> None:
    fixture_path = REPO_ROOT / "connector/fixtures/hero13/stock-usb-ncm-read-only.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    fixture["context"]["discovery"] = ["kitchen-camera.home.arpa"]
    invalid_path = tmp_path / "invalid-replay.json"
    invalid_path.write_text(json.dumps(fixture), encoding="utf-8")

    assert main(["replay-probe", str(invalid_path)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "PublicSafetyError"


def test_schema_cli_rejects_unreviewed_capability_limitation(
    tmp_path: Path,
    capsys,
) -> None:
    source = (
        REPO_ROOT
        / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    )
    profile = json.loads(source.read_text(encoding="utf-8"))
    profile["limitations"].append("Observed at http://192.168.1.2/private-evidence")
    document = tmp_path / "unsafe-profile.json"
    document.write_text(json.dumps(profile), encoding="utf-8")

    assert main(["schema", "validate", "capability_profile", str(document)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "ContractError"


def test_schema_cli_rejects_free_form_profile_evidence_ref(
    tmp_path: Path,
    capsys,
) -> None:
    source = (
        REPO_ROOT
        / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    )
    profile = json.loads(source.read_text(encoding="utf-8"))
    profile["evidence_refs"][2] = "kitchen-hero13"
    document = tmp_path / "free-form-evidence-profile.json"
    document.write_text(json.dumps(profile), encoding="utf-8")

    assert main(["schema", "validate", "capability_profile", str(document)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_type"] == "ContractError"
