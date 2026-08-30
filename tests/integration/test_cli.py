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
    assert payload["error_type"] == "ContractError"
