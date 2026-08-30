#!/usr/bin/env python3
"""Build and exercise an installed wheel outside the source checkout."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
IGNORE_NAMES = {
    ".git",
    ".connector-state",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in IGNORE_NAMES or name.endswith(".egg-info")
    }


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aoa-gopro-install-") as temp_value:
        temp_root = Path(temp_value)
        source_root = temp_root / "source"
        dist_root = temp_root / "dist"
        venv_root = temp_root / "venv"
        shutil.copytree(REPO_ROOT, source_root, ignore=_ignore)

        _run(
            [
                sys.executable,
                "-m",
                "build",
                "--no-isolation",
                "--outdir",
                str(dist_root),
            ],
            cwd=source_root,
        )
        wheels = sorted(dist_root.glob("aoa_gopro_connector-*.whl"))
        sdists = sorted(dist_root.glob("aoa_gopro_connector-*.tar.gz"))
        if len(wheels) != 1:
            raise RuntimeError(f"expected one wheel, found {len(wheels)}")
        if len(sdists) != 1:
            raise RuntimeError(f"expected one sdist, found {len(sdists)}")

        _run(
            [sys.executable, "-m", "venv", "--system-site-packages", str(venv_root)],
            cwd=temp_root,
        )
        python = venv_root / "bin" / "python"
        _run(
            [str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])],
            cwd=temp_root,
        )

        doctor = json.loads(
            _run([str(venv_root / "bin" / "aoa-gopro"), "doctor"], cwd=temp_root).stdout
        )
        fixture = source_root / "connector/fixtures/hero13/stock-usb-ncm-read-only.json"
        replay = json.loads(
            _run(
                [str(venv_root / "bin" / "aoa-gopro"), "replay-probe", str(fixture)],
                cwd=temp_root,
            ).stdout
        )
        expected_schema_root = venv_root / "share/aoa-gopro-connector/schemas"
        if Path(doctor["schema_root"]) != expected_schema_root:
            raise RuntimeError("installed doctor did not use wheel-owned schemas")
        if doctor["status"] != "ok" or replay["posture"] != "sanitized_replay":
            raise RuntimeError("installed doctor or replay contract failed")

        print(
            json.dumps(
                {
                    "schema_version": "aoa_gopro_install_route_verification_v1",
                    "status": "ok",
                    "wheel": wheels[0].name,
                    "sdist": sdists[0].name,
                    "installed_schema_count": len(doctor["schemas"]),
                    "replay_profile_id": replay["profile_id"],
                    "source_checkout_used_at_runtime": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
