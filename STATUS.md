# Status

This document records durable capability state. Exact commands belong to the
CLI, tests, validator, workflow, and root `AGENTS.md`. Local runtime paths,
private device identity, and operator media are not repository status.

## Current posture

The repository has a Phase 0 PR candidate. Its source validator, six packet
schemas, public-artifact safety checks, replay path, durable test suite, static
check, sdist/wheel build, and wheel-installed doctor/replay route pass locally
and in the GitHub Python 3.11/3.13/3.14 PR-head matrix. Review and landing
remain separate evidence. No release, deployment, effect admission, semantic
acceptance, or Goal closure is claimed.

## Named hardware baseline

A sanitized profile records one GoPro HERO13 Black with stock firmware
`2.10.00`, observed through USB/NCM and mDNS on 2026-08-29. Camera information,
state, and an empty media inventory were readable. Raw responses, address,
hostname, serial number, MAC, and SSID were discarded.

The baseline proves only a read-only contact with one named model/firmware/
topology profile. BLE, Wi-Fi AP, COHN, control, wake/sleep, preview, recording,
Hilight, media transfer, GPMF, disconnect recovery, and soak remain unprobed.
GoPro Labs is not installed on this profile.

## Dependency posture

The published `open-gopro` Python SDK baseline is `0.22.0` and declares Python
`>=3.11,<3.14`. The connector core therefore does not require the SDK: its
Phase 0 USB/NCM read path uses the standard library and runs on Python 3.14.
Future BLE/Wi-Fi SDK integration remains behind an optional adapter and a named
compatibility profile.

## Claim ladder

| Claim | State |
| --- | --- |
| Source-ready | Phase 0 PR candidate; review and landing remain separate |
| Offline-CI-ready | Local and GitHub PR-head validator/tests/install green |
| Named hardware profile-ready | Read-only baseline only |
| Standalone-runtime-ready | Not established |
| Deployed | Not established |
| Read-admitted | Not established |
| Effect-admitted | Not established |
| Semantic-scenario-accepted | Not established |
| Release-ready | Not established |
| Goal-accepted | Not established |
