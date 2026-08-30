from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_validator(repo_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/validate_connector.py"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )


def test_repository_validator_passes() -> None:
    completed = _run_validator(REPO_ROOT)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "ok"


def test_repository_validator_checks_every_discovered_public_artifact(
    tmp_path: Path,
) -> None:
    repo_copy = tmp_path / "repo"
    shutil.copytree(
        REPO_ROOT,
        repo_copy,
        ignore=shutil.ignore_patterns(
            ".git",
            ".pytest_cache",
            ".ruff_cache",
            "__pycache__",
            "*.egg-info",
        ),
    )

    profile_source = (
        repo_copy
        / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    )
    profile = json.loads(profile_source.read_text(encoding="utf-8"))
    profile["profile_digest"] = "sha256:" + "f" * 64
    (repo_copy / "connector/profiles/additional-invalid.json").write_text(
        json.dumps(profile),
        encoding="utf-8",
    )

    fixture_source = (
        repo_copy
        / "connector/fixtures/hero13/stock-usb-ncm-read-only.json"
    )
    fixture = json.loads(fixture_source.read_text(encoding="utf-8"))
    fixture["responses"]["/gopro/camera/unknown"] = {}
    (repo_copy / "connector/fixtures/additional-invalid.json").write_text(
        json.dumps(fixture),
        encoding="utf-8",
    )

    completed = _run_validator(repo_copy)
    assert completed.returncode == 1, completed.stdout + completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "error"
    assert any(
        "capability profile invalid connector/profiles/additional-invalid.json"
        in error
        for error in payload["errors"]
    )
    assert any(
        "replay fixture invalid connector/fixtures/additional-invalid.json" in error
        for error in payload["errors"]
    )
