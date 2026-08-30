"""Operator CLI for offline and read-only Phase 0 surfaces."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .adapters import HTTPReadAdapter, ReplayReadAdapter
from .config import resolve_storage_roots
from .errors import ContractError, GoProConnectorError
from .json_io import strict_json_dumps, strict_json_loads
from .probe import (
    OPEN_GOPRO_DECLARED_PYTHON,
    OPEN_GOPRO_PUBLISHED_VERSION,
    ProbeContext,
    build_capability_profile,
)
from .schema import SCHEMA_NAMES, load_schema, schema_root, validate_document


LIVE_EVIDENCE_REF = "local-live-read-only:operator-authorized-camera"


def _json_text(value: Any) -> str:
    return (
        strict_json_dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )


def _emit(value: Any, output: str | None = None) -> None:
    text = _json_text(value)
    if output:
        Path(output).write_text(text, encoding="utf-8")
    sys.stdout.write(text)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _doctor() -> dict[str, Any]:
    roots = resolve_storage_roots()
    schema_status: dict[str, str] = {}
    for name in SCHEMA_NAMES:
        load_schema(name)
        schema_status[name] = "valid"
    sdk_present = importlib.util.find_spec("open_gopro") is not None
    sdk_version = None
    if sdk_present:
        try:
            sdk_version = metadata.version("open-gopro")
        except metadata.PackageNotFoundError:
            sdk_version = "unknown"
    return {
        "schema_version": "aoa_gopro_doctor_v1",
        "status": "ok",
        "package_version": __version__,
        "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        "effects_available": False,
        "live_routes": "read_only_allowlist",
        "schemas": schema_status,
        "schema_root": str(schema_root()),
        "storage": roots.as_dict(),
        "open_gopro_sdk": {
            "installed": sdk_present,
            "version": sdk_version,
            "published_version": OPEN_GOPRO_PUBLISHED_VERSION,
            "declared_python": OPEN_GOPRO_DECLARED_PYTHON,
            "current_python_compatible": (3, 11) <= sys.version_info[:2] < (3, 14),
            "required_for_phase_0_usb_read": False,
        },
    }


def _replay_probe(args: argparse.Namespace) -> dict[str, Any]:
    adapter = ReplayReadAdapter.from_path(args.fixture)
    fixture = adapter.fixture
    context_value = fixture.get("context", {})
    if not isinstance(context_value, dict):
        raise GoProConnectorError("replay fixture context is invalid")
    string_fields: dict[str, str] = {}
    for field in (
        "observed_at",
        "topology",
        "protocol_version",
        "firmware_posture",
    ):
        value = context_value.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"replay fixture context {field} is invalid")
        string_fields[field] = value
    discovery = context_value.get("discovery")
    if not isinstance(discovery, list) or any(
        not isinstance(item, str) or not item.strip() for item in discovery
    ):
        raise ContractError("replay fixture context discovery must be a string list")
    fixture_id = fixture.get("fixture_id")
    if not isinstance(fixture_id, str) or not fixture_id.strip():
        raise ContractError("replay fixture_id is invalid")
    context = ProbeContext(
        observed_at=string_fields["observed_at"],
        topology=string_fields["topology"],
        discovery=tuple(discovery),
        protocol_version=string_fields["protocol_version"],
        firmware_posture=string_fields["firmware_posture"],
        evidence_ref=f"fixture:{fixture_id}",
    )
    return build_capability_profile(adapter, context)


def _live_probe(args: argparse.Namespace) -> dict[str, Any]:
    context = ProbeContext(
        observed_at=args.observed_at or _utc_now(),
        topology=args.topology,
        discovery=tuple(args.discovery),
        protocol_version=args.protocol_version,
        firmware_posture=args.firmware_posture,
        evidence_ref=LIVE_EVIDENCE_REF,
    )
    context.validate()
    adapter = HTTPReadAdapter(args.base_url, timeout_seconds=args.timeout)
    return build_capability_profile(adapter, context)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aoa-gopro")
    parser.add_argument("--version", action="version", version=__version__)
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("doctor", help="inspect offline package readiness")

    replay = subcommands.add_parser(
        "replay-probe", help="build a profile from a public-safe replay"
    )
    replay.add_argument("fixture")
    replay.add_argument("--output")

    live = subcommands.add_parser(
        "probe", help="run the allowlisted live read-only HTTP probe"
    )
    live.add_argument("--base-url", required=True)
    live.add_argument(
        "--topology",
        choices=("usb_ncm_http", "wifi_ap_http", "cohn_http"),
        default="usb_ncm_http",
    )
    live.add_argument("--discovery", action="append", default=[])
    live.add_argument("--protocol-version", default="unknown")
    live.add_argument(
        "--firmware-posture",
        choices=("stock", "labs", "unknown"),
        default="unknown",
    )
    live.add_argument("--observed-at")
    live.add_argument("--timeout", type=float, default=5.0)
    live.add_argument("--output")

    schema = subcommands.add_parser("schema", help="schema operations")
    schema_commands = schema.add_subparsers(dest="schema_command", required=True)
    validate = schema_commands.add_parser("validate")
    validate.add_argument("schema_name", choices=SCHEMA_NAMES)
    validate.add_argument("document")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            _emit(_doctor())
        elif args.command == "replay-probe":
            _emit(_replay_probe(args), args.output)
        elif args.command == "probe":
            _emit(_live_probe(args), args.output)
        elif args.command == "schema" and args.schema_command == "validate":
            document = strict_json_loads(
                Path(args.document).read_text(encoding="utf-8")
            )
            validate_document(args.schema_name, document)
            _emit(
                {
                    "schema_version": "aoa_gopro_schema_validation_v1",
                    "status": "ok",
                    "schema": args.schema_name,
                    "document": str(Path(args.document)),
                }
            )
        else:
            raise GoProConnectorError("unknown command")
    except (GoProConnectorError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        sys.stderr.write(
            _json_text(
                {
                    "schema_version": "aoa_gopro_cli_error_v1",
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
