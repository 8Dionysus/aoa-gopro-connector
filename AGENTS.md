# AGENTS.md

Root route card for `aoa-gopro-connector`.

## Purpose

This repository owns the GoPro camera member of the AoA connector family:
camera capability and quirk profiles, composed state, operation plans and
receipts, transport adapters, stream and media manifests, a future GoPro Labs
compiler, simulator/replay support, CLI, and a loopback daemon contract.

It is a physical sensor/actuator connector. It does not inherit crawl, search,
or answer semantics from evidence-source connectors.

## Boundaries

- Git contains public method, schemas, source, tests, synthetic fixtures, and
  sanitized capability profiles only.
- Credentials, certificates, private media, real device identifiers, network
  identity, and non-synthetic home audio/video stay outside Git.
- The current live probe surface is read-only and may call only the allowlisted
  camera information, state, and media-inventory endpoints.
- Firmware install/update, factory reset, and irreversible media deletion need
  a separate exact plan and explicit Operator approval.
- Runtime deployment and authenticated agent exposure belong to `abyss-stack`.
  Host device, storage, permission, and resource facts belong to
  `abyss-machine`.
- Central proof belongs to `aoa-evals`; shared measurement grammar belongs to
  `aoa-stats`; KAG is derived navigation.

## Read before editing

1. `CHARTER.md`, `BOUNDARIES.md`, and the relevant document under `docs/`.
2. `connector/SOURCE_POLICY.md` for camera, media, privacy, or effect changes.
3. `STORAGE_POLICY.md` for data classes, roots, retention, or artifact changes.
4. `STATUS.md` before changing a readiness or support claim.
5. The executable owner: schema, CLI parser, validator, test, or workflow for
   the changed contract.

## Test-surface lifecycle

Permanent tests must name the stable contract or recurring risk they protect.
Capability experiments, endpoint probes, packet captures, firmware-specific
reproducers, and incident scripts stay in task-local scratch. At the end of a
phase, promote the smallest durable contract test or remove the temporary
surface and its generated artifacts.

## Validation

Run from the repository root:

```bash
python scripts/validate_connector.py
python -m ruff check src tests scripts
python -m pytest -q
python -m aoa_gopro_connector.cli doctor
python -m aoa_gopro_connector.cli replay-probe \
  connector/fixtures/hero13/stock-usb-ncm-read-only.json
python scripts/verify_install_route.py
```

Hardware-in-the-loop commands are opt-in and prove only the named camera,
firmware, topology, and observed operation. Exact CLI syntax belongs to the
parser and `--help`; ordinary documentation links to that owner instead of
copying command catalogs.
