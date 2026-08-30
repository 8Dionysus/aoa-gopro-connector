# Architecture

`aoa-gopro-connector` is a ports-and-adapters application around one physical
camera actor.

## Components

- `domain`: capability profile, composed camera state, operation plan, receipt,
  event, and media-manifest contracts.
- `adapters`: replay and transport-specific discovery, power, control, preview,
  and media ports.
- `application`: future lease, actor queue, reconciliation, deadlines,
  cancellation, and recovery supervision.
- `evidence`: canonical digests, public-safe profiles, journals, receipts, and
  manifest integrity.
- `interfaces`: CLI now; loopback daemon and admitted agent adapters later.

The OpenGoPro Python SDK is an optional adapter dependency. Domain contracts
and the USB/NCM read path do not import it.

## State topology

Camera state is composed from presence, power, control ownership, network
readiness, preview and recording activity, media lifecycle, and health. Preview
and recording are independent flags because a supported profile may permit
both at once.

```text
ABSENT → DISCOVERED → LEASED → WAKING → CONTROL_READY → NETWORK_READY
       → PREVIEWING / RECORDING → MEDIA_FINALIZING → IDLE → SLEEPING

working state → DEGRADED → RECOVERING → working state
                               └──────→ NEEDS_OPERATOR
```

The lifecycle is a projection of composed observations, not a second source of
truth. Transition invariants belong to the schema and domain tests.

## Effect topology

```text
read observation → candidate operation plan → exact approval
→ serialized camera actor → adapter acknowledgement
→ state reconciliation → postcondition verdict → receipt
```

The current implementation ends after read observation. Later layers must use
the same plan and receipt contracts rather than adding adapter-shaped effect
shortcuts.

## Media topology

Inventory produces an immutable manifest before any transfer. Derivatives and
originals retain separate checksums, provenance, retention classes, and
freshness. Semantic providers attach observations to media/event refs; they do
not rewrite the camera or transport record.
