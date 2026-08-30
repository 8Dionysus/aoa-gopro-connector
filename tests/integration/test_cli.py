from __future__ import annotations

import json
from pathlib import Path

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
