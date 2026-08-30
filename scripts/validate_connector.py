#!/usr/bin/env python3
"""Validate the public Phase 0 GoPro connector repository."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from aoa_gopro_connector.adapters import ReplayReadAdapter
from aoa_gopro_connector.cli import build_parser
from aoa_gopro_connector.digest import verify_digest
from aoa_gopro_connector.json_io import strict_json_loads
from aoa_gopro_connector.probe import ProbeContext, build_capability_profile
from aoa_gopro_connector.redaction import public_safety_violations
from aoa_gopro_connector.schema import SCHEMA_NAMES, load_schema, validate_document


REQUIRED_FILES = [
    "AGENTS.md",
    "README.md",
    "CHARTER.md",
    "BOUNDARIES.md",
    "ROADMAP.md",
    "STATUS.md",
    "STORAGE_POLICY.md",
    "CHANGELOG.md",
    "LICENSE",
    "pyproject.toml",
    ".env.example",
    ".gitignore",
    ".github/workflows/validate.yml",
    ".connector-state/AGENTS.md",
    ".connector-state/README.md",
    "connector/SOURCE_POLICY.md",
    "connector/manifests/connector_manifest.yaml",
    "connector/manifests/route_allowlist.yaml",
    "connector/manifests/artifact_classes.yaml",
    "connector/fixtures/hero13/stock-usb-ncm-read-only.json",
    "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json",
    "docs/ARCHITECTURE.md",
    "docs/RUNTIME_CONTRACT.md",
    "decisions/README.md",
    "decisions/AOA-GOPRO-D-0001-physical-camera-contract.md",
    "decisions/AOA-GOPRO-D-0002-optional-opengopro-sdk.md",
    "evals/AGENTS.md",
    "evals/README.md",
    "stats/AGENTS.md",
    "stats/README.md",
    "src/aoa_gopro_connector/__init__.py",
    "src/aoa_gopro_connector/cli.py",
    "src/aoa_gopro_connector/json_io.py",
    "src/aoa_gopro_connector/models.py",
    "src/aoa_gopro_connector/probe.py",
    "src/aoa_gopro_connector/redaction.py",
    "src/aoa_gopro_connector/adapters/base.py",
    "src/aoa_gopro_connector/adapters/replay.py",
    "src/aoa_gopro_connector/adapters/http_read.py",
    "scripts/validate_connector.py",
    "scripts/verify_install_route.py",
]

REQUIRED_DIRS = [
    ".connector-state/data",
    ".connector-state/cache",
    ".connector-state/auth",
    ".connector-state/artifacts",
    ".connector-state/media",
    "connector/schemas",
    "connector/fixtures",
    "connector/profiles",
    "docs",
    "decisions",
    "evals/intake",
    "evals/reports",
    "stats",
    "src/aoa_gopro_connector/adapters",
    "tests/unit",
    "tests/contract",
    "tests/integration",
]

REQUIRED_GITIGNORE = [
    ".connector-state/auth/*",
    ".connector-state/media/*",
    "data/",
    "cache/",
    "auth/",
    "artifacts/",
    "media/",
    "raw/",
    "captures/",
    "packet-dumps/",
    "*.mp4",
    "*.lrv",
    "*.thm",
    "*.gpmf",
]

FORBIDDEN_HEAVY_ROOTS = {
    "data",
    "cache",
    "auth",
    "artifacts",
    "media",
    "raw",
    "captures",
    "packet-dumps",
    "exports",
}

FORBIDDEN_DUPLICATE_DOCS = {
    "docs/STATUS.md",
    "docs/ROADMAP.md",
    "docs/STORAGE_POLICY.md",
    "connector/STORAGE_POLICY.md",
    "docs/SOURCE_POLICY.md",
}

COMMAND_FENCE_LANGUAGES = {
    "bash",
    "sh",
    "shell",
    "console",
    "terminal",
    "powershell",
    "cmd",
}
COMMAND_LINE_RE = re.compile(
    r"^\s*(?:\$\s+|[A-Z][A-Z0-9_]*=|python(?:3)?\s+|pytest(?:\s|$)|"
    r"aoa-gopro(?:\s|$)|pip(?:3)?\s+|git\s+|curl\s+|ffmpeg\s+|export\s+)",
    re.IGNORECASE,
)


def _load_json(path: Path, errors: list[str]) -> object | None:
    try:
        return strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"invalid JSON {path.relative_to(REPO_ROOT)}: {exc}")
        return None


def _check_markdown_command_hygiene(errors: list[str]) -> None:
    for path in sorted(REPO_ROOT.rglob("*.md")):
        if path.name == "AGENTS.md" or ".git" in path.parts:
            continue
        relative = path.relative_to(REPO_ROOT)
        marker = ""
        language = ""
        start = 0
        body: list[str] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.lstrip()
            if not marker:
                if stripped.startswith("```") or stripped.startswith("~~~"):
                    marker = stripped[:3]
                    language = stripped[3:].strip().casefold().split(maxsplit=1)[0]
                    start = line_number
                    body = []
                continue
            if stripped.startswith(marker):
                if language in COMMAND_FENCE_LANGUAGES or any(
                    COMMAND_LINE_RE.match(item) for item in body
                ):
                    errors.append(f"command block outside AGENTS.md: {relative}:{start}")
                marker = ""
                language = ""
                body = []
            else:
                body.append(line)
        if marker:
            errors.append(f"unterminated Markdown fence: {relative}:{start}")


def _check_cli_surface(errors: list[str]) -> None:
    parser = build_parser()
    choices: set[str] = set()
    for action in parser._actions:
        if isinstance(action, __import__("argparse")._SubParsersAction):
            choices.update(action.choices)
    required = {"doctor", "probe", "replay-probe", "schema"}
    if not required.issubset(choices):
        errors.append(f"CLI missing Phase 0 commands: {sorted(required - choices)}")
    forbidden = {"execute", "record", "delete", "firmware", "reset", "effect"}
    if choices & forbidden:
        errors.append(f"Phase 0 CLI exposes effect commands: {sorted(choices & forbidden)}")


def _fixture_context(adapter: ReplayReadAdapter) -> ProbeContext:
    context = adapter.fixture["context"]
    return ProbeContext(
        observed_at=context["observed_at"],
        topology=context["topology"],
        discovery=tuple(context["discovery"]),
        protocol_version=context["protocol_version"],
        firmware_posture=context["firmware_posture"],
        evidence_ref=f"fixture:{adapter.fixture['fixture_id']}",
    )


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    for relative in REQUIRED_FILES:
        if not (REPO_ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")
    for relative in REQUIRED_DIRS:
        if not (REPO_ROOT / relative).is_dir():
            errors.append(f"missing required directory: {relative}")
    for relative in FORBIDDEN_DUPLICATE_DOCS:
        if (REPO_ROOT / relative).exists():
            errors.append(f"duplicate canonical documentation surface: {relative}")
    for name in FORBIDDEN_HEAVY_ROOTS:
        if (REPO_ROOT / name).exists():
            errors.append(f"heavy/private root exists in Git repository: {name}")

    gitignore_path = REPO_ROOT / ".gitignore"
    gitignore = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    for pattern in REQUIRED_GITIGNORE:
        if pattern not in gitignore:
            errors.append(f".gitignore missing private/heavy pattern: {pattern}")

    for name in SCHEMA_NAMES:
        try:
            load_schema(name)
        except Exception as exc:  # validator boundary reports every contract failure
            errors.append(f"schema {name} invalid: {exc}")

    public_json_paths = [
        *sorted((REPO_ROOT / "connector" / "fixtures").rglob("*.json")),
        *sorted((REPO_ROOT / "connector" / "profiles").rglob("*.json")),
    ]
    for path in public_json_paths:
        value = _load_json(path, errors)
        if value is not None:
            for violation in public_safety_violations(value):
                errors.append(f"public artifact unsafe {path.relative_to(REPO_ROOT)}: {violation}")

    profile_path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = _load_json(profile_path, errors) if profile_path.exists() else None
    if isinstance(profile, dict):
        try:
            validate_document("capability_profile", profile)
            verify_digest(profile, "profile_digest")
        except Exception as exc:
            errors.append(f"named capability profile invalid: {exc}")

    fixture_path = REPO_ROOT / "connector/fixtures/hero13/stock-usb-ncm-read-only.json"
    if fixture_path.exists():
        try:
            replay = ReplayReadAdapter.from_path(fixture_path)
            replay_profile = build_capability_profile(replay, _fixture_context(replay))
            validate_document("capability_profile", replay_profile)
        except Exception as exc:
            errors.append(f"replay contract failed: {exc}")

    allowlist_path = REPO_ROOT / "connector/manifests/route_allowlist.yaml"
    allowlist = allowlist_path.read_text(encoding="utf-8") if allowlist_path.exists() else ""
    for route in ("/gopro/camera/info", "/gopro/camera/state", "/gopro/media/list"):
        if route not in allowlist:
            errors.append(f"read allowlist missing route: {route}")
    if "effect_routes: []" not in allowlist or re.search(
        r"^\s*method:\s*(?!GET\s*$)\S+", allowlist, re.MULTILINE
    ):
        errors.append("Phase 0 route allowlist contains an effect or non-GET method")

    _check_cli_surface(errors)
    _check_markdown_command_hygiene(errors)

    payload = {
        "schema_version": "aoa_gopro_connector_validation_v1",
        "status": "ok" if not errors else "error",
        "repo_root": str(REPO_ROOT),
        "errors": errors,
        "warnings": warnings,
        "checked": {
            "required_files": len(REQUIRED_FILES),
            "required_dirs": len(REQUIRED_DIRS),
            "schemas": len(SCHEMA_NAMES),
            "public_json_artifacts": len(public_json_paths),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
