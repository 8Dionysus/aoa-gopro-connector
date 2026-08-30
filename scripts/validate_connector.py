#!/usr/bin/env python3
"""Validate the public Phase 0 GoPro connector repository."""

from __future__ import annotations

import json
import re
import subprocess
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
    "/data/",
    "/cache/",
    "/auth/",
    "/artifacts/",
    "/media/",
    "/raw/",
    "/captures/",
    "/packet-dumps/",
    "*.mp4",
    "*.lrv",
    "*.thm",
    "*.gpmf",
    "*.cer",
    "*.crt",
    "*.der",
    "*.jks",
    "*.key",
    "*.keystore",
    "*.p12",
    "*.p8",
    "*.p7b",
    "*.p7c",
    "*.pem",
    "*.pk8",
    "*.pkcs8",
    "*.pfx",
    "*.ppk",
    ".env",
    ".env.*",
    "!.env.example",
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

FORBIDDEN_PRIVATE_MEDIA_SUFFIXES = {
    ".gpmf",
    ".lrv",
    ".mp4",
    ".thm",
}

FORBIDDEN_CREDENTIAL_SUFFIXES = {
    ".cer",
    ".crt",
    ".der",
    ".jks",
    ".key",
    ".keystore",
    ".p12",
    ".p8",
    ".p7b",
    ".p7c",
    ".pem",
    ".pk8",
    ".pkcs8",
    ".pfx",
    ".ppk",
}

FORBIDDEN_CREDENTIAL_FILENAMES = {
    ".env",
    ".netrc",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "service-account.json",
}

FORBIDDEN_PEM_LABELS = (
    "CERTIFICATE",
    "DSA PRIVATE KEY",
    "EC PRIVATE KEY",
    "ENCRYPTED PRIVATE KEY",
    "OPENSSH PRIVATE KEY",
    "PGP PRIVATE KEY BLOCK",
    "PRIVATE KEY",
    "RSA PRIVATE KEY",
)
FORBIDDEN_PEM_MARKERS = tuple(
    ("-----BEGIN " + label + "-----").encode("ascii")
    for label in FORBIDDEN_PEM_LABELS
)

SNAPSHOT_SCAN_EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
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


def _repository_publication_paths(errors: list[str]) -> tuple[Path, ...]:
    """Return indexed paths in Git, or all files in an exported source snapshot."""

    if (REPO_ROOT / ".git").exists():
        try:
            completed = subprocess.run(
                ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "--cached"],
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            errors.append(f"cannot inspect Git publication index: {exc}")
            return ()
        if completed.returncode != 0:
            detail = completed.stderr.strip() or f"exit {completed.returncode}"
            errors.append(f"cannot inspect Git publication index: {detail}")
            return ()
        return tuple(
            Path(value) for value in completed.stdout.split("\0") if value
        )

    paths: list[Path] = []
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(REPO_ROOT)
        if any(part in SNAPSHOT_SCAN_EXCLUDED_DIRS for part in relative.parts):
            continue
        if any(part.endswith(".egg-info") for part in relative.parts):
            continue
        paths.append(relative)
    return tuple(sorted(paths))


def _contains_forbidden_pem_marker(path: Path) -> bool:
    overlap = max(len(marker) for marker in FORBIDDEN_PEM_MARKERS) - 1
    carry = b""
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            window = carry + chunk
            if any(marker in window for marker in FORBIDDEN_PEM_MARKERS):
                return True
            carry = window[-overlap:]
    return False


def _check_private_repository_files(errors: list[str]) -> int:
    paths = _repository_publication_paths(errors)
    for relative in paths:
        if relative.suffix.casefold() in FORBIDDEN_PRIVATE_MEDIA_SUFFIXES:
            errors.append(
                "forbidden private/heavy media file in repository: "
                f"{relative.as_posix()}"
            )
            continue
        filename = relative.name.casefold()
        if (
            relative.suffix.casefold() in FORBIDDEN_CREDENTIAL_SUFFIXES
            or filename in FORBIDDEN_CREDENTIAL_FILENAMES
            or (filename.startswith(".env.") and filename != ".env.example")
        ):
            errors.append(
                "forbidden credential/certificate file in repository: "
                f"{relative.as_posix()}"
            )
            continue
        candidate = REPO_ROOT / relative
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            contains_marker = _contains_forbidden_pem_marker(candidate)
        except OSError as exc:
            errors.append(
                f"cannot inspect publication file {relative.as_posix()}: {exc}"
            )
            continue
        if contains_marker:
            errors.append(
                "forbidden credential/certificate material in repository: "
                f"{relative.as_posix()}"
            )
    return len(paths)


def _fixture_context(adapter: ReplayReadAdapter) -> ProbeContext:
    context = adapter.fixture["context"]
    return ProbeContext(
        observed_at=context["observed_at"],
        topology=context["topology"],
        discovery=tuple(context["discovery"]),
        protocol_version=context["protocol_version"],
        firmware_posture=context["firmware_posture"],
        evidence_ref=f"fixture:{adapter.fixture_digest}",
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
    publication_path_count = _check_private_repository_files(errors)

    gitignore_path = REPO_ROOT / ".gitignore"
    gitignore = gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    gitignore_lines = {line.strip() for line in gitignore.splitlines()}
    for pattern in REQUIRED_GITIGNORE:
        if pattern not in gitignore_lines:
            errors.append(f".gitignore missing private/heavy pattern: {pattern}")

    for name in SCHEMA_NAMES:
        try:
            load_schema(name)
        except Exception as exc:  # validator boundary reports every contract failure
            errors.append(f"schema {name} invalid: {exc}")

    fixture_paths = sorted((REPO_ROOT / "connector" / "fixtures").rglob("*.json"))
    profile_paths = sorted((REPO_ROOT / "connector" / "profiles").rglob("*.json"))
    public_json_paths = [*fixture_paths, *profile_paths]
    for path in profile_paths:
        value = _load_json(path, errors)
        if value is None:
            continue
        for violation in public_safety_violations(value):
            errors.append(
                f"public artifact unsafe {path.relative_to(REPO_ROOT)}: {violation}"
            )
        if not isinstance(value, dict):
            errors.append(
                f"capability profile is not an object: {path.relative_to(REPO_ROOT)}"
            )
            continue
        try:
            validate_document("capability_profile", value)
            verify_digest(value, "profile_digest")
        except Exception as exc:
            errors.append(
                f"capability profile invalid {path.relative_to(REPO_ROOT)}: {exc}"
            )

    for path in fixture_paths:
        value = _load_json(path, errors)
        if value is None:
            continue
        for violation in public_safety_violations(value):
            errors.append(
                f"public artifact unsafe {path.relative_to(REPO_ROOT)}: {violation}"
            )
        if not isinstance(value, dict):
            errors.append(
                f"replay fixture is not an object: {path.relative_to(REPO_ROOT)}"
            )
            continue
        try:
            replay = ReplayReadAdapter(value)
            replay_profile = build_capability_profile(replay, _fixture_context(replay))
            validate_document("capability_profile", replay_profile)
        except Exception as exc:
            errors.append(
                f"replay fixture invalid {path.relative_to(REPO_ROOT)}: {exc}"
            )

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
            "publication_paths": publication_path_count,
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
