# AOA-GOPRO-D-0002: optional OpenGoPro SDK

## Status

Accepted.

## Context

The current published `open-gopro` SDK is `0.22.0` and declares Python
`>=3.11,<3.14`, while the active host runs Python 3.14. The official USB HTTP
API needed by the Phase 0 read path is simple and independently specified.

## Decision

Keep domain contracts, replay, schemas, and the allowlisted USB/NCM HTTP reader
compatible with Python 3.11 and newer without importing the SDK. Pin the SDK as
an optional adapter dependency only on supported Python versions. BLE/Wi-Fi SDK
work must carry an exact compatibility profile and may not leak SDK objects into
the domain.

## Consequence

The current host can develop and validate the core honestly. Absence of the SDK
does not become BLE/Wi-Fi readiness, and a future SDK release can replace the
adapter without changing operation or receipt semantics.
