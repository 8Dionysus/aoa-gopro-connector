# Source Policy

`aoa-gopro-connector` may observe or control only cameras the connected
Operator owns or is explicitly authorized to use. Camera media remains
Operator-owned source material.

## Source modes

- `live_read_only`: allowlisted camera information, state, and media inventory
  over an explicitly selected local topology.
- `sanitized_replay`: synthetic or allowlisted public-safe responses used for
  deterministic development and CI.
- `local_effect`: a future operator-facing plan/approval/receipt path owned by
  this repository.
- `admitted_effect`: a future `abyss-stack` bridge admitted separately from the
  read and candidate planes.

The Phase 0 live surface implements only `live_read_only`. Its route allowlist
is `connector/manifests/route_allowlist.yaml`.

## Identity and privacy

Camera serial number, hostname, MAC, SSID, credentials, certificates, network
address, private media names, and non-synthetic audio/video do not enter Git or
shareable evidence. Public capability profiles use a fixed redacted device ref
and retain only model, firmware, topology class, observation counts, capability
posture, and source references.

Live HTTP responses are parsed in memory through an allowlist. The public probe
does not retain raw payloads. Private runtime identity belongs under
`AOA_GOPRO_AUTH_ROOT`.

## Media posture

Inventory precedes transfer. Original files are immutable inputs. Selective
THM, LRV, original, and GPMF transfer will require manifests, checksums,
resumability, path safety, and explicit retention policy. MP4 and GPMF are
untrusted binary input and will be parsed with resource bounds.

## Effects

Every future effect must bind the exact camera ref, fresh capability-profile
digest, lease, preconditions, deadline, expected postconditions, idempotency
key, privacy/retention consequence, and required approval. API acknowledgement
alone is not success.

Firmware install/update, factory reset, and irreversible media deletion are
separate Operator-approved operations and are never implicit recovery.

Semantic observations come from named perception providers with confidence,
freshness, and evidence refs. They do not become transport truth.
